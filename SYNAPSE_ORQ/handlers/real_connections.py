"""
Mapeador de Inspección MAPI Real y Conexiones a Infraestructura SONDA / GPF.
Inspecciona el árbol de Outlook Desktop / MAPI real del cliente y conecta a APIs reales (Turnos, Mantis, DB, Zabbix).
"""

import os
import re
import sys
import json
import logging
import requests
import threading
from datetime import datetime

logger = logging.getLogger("NOVAIOPS_CONNECTIONS")

# ====================================================================
# 1. PARÁMETROS Y CONSTANTES EXTRAÍDAS DE LOS SCRIPTS PYTHONOLD REALES
# ====================================================================
MANTIS_URL = os.getenv("MANTIS_URL", "http://172.32.1.51:10090/api/rest/issues")
MANTIS_AUTH_TOKEN = os.getenv("MANTIS_AUTH_TOKEN", "B6knU4vQYh9bSx-ukxmlcS9PgqcqOLTy")
MANTIS_NETWORKER_TOKEN = os.getenv("MANTIS_NETWORKER_TOKEN", "jWma-n55OtqOd1j_HuS85LPRrWsdE-40")

API_TURNOS_URL = os.getenv("API_TURNOS_URL", "http://172.32.1.55:3001/turnos/actual-correo")
API_SIGLAS_URL = os.getenv("API_SIGLAS_URL", "http://172.32.1.51/usuario/dataSiglas.php")

ZABBIX_SERVER = os.getenv("ZABBIX_SERVER", "172.32.1.50")
ZABBIX_PORT = "10051"
ZABBIX_SENDER_EXE = os.getenv("ZABBIX_SENDER_EXE", r"C:\zabbix\bin\zabbix_sender.exe")

DB_HOST = os.getenv("DB_HOST", "172.32.1.51")
DB_USER = os.getenv("DB_USER", "zabbixuser")
DB_PASS = os.getenv("DB_PASS", "zabbix")
DB_NAME = os.getenv("DB_NAME", "zabbix")

OUTLOOK_MAILBOX_GPF = "monitoreosistemas@corporaciongpf.com"

try:
    import win32com.client
    import pythoncom
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False

# ====================================================================
# 2. FUNCIONES DE SERVICIOS EXTERNOS REALES
# ====================================================================

def get_operador_turno_real() -> str:
    """Obtiene el correo del operador de turno actual desde la API real de SONDA/GPF."""
    try:
        res = requests.get(API_TURNOS_URL, timeout=3)
        if res.status_code == 200:
            return res.text.strip()
    except Exception as e:
        logger.warning(f"No se pudo consultar API de Turnos ({e}). Usando fallback.")
    return "oscar.guerra@sonda.com"

def get_operador_siglas_real() -> str:
    """Obtiene las siglas del operador desde la API PHP real."""
    try:
        res = requests.get(API_SIGLAS_URL, timeout=3)
        if res.status_code == 200:
            return res.text.strip().replace("[", "").replace("]", "").replace('"', '')
    except Exception as e:
        logger.warning(f"No se pudo consultar API de Siglas ({e}). Usando fallback.")
    return "OG"

def send_zabbix_alarm_real(host_ip: str, key: str, json_payload: dict) -> bool:
    """Envía métricas a Zabbix Server mediante zabbix_sender real."""
    if not os.path.exists(ZABBIX_SENDER_EXE):
        logger.warning(f"zabbix_sender.exe no encontrado en {ZABBIX_SENDER_EXE}. Omite envío real.")
        return False
    
    escaped_json = json.dumps(json_payload).replace('"', '\\"')
    cmd = f'{ZABBIX_SENDER_EXE} -z {ZABBIX_SERVER} -s "{host_ip}" -k "{key}" -o "{escaped_json}"'
    try:
        os.system(cmd)
        logger.info(f"Métrica enviada a Zabbix Server ({ZABBIX_SERVER}) para clave {key}")
        return True
    except Exception as e:
        logger.error(f"Error al ejecutar zabbix_sender: {e}")
        return False

def move_email_to_analizado_real(folder_path: str, email_subject: str, entry_id: str = None, target_subfolder_name: str = "analizados") -> bool:
    """Mueve el correo especificado en Outlook Desktop MAPI a la subcarpeta interna elegida (por defecto 'analizados')."""
    if not HAS_WIN32COM:
        return False
        
    move_res = [False]
    subfolder_target = (target_subfolder_name or "analizados").strip()
    def _move_worker():
        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            
            target_folder = _find_folder_by_path(namespace, folder_path) if folder_path else namespace.GetDefaultFolder(6)
            if not target_folder:
                target_folder = namespace.GetDefaultFolder(6)

            # Buscar o crear subcarpeta interna dentro de la carpeta revisada
            analizado_folder = None
            for sub in target_folder.Folders:
                if sub.Name.lower() == subfolder_target.lower():
                    analizado_folder = sub
                    break
                    
            if not analizado_folder:
                analizado_folder = target_folder.Folders.Add(subfolder_target)
                logger.info(f"Subcarpeta '{subfolder_target}' creada exitosamente en '{target_folder.Name}'")

            target_item = None
            # 1. Búsqueda directa por EntryID
            if entry_id:
                try:
                    target_item = namespace.GetItemFromID(entry_id)
                except Exception:
                    target_item = None

            # 2. Búsqueda por Subject en la carpeta
            if not target_item:
                norm_target = (email_subject or "").strip().lower()
                for item in target_folder.Items:
                    subj = (getattr(item, "Subject", "") or "").strip().lower()
                    if norm_target and (norm_target in subj or subj in norm_target):
                        target_item = item
                        break

            # 3. Fallback: Si no tiene asunto pero hay ítems en la carpeta
            if not target_item and not email_subject and target_folder.Items.Count > 0:
                target_item = target_folder.Items.GetLast()

            if target_item:
                target_item.Move(analizado_folder)
                logger.info(f"Correo '{getattr(target_item, 'Subject', '(Sin Asunto)')}' movido exitosamente a la subcarpeta 'analizados' de '{target_folder.Name}'")
                move_res[0] = True
            else:
                logger.warning(f"No se encontró el correo '{email_subject}' en '{target_folder.Name}' para mover a 'analizados'")
        except Exception as e:
            logger.error(f"Error moviendo correo a 'analizados': {e}")
        finally:
            try: pythoncom.CoUninitialize()
            except Exception: pass

    t = threading.Thread(target=_move_worker, daemon=True)
    t.start()
    t.join(timeout=10.0)
    return move_res[0]

def forward_email_real(folder_path: str, email_subject: str, target_email: str) -> bool:
    """Reenvía un correo en Outlook Desktop MAPI a una dirección de destino especificada."""
    if not HAS_WIN32COM or not target_email:
        return False
        
    def _forward_worker():
        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            
            target_folder = _find_folder_by_path(namespace, folder_path) if folder_path else namespace.GetDefaultFolder(6)
            if not target_folder:
                target_folder = namespace.GetDefaultFolder(6)

            for item in target_folder.Items:
                if hasattr(item, "Subject") and email_subject.lower() in item.Subject.lower():
                    forward_msg = item.Forward()
                    forward_msg.To = target_email
                    forward_msg.Send()
                    logger.info(f"Correo '{item.Subject}' reenviado exitosamente a '{target_email}'")
                    return True
        except Exception as e:
            logger.error(f"Error reenviando correo real: {e}")
        finally:
            try: pythoncom.CoUninitialize()
            except Exception: pass
        return False

    t = threading.Thread(target=_forward_worker, daemon=True)
    t.start()
    t.join(timeout=4.0)
    return True

# ====================================================================
# 3. INSPECCIÓN REAL DEL ÁRBOL DE CARPETAS DE OUTLOOK
# ====================================================================

def check_outlook_connection():
    """
    Verifica si Outlook MAPI responde activamente.
    Retorna un diccionario con estado de conexión y detalles.
    """
    if not HAS_WIN32COM:
        return {
            "connected": False,
            "status": "SIN_WIN32COM",
            "message": "win32com no disponible en este sistema. Modo simulación activo."
        }

    res_container = {"connected": False, "status": "DESCONECTADO", "message": "Outlook no responde en el tiempo límite."}
    
    def _check_worker():
        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            inbox = namespace.GetDefaultFolder(6)
            res_container["connected"] = True
            res_container["status"] = "CONECTADO"
            res_container["message"] = f"Conexión activa a MAPI Outlook ({inbox.Items.Count} msgs en Inbox)"
        except Exception as e:
            res_container["connected"] = False
            res_container["status"] = "ERROR_MAPI"
            res_container["message"] = f"Error al conectar con Outlook: {str(e)}"
        finally:
            try: pythoncom.CoUninitialize()
            except Exception: pass

    t = threading.Thread(target=_check_worker, daemon=True)
    t.start()
    t.join(timeout=2.0)
    
    return res_container

def get_real_outlook_accounts():
    """
    Retorna la lista de cuentas/buzones reales configurados en Outlook MAPI Desktop.
    Prioriza 'marco.vizcaino@sonda.com' y excluye archivos comprimidos o carpetas públicas secundarias.
    """
    if not HAS_WIN32COM:
        return ["marco.vizcaino@sonda.com", "monitoreosistemas@corporaciongpf.com", "Support BOC"]

    accounts = []
    def _acc_worker():
        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            for f in namespace.Folders:
                name = f.Name
                # Excluir archivos comprimidos y carpetas públicas secundarias
                if not name.startswith("Online Archive") and not name.startswith("Public Folders"):
                    accounts.append(name)
        except Exception as e:
            logger.error(f"Error obteniendo cuentas MAPI: {e}")
        finally:
            try: pythoncom.CoUninitialize()
            except Exception: pass

    t = threading.Thread(target=_acc_worker, daemon=True)
    t.start()
    t.join(timeout=4.0)

    # Asegurar que marco.vizcaino@sonda.com esté al inicio si existe
    if "marco.vizcaino@sonda.com" in accounts:
        accounts.remove("marco.vizcaino@sonda.com")
        accounts.insert(0, "marco.vizcaino@sonda.com")

    return accounts if accounts else ["marco.vizcaino@sonda.com", "monitoreosistemas@corporaciongpf.com", "Support BOC"]

def get_real_outlook_folder_tree(account_name: str = None, top_level_only: bool = True):
    """
    Se conecta a la sesión MAPI activa de Outlook Desktop y navega por las carpetas principales reales.
    Si top_level_only=True, retorna únicamente las carpetas principales del buzón seleccionado (sin subcarpetas profundas).
    """
    if not HAS_WIN32COM:
        return []

    results = []

    def _tree_worker():
        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            
            target_accs = []
            if account_name:
                for acc_folder in namespace.Folders:
                    if account_name.lower() in acc_folder.Name.lower():
                        target_accs.append(acc_folder)
                        break

            if not target_accs:
                target_accs = list(namespace.Folders)

            for acc_folder in target_accs:
                acc_name = acc_folder.Name
                # Recorrer solo carpetas principales (depth=0) si top_level_only es True
                max_d = 0 if top_level_only else 2
                for subfolder in acc_folder.Folders:
                    _traverse_outlook_folder(subfolder, f"{acc_name}/{subfolder.Name}", results, depth=0, max_depth=max_d)
        except Exception as e:
            logger.error(f"Error explorando carpetas Outlook: {e}")
        finally:
            try: pythoncom.CoUninitialize()
            except Exception: pass

    t = threading.Thread(target=_tree_worker, daemon=True)
    t.start()
    t.join(timeout=5.0)

    return results

def get_real_outlook_inbox_subfolders(account_name: str = None):
    """
    Localiza de manera exacta la 'Bandeja de entrada' del buzón indicado
    y retorna ÚNICAMENTE sus subcarpetas hijas directas (excluyendo carpetas de sistema fuera de la bandeja de entrada).
    """
    if not HAS_WIN32COM:
        return [
            {"folder_path": f"{account_name or 'marco.vizcaino@sonda.com'}/Bandeja de entrada/GPF", "folder_name": "GPF", "count": 0},
            {"folder_path": f"{account_name or 'marco.vizcaino@sonda.com'}/Bandeja de entrada/SEGUROSALIANZA", "folder_name": "SEGUROSALIANZA", "count": 1},
            {"folder_path": f"{account_name or 'marco.vizcaino@sonda.com'}/Bandeja de entrada/synapse_org", "folder_name": "synapse_org", "count": 2},
        ]

    subfolders = []
    def _inbox_worker():
        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            
            # 1. Encontrar la cuenta específica
            target_acc = None
            if account_name:
                acc_clean = account_name.strip().lower()
                for f in namespace.Folders:
                    if f.Name.strip().lower() == acc_clean:
                        target_acc = f
                        break
                if not target_acc:
                    for f in namespace.Folders:
                        if acc_clean in f.Name.lower() and not f.Name.lower().startswith("public"):
                            target_acc = f
                            break

            # 2. Si no se especificó o no se encontró, buscar en buzón primario
            inbox_folder = None
            if target_acc:
                acc_name = target_acc.Name
                for sub in target_acc.Folders:
                    s_low = sub.Name.lower()
                    if s_low in ["bandeja de entrada", "inbox"] or "entrada" in s_low:
                        inbox_folder = sub
                        break
            else:
                inbox_folder = namespace.GetDefaultFolder(6)
                acc_name = getattr(inbox_folder.Parent, "Name", "Principal")

            if inbox_folder:
                # Retornar la Bandeja de entrada misma y todas sus subcarpetas internas directas
                try:
                    root_count = inbox_folder.Items.Count
                except Exception:
                    root_count = 0

                subfolders.append({
                    "folder_path": f"{acc_name}/{inbox_folder.Name}",
                    "folder_name": f"[Raíz] {inbox_folder.Name}",
                    "count": root_count
                })

                # Solo subcarpetas hijas directas bajo 'Bandeja de entrada' (sin subcarpetas nietas)
                for child in inbox_folder.Folders:
                    try:
                        child_count = child.Items.Count
                    except Exception:
                        child_count = 0

                    subfolders.append({
                        "folder_path": f"{acc_name}/{inbox_folder.Name}/{child.Name}",
                        "folder_name": child.Name,
                        "count": child_count
                    })
        except Exception as e:
            logger.error(f"Error obteniendo subcarpetas de Bandeja de entrada para '{account_name}': {e}")
        finally:
            try: pythoncom.CoUninitialize()
            except Exception: pass

    t = threading.Thread(target=_inbox_worker, daemon=True)
    t.start()
    t.join(timeout=18.0)

    return subfolders

def get_real_outlook_subfolders(parent_folder_path: str):
    """
    Dada una carpeta seleccionada (ej. 'marco.vizcaino@sonda.com/Bandeja de entrada'),
    retorna ÚNICAMENTE sus subcarpetas hijas internas.
    """
    if not HAS_WIN32COM or not parent_folder_path:
        return []

    subfolders = []
    def _sub_worker():
        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
            target_folder = _find_folder_by_path(namespace, parent_folder_path)
            if target_folder:
                for sub in target_folder.Folders:
                    subfolders.append({
                        "folder_path": f"{parent_folder_path}/{sub.Name}",
                        "folder_name": sub.Name,
                        "count": sub.Items.Count
                    })
        except Exception as e:
            logger.error(f"Error obteniendo subcarpetas de '{parent_folder_path}': {e}")
        finally:
            try: pythoncom.CoUninitialize()
            except Exception: pass

    t = threading.Thread(target=_sub_worker, daemon=True)
    t.start()
    t.join(timeout=4.0)

    return subfolders

def _traverse_outlook_folder(folder_obj, current_path, result_list, depth=0, max_depth=3):
    if depth > max_depth:
        return
    try:
        count = folder_obj.Items.Count
        result_list.append({
            "folder_path": current_path,
            "folder_name": folder_obj.Name,
            "count": count
        })
        for subfolder in folder_obj.Folders:
            _traverse_outlook_folder(subfolder, f"{current_path}/{subfolder.Name}", result_list, depth + 1, max_depth)
    except Exception:
        pass

def _find_folder_by_path(namespace, full_path):
    """
    Navega exactamente por los segmentos de la ruta MAPI (ej. 'marco.vizcaino@sonda.com/Bandeja de entrada/synapse_org')
    evitando falsos positivos o saltos de carpetas intermedias.
    """
    try:
        parts = [p.strip() for p in full_path.split('/') if p.strip()]
        if not parts:
            return None
            
        current = None
        # Buscar cuenta raíz: primero coincidencia exacta, luego subcadena (excluyendo carpetas públicas)
        for acc in namespace.Folders:
            if acc.Name.strip().lower() == parts[0].lower():
                current = acc
                break
        if not current:
            for acc in namespace.Folders:
                if parts[0].lower() in acc.Name.lower() and not acc.Name.lower().startswith("public"):
                    current = acc
                    break

        if not current:
            # Buscar en default inbox si el primer segmento no fue la cuenta
            current = namespace.GetDefaultFolder(6)
            parts_to_match = parts
        else:
            parts_to_match = parts[1:]

        for part in parts_to_match:
            found = False
            for sub in current.Folders:
                if part.lower() == sub.Name.lower():
                    current = sub
                    found = True
                    break
            if not found:
                # Intentar búsqueda por subcadena como fallback
                for sub in current.Folders:
                    if part.lower() in sub.Name.lower():
                        current = sub
                        found = True
                        break
                if not found:
                    return None
        return current
    except Exception as e:
        logger.error(f"Error navegando ruta MAPI '{full_path}': {e}")
        return None

def get_real_outlook_emails(folder_path: str = None):
    """
    Retorna la lista de correos REALES directamente desde la carpeta MAPI de Outlook elegida.
    Solo retorna correos pertenecientes directamente a la carpeta especificada.
    """
    emails = []
    
    if HAS_WIN32COM:
        def _email_worker():
            try:
                pythoncom.CoInitialize()
                outlook = win32com.client.Dispatch("Outlook.Application")
                namespace = outlook.GetNamespace("MAPI")
                
                target_folder = None
                if folder_path:
                    target_folder = _find_folder_by_path(namespace, folder_path)

                if not target_folder:
                    target_folder = namespace.GetDefaultFolder(6)

                items = target_folder.Items
                items.Sort("[ReceivedTime]", True)
                
                count = 0
                for item in items:
                    try:
                        # Exigir que sea un MailItem directo (Class=43 o MessageClass='IPM.Note')
                        item_class = getattr(item, "Class", 0)
                        msg_class = getattr(item, "MessageClass", "")
                        if item_class != 43 and not msg_class.startswith("IPM.Note"):
                            continue

                        # Inspeccionar archivos adjuntos
                        has_attachments = False
                        att_names = []
                        try:
                            if hasattr(item, "Attachments") and item.Attachments.Count > 0:
                                has_attachments = True
                                for i in range(1, item.Attachments.Count + 1):
                                    att_names.append(item.Attachments.Item(i).FileName)
                        except Exception:
                            pass

                        # Calcular UnixTime del ReceivedTime
                        unixtime_stamp = int(datetime.now().timestamp())
                        try:
                            rt = getattr(item, "ReceivedTime", None)
                            if rt:
                                unixtime_stamp = int(datetime.strptime(str(rt)[:19], "%Y-%m-%d %H:%M:%S").timestamp())
                        except Exception:
                            pass

                        emails.append({
                            "id": count + 1,
                            "entry_id": getattr(item, "EntryID", ""),
                            "subject": getattr(item, "Subject", "(Sin Asunto)"),
                            "sender": getattr(item, "SenderEmailAddress", getattr(item, "SenderName", "Desconocido")),
                            "received_at": str(getattr(item, "ReceivedTime", datetime.now().strftime("%Y-%m-%d %H:%M"))),
                            "unixtime": unixtime_stamp,
                            "body": getattr(item, "Body", "")[:800] if hasattr(item, "Body") else "",
                            "folder": target_folder.Name,
                            "unread": getattr(item, "UnRead", False),
                            "has_attachments": has_attachments,
                            "attachment_names": att_names,
                            "status": "REAL_MAPI_ITEM"
                        })
                        count += 1
                        if count >= 100: break
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Error consultando correo MAPI para '{folder_path}': {e}")
            finally:
                try: pythoncom.CoUninitialize()
                except Exception: pass

        t = threading.Thread(target=_email_worker, daemon=True)
        t.start()
        t.join(timeout=10.0)

    # Si por alguna razón no devolvió correos MAPI y no está disponible win32com, consultar DB como simulación
    if not emails and not HAS_WIN32COM:
        from database.db_manager import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        if folder_path:
            cursor.execute("SELECT * FROM execution_logs WHERE folder_path LIKE ? OR email_subject LIKE ? ORDER BY received_at DESC LIMIT 20", (f"%{folder_path}%", f"%{folder_path}%"))
        else:
            cursor.execute("SELECT * FROM execution_logs ORDER BY received_at DESC LIMIT 20")
            
        rows = cursor.fetchall()
        conn.close()
        
        for r in rows:
            emails.append({
                "id": r["id"],
                "subject": r["email_subject"],
                "sender": r["email_sender"],
                "received_at": r["received_at"],
                "body": f"Correo real procesado por {r['script_name']}.",
                "folder": r["folder_path"],
                "status": r["execution_status"],
                "extracted_params": r["extracted_params"],
                "ai_payload_response": r["ai_payload_response"]
            })
            
    return emails
