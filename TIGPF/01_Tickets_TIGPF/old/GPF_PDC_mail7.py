# --------------------------------------------------------------------------
# SCRIPT: ioc_ingestor_final_v6.py
# DESCRIPCIÓN: Versión con modelo relacional y nombres de tabla actualizados.
#               MODIFICADO para convertir tabla HTML a BBCode para MantisBT.
#               MODIFICADO para incluir análisis de tiempo de llegada de correos.
# --------------------------------------------------------------------------

# PASO 1: CONFIGURACIÓN Y LIBRERÍAS
import os
import mysql.connector
import win32com.client
import pandas as pd
from datetime import datetime, time, timedelta
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

# --- NUEVA CONFIGURACIÓN DE HORARIOS ---
HORARIOS_ESPERADOS = [
    (time(8, 0), time(8, 10)),
    (time(12, 0), time(12, 10)),
    (time(16, 0), time(16, 10)),
    (time(20, 0), time(20, 10)),
]

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

def verificar_correo_recibido(db_connection, inicio, fin):
    """Verifica si un correo fue recibido en la ventana de tiempo especificada."""
    if not db_connection: return True # Asumir que sí para no generar falsos positivos
    cursor = db_connection.cursor()
    query = f"""
    SELECT COUNT(*) FROM {DB_ARCHIVOS_TABLE}
    WHERE fecha_recepcion BETWEEN %s AND %s
    """
    try:
        cursor.execute(query, (inicio, fin))
        count = cursor.fetchone()[0]
        return count > 0
    except mysql.connector.Error as err:
        print(f"❌ [LOG] ERROR SQL al verificar correos: {err}")
        return True # Asumir que sí para no generar falsos positivos
    finally:
        cursor.close()
        
# --------------------------------------------------------------------------
# PASO 3: FUNCIONES DE PROCESAMIENTO Y MANEJO DE MANTIS
# --------------------------------------------------------------------------
def procesar_adjunto_csv(attachment, ioc_folder_path):
    """Procesa el adjunto, lo renombra y extrae la data."""
    print(f"📋 [LOG] Iniciando procesamiento de adjunto '{attachment.FileName}'.")
    if not attachment.FileName.lower().startswith(ATTACHMENT_NAME_PREFIX.lower()):
        print(f"⚠️ [LOG] Ignorando adjunto: El nombre no empieza con '{ATTACHMENT_NAME_PREFIX}'.")
        return None, None

    timestamp = datetime.now().strftime('%Y%m%d%H%M')
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
        "custom_fields": [
            {"field": {"id": 2, "name": "id_unique"}, "value": unique_id},
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": MANTIS_AUTH_TOKEN,
    }

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

# --- NUEVA FUNCIÓN PARA TICKET DE CORREO FALTANTE ---
def create_mantis_ticket_for_missing_mail(unique_id, subject, description):
    """Crear un ticket en MantisBT para un correo no recibido."""
    print(f"📋 [LOG] Intentando crear ticket en MantisBT para correo no recibido. ID: '{unique_id}'.")
    
    operador = get_operador()
    
    payload = {
        "summary": subject,
        "description": description,
        "project": {"id": MANTIS_PROJECT_ID},
        "handler": {"name": operador},
        "category": MANTIS_CATEGORY,
        "priority": {"name": MANTIS_PRIORITY},
        "custom_fields": [
            {"field": {"id": 2, "name": "id_unique"}, "value": unique_id},
        ],
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": MANTIS_AUTH_TOKEN,
    }
    
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
# PASO 4: PROCESAMIENTO DE CORREOS EN OUTLOOK
# --------------------------------------------------------------------------
def procesar_correos_outlook(cantidad_a_leer):
    """Procesar los correos de Outlook."""
    print("📋 [LOG] Iniciando procesamiento de correos de Outlook.")
    db_connection = conectar_base_datos()
    if not db_connection:
        return

    ioc_folder_path = os.path.join(os.getcwd(), IOC_FOLDER_NAME)
    if not os.path.exists(ioc_folder_path):
        os.makedirs(ioc_folder_path)
        print(f"✅ [LOG] Carpeta de IOCs creada: '{ioc_folder_path}'.")

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")

        source_folder = namespace.Folders.Item(OUTLOOK_MAILBOX)
        for folder_name in SOURCE_FOLDER_PATH:
            source_folder = source_folder.Folders.Item(folder_name)

        print(f"✅ [LOG] Carpeta de origen '{source_folder.Name}' encontrada.")

        try:
            processed_folder = source_folder.Folders.Item(PROCESSED_FOLDER_NAME)
        except Exception:
            print(f"  [LOG] INFO: Creando carpeta de destino '{PROCESSED_FOLDER_NAME}'...")
            processed_folder = source_folder.Folders.Add(PROCESSED_FOLDER_NAME)

        items = source_folder.Items
        items.Sort("[ReceivedTime]", True)
        num_a_procesar = min(cantidad_a_leer, items.Count)
        print(f"📬 [LOG] Analizando los {num_a_procesar} correos más recientes.")
        if num_a_procesar == 0:
            print("⚠️ [LOG] No hay correos para procesar.")
            return

        correos_a_procesar = [items.Item(i + 1) for i in range(num_a_procesar)]

        for email in tqdm(correos_a_procesar, desc="Procesando correos", unit="correo"):
            print(f"\n--- Procesando correo '{email.Subject}' del remitente '{email.SenderEmailAddress}' ---")
            if email.Subject != REQUIRED_SUBJECT:
                print(f"❌ [LOG] Correo ignorado: Asunto incorrecto.")
                continue
            if email.SenderEmailAddress.lower() != REQUIRED_SENDER.lower():
                print(f"❌ [LOG] Correo ignorado: Remitente incorrecto.")
                continue
            if email.Attachments.Count != 1:
                print(f"❌ [LOG] Correo ignorado: Cantidad de adjuntos incorrecta. Se encontraron {email.Attachments.Count}.")
                continue

            received_time = email.ReceivedTime.replace(tzinfo=None)
            unique_id = int(received_time.timestamp())

            print(f"✅ [LOG] Correo validado. ID Único: {unique_id}.")

            attachment = email.Attachments.Item(1)
            data_df, temp_path = procesar_adjunto_csv(attachment, ioc_folder_path)

            estado = "VACIO" if data_df is None or data_df.empty else "ERROR"
            
            # --- NUEVA LÓGICA DE ESTADO DE ANÁLISIS ---
            if estado == "ERROR":
                correo_a_tiempo = False
                for inicio, fin in HORARIOS_ESPERADOS:
                    if inicio <= received_time.time() <= fin:
                        correo_a_tiempo = True
                        break
                if not correo_a_tiempo:
                    estado = "OUTTIME"

            nombre_archivo_resultante = os.path.basename(temp_path) if temp_path else None

            almacenar_metadatos_archivo(db_connection, unique_id, email.Subject, email.SenderEmailAddress,
                                        nombre_archivo_resultante, received_time, estado)

            if estado == "ERROR" or estado == "OUTTIME":
                num_inserted = almacenar_datos_del_archivo(db_connection, data_df, unique_id)

                if num_inserted > 0:
                    mantis_id = create_mantis_ticket(email, unique_id)
                    if mantis_id:
                        actualizar_id_mantis(db_connection, unique_id, mantis_id)

                print(f"📋 [LOG] Intentando mover el correo a la carpeta '{processed_folder.Name}'...")
                try:
                    email.Move(processed_folder)
                    print(f"✅ [LOG] Correo movido exitosamente.")
                except Exception as e:
                    print(f"❌ [LOG] ERROR al mover el correo: {e}. El correo permanecerá en la carpeta de origen.")

            if temp_path and os.path.exists(temp_path):
                print(f"📋 [LOG] Intentando eliminar el archivo temporal '{os.path.basename(temp_path)}'.")
                try:
                    os.remove(temp_path)
                    print(f"✅ [LOG] Archivo temporal eliminado.")
                except Exception as e:
                    print(f"❌ [LOG] ERROR al eliminar archivo temporal: {e}.")

    except Exception as e:
        print(f"❌ [LOG] Error general al procesar Outlook: {e}")
    finally:
        if db_connection and db_connection.is_connected():
            db_connection.close()
            print("🔌 [LOG] Conexión a la base de datos cerrada.")

# --- NUEVA FUNCIÓN PARA MANEJAR CORREOS FALTANTES ---
def manejar_correo_faltante(horario_str):
    """Función que se ejecuta cuando no llega un correo a tiempo."""
    print(f"🚨 [ALERTA] No se ha recibido el correo esperado en el horario de {horario_str}.")
    
    db_connection = conectar_base_datos()
    if not db_connection:
        return

    # Verificar si el correo llegó tarde pero antes de esta verificación
    now = datetime.now()
    inicio_ventana = datetime.combine(now.date(), time(int(horario_str.split(':')[0]), int(horario_str.split(':')[1].split(' ')[0])))
    fin_ventana = inicio_ventana + timedelta(minutes=10)

    if verificar_correo_recibido(db_connection, inicio_ventana, now):
        print(f"  [LOG] INFO: Se encontró un correo para el horario {horario_str} que llegó tarde. No se creará ticket de 'SIN CORREO'.")
        db_connection.close()
        return

    unique_id = int(now.timestamp())
    subject = f"No llegada de Correo Monitoreo Planes de Credito a tiempo {horario_str}"
    description = f"No se recibió el correo de Monitoreo de Planes de Crédito que debía haber llegado en el horario de {horario_str}."
    
    almacenar_metadatos_archivo(db_connection, unique_id, subject, "", "", now, "SIN CORREO")
    
    mantis_id = create_mantis_ticket_for_missing_mail(unique_id, subject, description)
    if mantis_id:
        actualizar_id_mantis(db_connection, unique_id, mantis_id)

    if db_connection and db_connection.is_connected():
        db_connection.close()
        print("🔌 [LOG] Conexión a la base de datos cerrada.")

# PASO 5: EJECUCIÓN PRINCIPAL
if __name__ == "__main__":
    print(f"--- Iniciando Script de Monitoreo de Planes de Credito ---")
    print(f"Hora de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # --- NUEVA LÓGICA DE EJECUCIÓN CON SCHEDULE ---
    
    # Programar la revisión de correos cada 15 minutos
    schedule.every(15).minutes.do(procesar_correos_outlook, cantidad_a_leer=100)
    
    # Programar las alertas de correos no recibidos
    schedule.every().day.at("08:11").do(manejar_correo_faltante, horario_str="de 8:00 a 8:10")
    schedule.every().day.at("12:11").do(manejar_correo_faltante, horario_str="de 12:00 a 12:10")
    schedule.every().day.at("16:11").do(manejar_correo_faltante, horario_str="de 16:00 a 16:10")
    schedule.every().day.at("20:11").do(manejar_correo_faltante, horario_str="de 20:00 a 20:10")
    
    print("✅ [LOG] Tareas programadas. El script se ejecutará en un bucle infinito.")
    print("Presiona Ctrl+C para detener el script.")

    # Ejecutar la primera vez al iniciar
    procesar_correos_outlook(100)

    while True:
        schedule.run_pending()
        time_sleep.sleep(1)