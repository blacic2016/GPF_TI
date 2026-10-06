"""
Demonio Principal de Escucha MAPI de Outlook en Tiempo Real para NOVAIOPS.
Utiliza win32com.client con WithEvents y PumpWaitingMessages con Worker Pool Multihilo.
"""

import sys
import os
import time
import re
import json
import queue
import threading
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

# Importación de Configuración de Logging y Payload Firewall de SYNAPSE-ORQ
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.logging_config import init_synapse_logger
from daemon.payload_firewall import sanitize_and_filter_email
from database.db_manager import get_db_connection
from handlers.email_handlers import get_handler

logger = init_synapse_logger()

# Cola thread-safe en memoria para desacoplar el evento MAPI COM de SYNAPSE-ORQ
email_queue = queue.Queue()
is_daemon_running = True

# Registro global en memoria para evitar que un mismo correo sea analizado más de 1 vez
processed_emails_cache = set()
processed_cache_lock = threading.Lock()

try:
    import pythoncom
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False
    logger.warning("win32com / pythoncom no disponibles en este entorno. Se activará el simulador MAPI de SYNAPSE-ORQ.")

class OutlookEventHandler:
    """Clase que intercepta los eventos de Outlook mediante win32com WithEvents bajo SYNAPSE-ORQ Firewall"""
    def OnItemAdd(self, item):
        try:
            # Filtrar únicamente mensajes de correo (IPM.Note) y sanitizar con SYNAPSE-ORQ Firewall
            if hasattr(item, "MessageClass") and item.MessageClass == "IPM.Note":
                # Solo procesar si la Bandeja de entrada o la carpeta del ítem está activamente en Manage Monitoreo
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM automation_scripts WHERE status = 'active' AND (target_folder_path LIKE '%Bandeja de entrada%' OR target_folder_path LIKE '%Inbox%')")
                is_monitored = cursor.fetchone()[0] > 0
                conn.close()

                if not is_monitored:
                    # No hay monitoreos creados para la Bandeja de entrada en Manage Monitoreo
                    return

                sanitized_email = sanitize_and_filter_email(item)
                if sanitized_email:
                    subject = sanitized_email.get('subject', '')
                    sender = sanitized_email.get('sender', '')
                    recv_time = sanitized_email.get('received_time', '')
                    entry_id = sanitized_email.get('entry_id', '')

                    key1 = f"entry::{entry_id.strip()}" if entry_id else ""
                    key2 = f"key::{subject.strip().lower()}::{sender.strip().lower()}::{recv_time.strip()}"

                    with processed_cache_lock:
                        if (key1 and key1 in processed_emails_cache) or (key2 in processed_emails_cache):
                            return

                    logger.info(f"[SYNAPSE-ORQ ITEM_ADD] Correo capturado para carpeta monitoreada: '{subject}' de {sender}")
                    email_queue.put(sanitized_email)
        except Exception as e:
            logger.error(f"Error procesando evento ItemAdd MAPI en SYNAPSE-ORQ: {str(e)}")

CORE_SERVER_URL = os.environ.get("SYNAPSE_CORE_URL", "http://127.0.0.1:5000")
import urllib.request

def record_daemon_heartbeat(status="ONLINE", metrics=None, details=""):
    """Registra la telemetría del Demonio MAPI en la base de datos para visualización en pantalla"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        metrics_str = json.dumps(metrics or {})
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
        INSERT INTO microservices_heartbeat 
        (service_id, service_name, role, status, last_heartbeat, metrics_json, details)
        VALUES ('mapi_reader_daemon', 'Microservicio 1: MAPI Reader Daemon', 'Lector MAPI Outlook & Dispatcher HTTP', ?, ?, ?, ?)
        ON CONFLICT(service_id) DO UPDATE SET
        status = excluded.status,
        last_heartbeat = excluded.last_heartbeat,
        metrics_json = excluded.metrics_json,
        details = excluded.details
        """, (status, now_str, metrics_str, details))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"No se pudo registrar heartbeat del demonio: {e}")

def dispatch_email_to_core(email_data):
    """
    Microservicio 1 -> Microservicio 2:
    Despacha el correo detectado al Core Server mediante llamada HTTP REST.
    Si el Core Server está ocupado o reiniciando, reintenta de forma no bloqueante.
    """
    url = f"{CORE_SERVER_URL}/api/daemon/inbound_email"
    headers = {"Content-Type": "application/json"}
    body_json = json.dumps(email_data).encode("utf-8")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=body_json, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status == 200:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    logger.info(f"[DISPATCHER HTTP] Correo '{email_data.get('subject')}' despachado exitosamente al Core Server: {resp_data.get('script_name')} | Traslado: {resp_data.get('moved_to_analizados')}")
                    return True
        except Exception as err:
            logger.warning(f"[DISPATCHER HTTP] Intento #{attempt+1} falló al enviar correo al Core Server ({url}): {err}")
            time.sleep(1.0)
    logger.error(f"[DISPATCHER HTTP ERROR] No se pudo enviar el correo '{email_data.get('subject')}' al Core Server tras {max_retries} intentos.")
    return False

def process_email_worker(worker_id):
    """Worker Thread Pool desacoplado: despacha correos vía HTTP al Microservicio 2 (Core Server)"""
    logger.info(f"Worker Dispatcher Thread #{worker_id} iniciado.")
    while is_daemon_running:
        try:
            try:
                email_data = email_queue.get(timeout=2)
            except queue.Empty:
                continue

            subject = email_data.get("subject", "")
            sender = email_data.get("sender", "")
            received_at = email_data.get("received_at") or email_data.get("received_time") or ""
            entry_id = email_data.get("entry_id") or ""

            if entry_id:
                email_key = f"entry::{entry_id.strip()}"
            else:
                email_key = f"key::{subject.strip().lower()}::{sender.strip().lower()}::{received_at.strip()}"

            with processed_cache_lock:
                if email_key in processed_emails_cache:
                    logger.info(f"[WORKER #{worker_id}] Correo ya despachado previamente ('{subject}'). Omitiendo duplicado.")
                    email_queue.task_done()
                    continue
                processed_emails_cache.add(email_key)
                if len(processed_emails_cache) > 20000:
                    processed_emails_cache.clear()

            logger.info(f"[WORKER #{worker_id}] Despachando correo al Server Central: '{subject}' (De: {sender})")
            dispatch_email_to_core(email_data)
            email_queue.task_done()

        except Exception as e:
            logger.error(f"[WORKER #{worker_id}] Excepción grave en worker dispatcher: {str(e)}", exc_info=True)

def start_daemon():
    """Inicia el demonio MAPI con 3 Hilos de Trabajadores y monitoreo de subcarpetas"""
    global is_daemon_running
    logger.info("Iniciando Demonio de Escucha MAPI de Outlook en Tiempo Real...")
    
    # Arrancar Worker Threads
    threads = []
    for i in range(3):
        t = threading.Thread(target=process_email_worker, args=(i+1,), daemon=True)
        t.start()
        threads.append(t)

    # Sub-hilo de rastreo en tiempo real para subcarpetas (ej. SEGUROSALIANZA / synapse_org)
    seen_email_entry_ids = set()
    
    def folder_poller():
        logger.info("Poller MAPI de Monitoreo continuo activado (escaneando carpetas de monitoreos activos)...")
        while is_daemon_running:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT target_folder_path FROM automation_scripts WHERE status = 'active' AND (step1_enabled IS NULL OR step1_enabled != 0) AND target_folder_path IS NOT NULL AND target_folder_path != ''")
                rows = cursor.fetchall()
                target_folders = [r["target_folder_path"] for r in rows]
                conn.close()

                if target_folders:
                    from handlers.real_connections import get_real_outlook_emails
                    for fpath in target_folders:
                        emails = get_real_outlook_emails(fpath)
                        for e in emails:
                            eid = e.get('entry_id') or f"{fpath}::{e.get('subject', '')}::{e.get('received_at', '')}"
                            key1 = f"entry::{e.get('entry_id', '').strip()}" if e.get('entry_id') else ""
                            key2 = f"key::{e.get('subject', '').strip().lower()}::{e.get('sender', '').strip().lower()}::{e.get('received_at', '').strip()}"

                            with processed_cache_lock:
                                if (key1 and key1 in processed_emails_cache) or (key2 in processed_emails_cache):
                                    continue
                                if eid in seen_email_entry_ids:
                                    continue
                                seen_email_entry_ids.add(eid)
                                if len(seen_email_entry_ids) > 10000:
                                    seen_email_entry_ids.clear()

                            e["folder"] = fpath
                            logger.info(f"[POLLER CARPETA ACTIVA] Nuevo correo detectado para procesar en '{fpath}': '{e.get('subject')}' (De: {e.get('sender')})")
                            email_queue.put(e)
            except Exception as poll_err:
                logger.warning(f"Advertencia en Poller continuo de Carpetas: {poll_err}")
            
            # Chequeo continuo cada 5 segundos para que la detección sea rápida y precisa
            try:
                num_folders = len(target_folders) if 'target_folders' in locals() else 0
                f_names = [f.split('/')[-1] for f in target_folders] if 'target_folders' in locals() else []
                detail_msg = f"Escaneando cada 5s | {num_folders} carpeta(s) activa(s): {', '.join(f_names) if f_names else 'Ninguna'}"
                record_daemon_heartbeat(status="ONLINE", metrics={"queue_size": email_queue.qsize(), "monitored_folders": num_folders, "interval_sec": 5}, details=detail_msg)
            except Exception:
                pass
            time.sleep(5.0)

    poller_thread = threading.Thread(target=folder_poller, daemon=True)
    poller_thread.start()

    # Heartbeat inicial
    record_daemon_heartbeat(status="ONLINE", metrics={"queue_size": 0}, details="Inicializando MAPI Listener...")

    if HAS_WIN32COM:
        last_hb = 0
        while is_daemon_running:
            try:
                pythoncom.CoInitialize()
                outlook = win32com.client.Dispatch("Outlook.Application")
                mapi = outlook.GetNamespace("MAPI")
                inbox = mapi.GetDefaultFolder(6) # 6 = olFolderInbox
                
                # Registrar Manejador sobre la Bandeja de Entrada Principal
                win32com.client.WithEvents(inbox.Items, OutlookEventHandler)
                logger.info("Manejador de eventos MAPI WithEvents registrado sobre la Bandeja de Entrada.")

                while is_daemon_running:
                    pythoncom.PumpWaitingMessages()
                    time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error de conexión MAPI en el Demonio: {str(e)}. Reintentando en 5 segundos...")
                record_daemon_heartbeat(status="WARNING", metrics={"error": str(e)}, details=f"Reintentando MAPI: {str(e)[:50]}")
                time.sleep(5)
            finally:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
    else:
        logger.info("Modo de simulación MAPI activo. Esperando correos desde la API Web/Test UI...")
        try:
            while is_daemon_running:
                time.sleep(1)
        except KeyboardInterrupt:
            is_daemon_running = False

if __name__ == "__main__":
    import re
    start_daemon()
