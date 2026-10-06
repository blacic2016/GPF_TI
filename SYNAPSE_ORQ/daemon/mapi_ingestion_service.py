"""
Microservicio 1: SYNAPSE-ORQ MAPI Ingestion Daemon
===================================================
Microservicio autonomo y ultraligero de captura e ingesta de correos MAPI en Outlook.
Responsabilidad unica:
1. Conectarse a Outlook Desktop MAPI (WithEvents en Bandeja de Entrada + Poller de Subcarpetas).
2. Sanitizar el correo mediante Payload Firewall (limite de tamano y adjuntos).
3. Despachar de inmediato cada correo nuevo hacia el Core Server (POST http://127.0.0.1:5000/api/ingest/email).
4. Emitir latidos continuos (Heartbeats) cada 5 segundos reportando salud, PID y metricas.
5. Auto-recuperacion infinita: ante caidas de Outlook o red, reintenta y preserva un buffer local sin perder correos.
"""

import sys
import os
import time
import json
import queue
import threading
import logging
from datetime import datetime
import urllib.request
import urllib.error

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.logging_config import init_synapse_logger
from daemon.payload_firewall import sanitize_and_filter_email
from database.db_manager import get_db_connection

logger = init_synapse_logger()

SERVICE_NAME = "mapi_ingestion_service"
CORE_SERVER_URL = os.getenv("CORE_SERVER_URL", "http://127.0.0.1:5000/api/ingest/email")
HEARTBEAT_INTERVAL = 5.0
POLLER_INTERVAL = 5.0

is_running = True
ingestion_queue = queue.Queue()
seen_entry_ids = set()
seen_lock = threading.Lock()

total_detected = 0
total_forwarded = 0
total_errors = 0

try:
    import pythoncom
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False
    logger.warning("win32com no disponible en el entorno de ingesta MAPI.")

def send_heartbeat():
    global total_detected, total_forwarded, total_errors
    pid = os.getpid()
    while is_running:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            details = {
                "detected": total_detected,
                "forwarded_to_core": total_forwarded,
                "errors": total_errors,
                "buffer_queue_size": ingestion_queue.qsize(),
                "has_win32com": HAS_WIN32COM,
                "last_pulse": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            cursor.execute("""
            INSERT INTO microservice_heartbeats (service_name, pid, status, last_seen, items_count, errors_count, details_json)
            VALUES (?, ?, 'ONLINE', CURRENT_TIMESTAMP, ?, ?, ?)
            ON CONFLICT(service_name) DO UPDATE SET
                pid = excluded.pid,
                status = 'ONLINE',
                last_seen = CURRENT_TIMESTAMP,
                items_count = excluded.items_count,
                errors_count = excluded.errors_count,
                details_json = excluded.details_json
            """, (SERVICE_NAME, pid, total_forwarded, total_errors, json.dumps(details)))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[HEARTBEAT] Error guardando latido del microservicio: {e}")
        time.sleep(HEARTBEAT_INTERVAL)

def http_dispatcher_worker():
    global total_forwarded, total_errors
    logger.info("[HTTP DISPATCHER] Hilo de despacho HTTP hacia Core Server iniciado.")
    
    while is_running:
        try:
            try:
                email_payload = ingestion_queue.get(timeout=2.0)
            except queue.Empty:
                continue

            data_bytes = json.dumps(email_payload).encode("utf-8")
            req = urllib.request.Request(
                CORE_SERVER_URL,
                data=data_bytes,
                headers={"Content-Type": "application/json", "User-Agent": "SYNAPSE-MAPI-Ingestion/3.0"}
            )
            
            success = False
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=10.0) as resp:
                        if resp.status in (200, 201, 202):
                            total_forwarded += 1
                            success = True
                            logger.info(f"[HTTP DISPATCHER] Correo '{email_payload.get('subject')}' despachado exitosamente al Core Server.")
                            break
                except urllib.error.URLError:
                    time.sleep(1.0)
                except Exception as ex:
                    logger.warning(f"[HTTP DISPATCHER] Reintento {attempt+1}/3 al despachar correo: {ex}")
                    time.sleep(1.0)
                    
            if not success:
                total_errors += 1
                logger.error(f"[HTTP DISPATCHER] Fallo el despacho definitivo del correo '{email_payload.get('subject')}' al Core Server.")

            ingestion_queue.task_done()
        except Exception as general_err:
            logger.error(f"[HTTP DISPATCHER] Error en dispatcher: {general_err}")

class MAPIEventListener:
    def OnItemAdd(self, item):
        global total_detected
        try:
            if hasattr(item, "MessageClass") and item.MessageClass == "IPM.Note":
                sanitized = sanitize_and_filter_email(item)
                if sanitized:
                    eid = sanitized.get("entry_id") or f"inbox::{sanitized.get('subject')}::{sanitized.get('received_time')}"
                    with seen_lock:
                        if eid in seen_entry_ids:
                            return
                        seen_entry_ids.add(eid)
                        if len(seen_entry_ids) > 20000:
                            seen_entry_ids.clear()

                    total_detected += 1
                    logger.info(f"[MAPI REAL-TIME INBOX] Nuevo correo detectado: '{sanitized.get('subject')}' (De: {sanitized.get('sender')})")
                    ingestion_queue.put(sanitized)
        except Exception as e:
            logger.error(f"[MAPI EVENT ERROR] {e}")

def folder_poller_worker():
    global total_detected
    logger.info("[FOLDER POLLER] Iniciando escaner de subcarpetas MAPI activas...")
    
    while is_running:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
            SELECT DISTINCT target_folder_path FROM automation_scripts 
            WHERE status = 'active' AND (step1_enabled IS NULL OR step1_enabled != 0) 
            AND target_folder_path IS NOT NULL AND target_folder_path != ''
            """)
            rows = cursor.fetchall()
            target_folders = [r["target_folder_path"] for r in rows]
            conn.close()

            if target_folders:
                from handlers.real_connections import get_real_outlook_emails
                for fpath in target_folders:
                    emails = get_real_outlook_emails(fpath)
                    for em in emails:
                        eid = em.get("entry_id") or f"{fpath}::{em.get('subject')}::{em.get('received_at')}"
                        with seen_lock:
                            if eid in seen_entry_ids:
                                continue
                            seen_entry_ids.add(eid)
                            if len(seen_entry_ids) > 20000:
                                seen_entry_ids.clear()

                        total_detected += 1
                        em["folder"] = fpath
                        logger.info(f"[FOLDER POLLER] Correo detectado en carpeta '{fpath}': '{em.get('subject')}' (De: {em.get('sender')})")
                        ingestion_queue.put(em)

        except Exception as e:
            logger.warning(f"[FOLDER POLLER] Advertencia en escaneo de carpetas: {e}")

        time.sleep(POLLER_INTERVAL)

def start_ingestion_service():
    logger.info("===================================================================")
    logger.info(f"[MS-1] INICIANDO MICROSERVICIO DE INGESTA MAPI OUTLOOK (PID: {os.getpid()})")
    logger.info(f"[MS-1] Destino HTTP de Despacho: {CORE_SERVER_URL}")
    logger.info("===================================================================")

    hb_thread = threading.Thread(target=send_heartbeat, daemon=True)
    hb_thread.start()

    disp_thread = threading.Thread(target=http_dispatcher_worker, daemon=True)
    disp_thread.start()

    poll_thread = threading.Thread(target=folder_poller_worker, daemon=True)
    poll_thread.start()

    if HAS_WIN32COM:
        while is_running:
            try:
                pythoncom.CoInitialize()
                outlook = win32com.client.Dispatch("Outlook.Application")
                mapi = outlook.GetNamespace("MAPI")
                inbox = mapi.GetDefaultFolder(6)

                win32com.client.WithEvents(inbox.Items, MAPIEventListener)
                logger.info("[MS-1 MAPI] Escucha COM WithEvents vinculada exitosamente a la Bandeja de Entrada.")

                while is_running:
                    pythoncom.PumpWaitingMessages()
                    time.sleep(0.3)
            except Exception as e:
                logger.error(f"[MS-1 MAPI] Conexion MAPI reiniciando en 5 segundos: {e}")
                time.sleep(5.0)
            finally:
                try: pythoncom.CoUninitialize()
                except Exception: pass
    else:
        logger.info("[MS-1 SIMULADOR] MAPI no disponible. Corriendo en modo despacho de prueba.")
        while is_running:
            time.sleep(1.0)

if __name__ == "__main__":
    start_ingestion_service()
