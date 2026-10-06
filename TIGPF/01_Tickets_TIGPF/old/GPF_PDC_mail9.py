# --------------------------------------------------------------------------
# SCRIPT: ioc_ingestor_final_v10.py
# DESCRIPCIÓN: Lógica robusta para rastreo de 4 correos diarios, diferenciando
#               correctamente entre OK, OUTTIME, SIN CORREO y PRUEBA.
#               MODIFICADO para que el estado PRUEBA también genere tickets.
# --------------------------------------------------------------------------

# PASO 1: CONFIGURACIÓN Y LIBRERÍAS
import os
import mysql.connector
import win32com.client
import pandas as pd
from datetime import datetime, time, timedelta, date
from tqdm import tqdm
import time as time_sleep
import requests
import json
from bs4 import BeautifulSoup
import schedule

# --- Configuración de la Base de Datos ---
DB_HOST = "172.32.1.51"
DB_USER = "zabbixuser"
DB_PASSWORD = "zabbix"
DB_NAME = "your_database_name"
DB_ARCHIVOS_TABLE = "GPF_00_Archivos_Procesados"
DB_DATA_TABLE = "GPF_00_Planesdecredito"

# --- Configuración de Outlook ---
OUTLOOK_MAILBOX = "monitoreosistemas@corporaciongpf.com"
SOURCE_FOLDER_PATH = ["Monitoreo Planes de Credito"]
PROCESSED_FOLDER_NAME = "PDC Procesados"

# --- Configuración de Archivos Adjuntos y Filtros ---
REQUIRED_SUBJECT = "Monitoreo Planes de Credito"
REQUIRED_SENDER = "soporteprdn3@corporaciongpf.com"
ATTACHMENT_NAME_PREFIX = "MONITOREOPLANESCREDITO"
NEW_ATTACHMENT_PREFIX = "MonitoreoPDC_"
IOC_FOLDER_NAME = "ioc"

# --- Configuración de MantisBT ---
MANTIS_URL = "http://172.32.1.51:10090/api/rest/issues"
MANTIS_AUTH_TOKEN = "B6knU4vQYh9bSx-ukxmlcS9PgqcqOLTy"
MANTIS_PROJECT_ID = 39
MANTIS_CATEGORY = "General"
MANTIS_PRIORITY = "alta"

# --- CONFIGURACIÓN DE HORARIOS DE ANÁLISIS DIARIO ---
# Se usa solo la hora de inicio como identificador único de la ventana
HORARIOS_ESPERADOS = {
    time(8, 0): (time(8, 0), time(8, 10)),
    time(12, 0): (time(12, 0), time(12, 10)),
    time(16, 0): (time(16, 0), time(16, 10)),
    time(20, 0): (time(20, 0), time(20, 10)),
}

# --- RASTREADOR DE CORREOS RECIBIDOS EN EL DÍA ---
PROCESSED_WINDOWS_TODAY = set()

# PASO 2: FUNCIONES DE BASE DE DATOS
def conectar_base_datos():
    """Establece conexión a la base de datos MySQL."""
    print("📋 [LOG] Intentando conectar a la base de datos...")
    try:
        connection = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        print("✅ [LOG] Conexión a la base de datos exitosa.")
        return connection
    except mysql.connector.Error as err:
        print(f"❌ [LOG] Error al conectar a la base de datos: {err}")
        return None

def almacenar_metadatos_archivo(db_connection, unique_id, email_subject, email_sender,
                                  nombre_archivo_resultante, fecha_recepcion, estado_analisis):
    """Almacena los metadatos del archivo en la nueva tabla."""
    if not db_connection: return
    cursor = db_connection.cursor()
    query = f"""
    INSERT IGNORE INTO {DB_ARCHIVOS_TABLE}
    (id_unico, asunto_correo, remitente_correo, nombre_archivo_resultante, fecha_recepcion, estado_analisis, fecha_creacion_registro)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    try:
        cursor.execute(query, (
            unique_id,
            email_subject,
            email_sender,
            nombre_archivo_resultante,
            fecha_recepcion,
            estado_analisis,
            datetime.now()
        ))
        db_connection.commit()
        if cursor.rowcount > 0:
            print(f"📦 [LOG] Metadatos del archivo almacenados. ID Único: '{unique_id}'.")
        else:
            print(f"⚠️ [LOG] Metadatos para ID '{unique_id}' ya existen. Ignorando inserción.")
    except mysql.connector.Error as err:
        print(f"❌ [LOG] ERROR SQL al insertar metadatos: {err}")
        db_connection.rollback()
    finally:
        cursor.close()

def almacenar_datos_del_archivo(db_connection, data_df, id_archivo):
    """Almacena el DataFrame de datos en la tabla principal."""
    if not db_connection or data_df.empty: return 0
    cursor = db_connection.cursor()

    cols = ", ".join([f"`{col}`" for col in data_df.columns])
    insert_cols = f"`id_archivo`, {cols}"
    placeholders = ", ".join(["%s"] * (len(data_df.columns) + 1))

    query = f"INSERT INTO {DB_DATA_TABLE} ({insert_cols}) VALUES ({placeholders})"
    count = 0

    try:
        rows_to_insert = [
            (id_archivo,) + tuple(row)
            for row in data_df.itertuples(index=False, name=None)
        ]

        cursor.executemany(query, rows_to_insert)
        db_connection.commit()
        count = cursor.rowcount
        cursor.close()

        print(f"📦 [LOG] ÉXITO: Se almacenaron {count} nuevos registros de datos.")
    except mysql.connector.Error as err:
        print(f"❌ [LOG] ERROR SQL al insertar datos: {err}")
        db_connection.rollback()
        return 0
    return count

def actualizar_id_mantis(db_connection, unique_id, mantis_id):
    """Actualiza el ID del ticket de Mantis en la tabla de metadatos."""
    print(f"📋 [LOG] Intentando actualizar el ID de Mantis '{mantis_id}' para el ID único '{unique_id}'.")
    if not db_connection: return
    cursor = db_connection.cursor()
    query = f"UPDATE {DB_ARCHIVOS_TABLE} SET id_mantis = %s WHERE id_unico = %s"
    try:
        cursor.execute(query, (mantis_id, unique_id))
        db_connection.commit()
        print(f"✅ [LOG] Se actualizó el ID de Mantis '{mantis_id}' para el ID único '{unique_id}'.")
    except mysql.connector.Error as err:
        print(f"❌ [LOG] ERROR SQL al actualizar ID de Mantis: {err}")
        db_connection.rollback()
    finally:
        cursor.close()
    print("✅ [LOG] Actualización de ID de Mantis finalizada.")

# --------------------------------------------------------------------------
# PASO 3: FUNCIONES DE PROCESAMIENTO Y MANEJO DE MANTIS
# --------------------------------------------------------------------------
def procesar_adjunto_csv(attachment, ioc_folder_path, reception_date):
    """Procesa el adjunto, lo renombra usando la fecha de recepción y extrae la data."""
    print(f"📋 [LOG] Iniciando procesamiento de adjunto '{attachment.FileName}'.")
    if not attachment.FileName.lower().startswith(ATTACHMENT_NAME_PREFIX.lower()):
        print(f"⚠️ [LOG] Ignorando adjunto: El nombre no empieza con '{ATTACHMENT_NAME_PREFIX}'.")
        return None, None

    timestamp = reception_date.strftime('%Y%m%d%H%M%S')
    new_file_name = f"{NEW_ATTACHMENT_PREFIX}{timestamp}.csv"
    save_path = os.path.join(ioc_folder_path, new_file_name)

    try:
        attachment.SaveAsFile(save_path)
        print(f"✅ [LOG] Adjunto guardado en '{save_path}'.")
        df = pd.read_csv(save_path, sep=';')

        if df.empty:
            print("  [LOG] INFO: El archivo está vacío (solo encabezado). No se procesarán datos.")
            return None, save_path

        print("✅ [LOG] Datos extraídos del archivo correctamente.")
        return df, save_path
    except Exception as e:
        print(f"❌ [LOG] Error al leer el archivo CSV '{new_file_name}': {e}")
        return None, save_path

def get_operador():
    """Obtener el operador desde un servicio externo."""
    print("📋 [LOG] Intentando obtener el operador de turno...")
    url = "http://172.32.1.55:3001/turnos/actual-correo"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            operador = response.text.strip()
            print(f"✅ [LOG] Operador de turno obtenido: '{operador}'.")
            return operador
        print(f"❌ [LOG] Error al obtener operador, código de estado: {response.status_code}")
    except requests.RequestException as e:
        print(f"❌ [LOG] Error de conexión al obtener operador: {e}")
    print("⚠️ [LOG] Usando operador por defecto.")
    return "oscar.guerra@sonda.com"

def create_mantis_ticket(email, unique_id):
    """Crear un ticket en MantisBT, convirtiendo la tabla HTML del correo a BBCode."""
    print(f"📋 [LOG] Intentando crear ticket en MantisBT para ID único: '{unique_id}'.")

    html_body = email.HTMLBody
    soup = BeautifulSoup(html_body, 'html.parser')

    table_html = soup.find('table')

    if table_html:
        print("✅ [LOG] Tabla HTML encontrada. Convirtiendo a formato BBCode.")
        bbcode_table_parts = ['[table]']
        for row in table_html.find_all('tr'):
            cells = [cell.get_text(strip=True) for cell in row.find_all(['th', 'td'])]
            bbcode_row = '[tr]' + ''.join(f'[td]{text}[/td]' for text in cells) + '[/tr]'
            bbcode_table_parts.append(bbcode_row)

        bbcode_table_parts.append('[/table]')
        bbcode_table_str = '\n'.join(bbcode_table_parts)
        table_html.replace_with(bbcode_table_str)
        final_description = soup.get_text(separator='\n').strip()

    else:
        print("⚠️ [LOG] No se encontró tabla HTML. Usando el cuerpo del correo en texto plano.")
        final_description = email.Body

    operador = get_operador()
    payload = {
        "summary": f"Reporte de Planes de Crédito: ID:{unique_id} -> {email.Subject}",
        "description": final_description,
        "project": {"id": MANTIS_PROJECT_ID},
        "handler": {"name": operador},
        "category": MANTIS_CATEGORY,
        "priority": {"name": MANTIS_PRIORITY},
        "custom_fields": [{"field": {"id": 2, "name": "id_unique"}, "value": unique_id}],
    }
    headers = {"Content-Type": "application/json", "Authorization": MANTIS_AUTH_TOKEN}
    try:
        response = requests.post(MANTIS_URL, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        issue_id = response.json().get('issue', {}).get('id')
        if issue_id:
            print(f"✅ [LOG] Ticket de Mantis creado con el ID: '{issue_id}'.")
            return issue_id
        else:
            print(f"❌ [LOG] No se pudo obtener el ID del ticket. Respuesta: {response.text}")
            return None
    except requests.RequestException as e:
        print(f"❌ [LOG] Error de la API de MantisBT: {e}")
        return None

def create_mantis_ticket_for_missing_mail(unique_id, subject, description):
    """Crear un ticket en MantisBT para un correo no recibido."""
    print(f"📋 [LOG] Intentando crear ticket en MantisBT para correo no recibido. ID: '{unique_id}'.")
    operador = get_operador()
    payload = {
        "summary": subject, "description": description, "project": {"id": MANTIS_PROJECT_ID},
        "handler": {"name": operador}, "category": MANTIS_CATEGORY, "priority": {"name": MANTIS_PRIORITY},
        "custom_fields": [{"field": {"id": 2, "name": "id_unique"}, "value": unique_id}],
    }
    headers = {"Content-Type": "application/json", "Authorization": MANTIS_AUTH_TOKEN}
    try:
        response = requests.post(MANTIS_URL, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        issue_id = response.json().get('issue', {}).get('id')
        if issue_id:
            print(f"✅ [LOG] Ticket de Mantis para correo faltante creado con el ID: '{issue_id}'.")
            return issue_id
        else:
            print(f"❌ [LOG] No se pudo obtener el ID del ticket. Respuesta: {response.text}")
            return None
    except requests.RequestException as e:
        print(f"❌ [LOG] Error de la API de MantisBT: {e}")
        return None

# --------------------------------------------------------------------------
# PASO 4: LÓGICA PRINCIPAL Y PROCESAMIENTO DE CORREOS
# --------------------------------------------------------------------------

def get_corresponding_window(received_time):
    """
    Determina a qué ventana de monitoreo pertenece un correo, incluso si llegó tarde.
    """
    received_time_obj = received_time.time()
    window_starts = sorted(HORARIOS_ESPERADOS.keys(), reverse=True)

    for start_time in window_starts:
        if received_time_obj >= start_time:
            return start_time
    return window_starts[-1]

def procesar_correos_outlook(cantidad_a_leer):
    """Procesar los correos de Outlook con la nueva lógica de estados."""
    print("\n📋 [LOG] Iniciando ciclo de procesamiento de correos de Outlook.")
    db_connection = conectar_base_datos()
    if not db_connection: return

    ioc_folder_path = os.path.join(os.getcwd(), IOC_FOLDER_NAME)
    os.makedirs(ioc_folder_path, exist_ok=True)

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        source_folder = namespace.Folders.Item(OUTLOOK_MAILBOX)
        for folder_name in SOURCE_FOLDER_PATH:
            source_folder = source_folder.Folders.Item(folder_name)
        
        try:
            processed_folder = source_folder.Folders.Item(PROCESSED_FOLDER_NAME)
        except Exception:
            processed_folder = source_folder.Folders.Add(PROCESSED_FOLDER_NAME)

        items = source_folder.Items
        items.Sort("[ReceivedTime]", True)
        num_a_procesar = min(cantidad_a_leer, items.Count)
        if num_a_procesar == 0:
            print("⚠️ [LOG] No hay correos para procesar.")
            if db_connection and db_connection.is_connected(): db_connection.close()
            return
        
        print(f"📬 [LOG] Analizando los {num_a_procesar} correos más recientes.")
        correos_a_procesar = [items.Item(i + 1) for i in range(num_a_procesar)]

        for email in tqdm(correos_a_procesar, desc="Procesando correos", unit="correo"):
            if not (email.Subject == REQUIRED_SUBJECT and 
                    email.SenderEmailAddress.lower() == REQUIRED_SENDER.lower() and 
                    email.Attachments.Count == 1):
                continue

            received_time = email.ReceivedTime.replace(tzinfo=None)
            unique_id = int(received_time.timestamp())
            
            print(f"\n--- Procesando correo de las {received_time} (ID: {unique_id}) ---")

            estado = None
            
            if received_time.date() < date.today():
                estado = "PRUEBA"
                print(f"  [LOG] La fecha del correo ({received_time.date()}) es anterior a hoy. Estado: {estado}")
            else:
                window_start = get_corresponding_window(received_time)
                ventana_inicio, ventana_fin = HORARIOS_ESPERADOS[window_start]
                
                if ventana_inicio <= received_time.time() <= ventana_fin:
                    estado = "OK"
                    print(f"  [LOG] Correo recibido a las {received_time.time()} DENTRO del horario {ventana_inicio}-{ventana_fin}. Estado: {estado}")
                else:
                    estado = "OUTTIME"
                    print(f"  [LOG] Correo recibido a las {received_time.time()} FUERA del horario {ventana_inicio}-{ventana_fin}. Estado: {estado}")
                
                print(f"  [LOG] Registrando ventana de las {window_start} como completada para hoy.")
                PROCESSED_WINDOWS_TODAY.add(window_start)

            attachment = email.Attachments.Item(1)
            data_df, temp_path = procesar_adjunto_csv(attachment, ioc_folder_path, received_time)
            nombre_archivo_resultante = os.path.basename(temp_path) if temp_path else None

            almacenar_metadatos_archivo(db_connection, unique_id, email.Subject, email.SenderEmailAddress,
                                        nombre_archivo_resultante, received_time, estado)
            
            # ##########################################################################
            # ############ CAMBIO: AHORA PRUEBA TAMBIÉN PROCESA Y GENERA TICKET #########
            # ##########################################################################
            if estado in ["OK", "OUTTIME", "PRUEBA"]:
                if data_df is not None and not data_df.empty:
                    num_inserted = almacenar_datos_del_archivo(db_connection, data_df, unique_id)
                    # Siempre crear ticket si el estado lo permite y hay datos
                    if num_inserted > 0:
                        mantis_id = create_mantis_ticket(email, unique_id)
                        if mantis_id:
                            actualizar_id_mantis(db_connection, unique_id, mantis_id)
                else:
                    # Aunque el adjunto esté vacío, si es PRUEBA, se crea ticket.
                    if estado == "PRUEBA":
                         mantis_id = create_mantis_ticket(email, unique_id)
                         if mantis_id:
                             actualizar_id_mantis(db_connection, unique_id, mantis_id)
                    else:
                        print("  [LOG] El correo estaba en un horario de producción, pero el archivo adjunto estaba vacío.")

            try:
                email.Move(processed_folder)
            except Exception as e:
                print(f"❌ [LOG] ERROR al mover el correo: {e}.")
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    print(f"❌ [LOG] ERROR al eliminar archivo temporal: {e}.")

    except Exception as e:
        print(f"❌ [LOG] Error general al procesar Outlook: {e}")
    finally:
        if db_connection and db_connection.is_connected():
            db_connection.close()
            print("🔌 [LOG] Conexión a la base de datos cerrada.")

def manejar_correo_faltante(window_start, horario_str):
    """Función que se ejecuta para verificar si un correo no llegó."""
    print(f"\n🚨 [ALERTA] Verificando si se recibió el correo para la ventana de {horario_str}.")

    if window_start in PROCESSED_WINDOWS_TODAY:
        print(f"  [LOG] Verificación completa. El correo para la ventana de las {window_start} ya fue procesado hoy.")
        return

    print(f"  [LOG] ¡FALTA CORREO! No se ha recibido el correo de las {window_start}. Se creará registro y ticket.")
    
    db_connection = conectar_base_datos()
    if not db_connection: return

    now = datetime.now()
    unique_id = int(now.timestamp())
    subject = f"SIN CORREO: Monitoreo Planes de Credito a tiempo {horario_str}"
    description = f"No se recibió el correo de Monitoreo de Planes de Crédito que debía haber llegado en el horario de {horario_str}."

    almacenar_metadatos_archivo(db_connection, unique_id, subject, "", "", now, "SIN CORREO")
    
    mantis_id = create_mantis_ticket_for_missing_mail(unique_id, subject, description)
    if mantis_id:
        actualizar_id_mantis(db_connection, unique_id, mantis_id)

    if db_connection and db_connection.is_connected():
        db_connection.close()
        print("🔌 [LOG] Conexión a la base de datos cerrada.")

def reset_daily_tracker():
    """Reinicia el rastreador de ventanas para el nuevo día."""
    global PROCESSED_WINDOWS_TODAY
    PROCESSED_WINDOWS_TODAY.clear()
    print(f"\n🌅 [LOG] Es un nuevo día ({date.today()}). Reiniciando el rastreador de correos diarios.")

# PASO 5: EJECUCIÓN PRINCIPAL
if __name__ == "__main__":
    print(f"--- Iniciando Script de Monitoreo de Planes de Credito ---")
    print(f"Hora de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    schedule.every(15).minutes.do(procesar_correos_outlook, cantidad_a_leer=100)
    
    schedule.every().day.at("00:01").do(reset_daily_tracker)

    schedule.every().day.at("08:11").do(manejar_correo_faltante, window_start=time(8, 0), horario_str="de 8:00 a 8:10")
    schedule.every().day.at("12:11").do(manejar_correo_faltante, window_start=time(12, 0), horario_str="de 12:00 a 12:10")
    schedule.every().day.at("16:11").do(manejar_correo_faltante, window_start=time(16, 0), horario_str="de 16:00 a 16:10")
    schedule.every().day.at("20:11").do(manejar_correo_faltante, window_start=time(20, 0), horario_str="de 20:00 a 20:10")
    
    print("✅ [LOG] Tareas programadas. El script se ejecutará en un bucle infinito.")
    print("Presiona Ctrl+C para detener el script.")

    procesar_correos_outlook(100)

    while True:
        schedule.run_pending()
        time_sleep.sleep(1)