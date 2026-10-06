# --------------------------------------------------------------------------
# SCRIPT: ioc_ingestor_final_v5.py
# DESCRIPCIÓN: Versión final con integración de la API REST de MantisBT
#              para la creación y gestión de tickets, basada en el
#              código de muestra.
# --------------------------------------------------------------------------

# PASO 1: CONFIGURACIÓN Y LIBRERÍAS
import os
import mysql.connector
import win32com.client
import pandas as pd
from datetime import datetime
from tqdm import tqdm
import time
import requests # Nuevo
import json # Nuevo

# --- Configuración de la Base de Datos ---
DB_HOST = "172.32.1.51"
DB_USER = "zabbixuser"
DB_PASSWORD = "zabbix"
DB_NAME = "your_database_name"
DB_TABLE = "GPF_00_Planesdecredito"

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
MANTIS_AUTH_TOKEN = "B6knU4vQYh9bSx-ukxmlcS9PgqcO" # Token de ejemplo, reemplazar.
MANTIS_PROJECT_ID = 39
MANTIS_CATEGORY = "General"
MANTIS_PRIORITY = "alta"

# PASO 2: FUNCIONES DE BASE DE DATOS
def conectar_base_datos():
    """Establece conexión a la base de datos MySQL."""
    try:
        connection = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        print("✅ Conexión a la base de datos exitosa.")
        return connection
    except mysql.connector.Error as err:
        print(f"❌ Error al conectar a la base de datos: {err}")
        return None

def almacenar_datos(db_connection, data_df, unique_id, received_date, source_file):
    """Almacena un DataFrame de datos en la BD."""
    if not db_connection or data_df.empty:
        return 0
    cursor = db_connection.cursor()
    
    cols = ", ".join([f"`{col}`" for col in data_df.columns])
    insert_cols = f"`id_unico`, `fecha_creacion`, `fecha_recepcion`, {cols}"
    placeholders = ", ".join(["%s"] * (len(data_df.columns) + 3))
    
    query = f"INSERT IGNORE INTO {DB_TABLE} ({insert_cols}) VALUES ({placeholders})"
    count = 0
    now = datetime.now()
    
    try:
        rows_to_insert = [
            (unique_id, now, received_date) + tuple(row)
            for row in data_df.itertuples(index=False, name=None)
        ]
        
        cursor.executemany(query, rows_to_insert)
        db_connection.commit()
        count = cursor.rowcount
        cursor.close()
        
        if count > 0:
            print(f"📦 ÉXITO: Se almacenaron {count} nuevos registros del archivo '{source_file}'.")
        else:
            print(f"  [INFO] No se añadieron nuevos registros de '{source_file}'.")
    except mysql.connector.Error as err:
        print(f"❌ ERROR SQL al insertar datos de '{source_file}': {err}")
        db_connection.rollback()
        return 0
    return count

def actualizar_id_mantis(db_connection, unique_id, mantis_id):
    """Actualiza el ID del ticket de Mantis en la BD."""
    if not db_connection: return
    cursor = db_connection.cursor()
    query = f"UPDATE {DB_TABLE} SET id_mantis = %s WHERE id_unico = %s"
    try:
        cursor.execute(query, (mantis_id, unique_id))
        db_connection.commit()
        print(f"✅ Se actualizó el ID de Mantis '{mantis_id}' para el ID único '{unique_id}'.")
    except mysql.connector.Error as err:
        print(f"❌ ERROR SQL al actualizar ID de Mantis: {err}")
        db_connection.rollback()
    finally:
        cursor.close()

# --------------------------------------------------------------------------
# PASO 3: FUNCIONES DE PROCESAMIENTO Y MANEJO DE MANTIS
# --------------------------------------------------------------------------
def procesar_adjunto_csv(attachment, ioc_folder_path):
    """
    Procesa el adjunto, lo renombra y extrae la data asumiendo formato CSV.
    Retorna el DataFrame con los datos si la validación es exitosa.
    """
    if not attachment.FileName.lower().startswith(ATTACHMENT_NAME_PREFIX.lower()):
        print(f"⚠️ Nombre de adjunto incorrecto: '{attachment.FileName}'. Ignorando.")
        return None, None
    
    timestamp = datetime.now().strftime('%Y%m%d%H%M')
    new_file_name = f"{NEW_ATTACHMENT_PREFIX}{timestamp}.csv"
    save_path = os.path.join(ioc_folder_path, new_file_name)
    attachment.SaveAsFile(save_path)
    print(f"📄 Adjunto guardado como '{new_file_name}'.")

    try:
        # Leer el archivo CSV con delimitador de punto y coma
        df = pd.read_csv(save_path, sep=';')
        
        if df.empty:
            print("  [INFO] El archivo está vacío (solo encabezado). No se crearán registros ni tickets.")
            return None, save_path
        
        return df, save_path
    except Exception as e:
        print(f"❌ Error al leer el archivo CSV '{new_file_name}': {e}")
        return None, save_path
    
def get_operador():
    """Obtener el operador desde un servicio externo (función del código de muestra)."""
    url = "http://172.32.1.55:3001/turnos/actual-correo"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.text.strip()
        print(f"Error al obtener operador: {response.status_code}")
    except requests.RequestException as e:
        print(f"Error al obtener operador: {e}")
    return "oscar.guerra@sonda.com"

def create_mantis_ticket(email_subject, email_body, unique_id):
    """Crear un ticket en MantisBT usando la API REST."""
    operador = get_operador()
    
    payload = {
        "summary": f"Reporte de Planes de Crédito: ID:{unique_id} -> {email_subject}",
        "description": email_body,
        "project": {"id": MANTIS_PROJECT_ID},
        "handler": {"name": operador},
        "category": MANTIS_CATEGORY,
        "priority": {"name": MANTIS_PRIORITY},
        # Los campos personalizados deben ser adaptados a tu MantisBT.
        # Los siguientes campos son de EJEMPLO.
        "custom_fields": [
            {"field": {"id": 2, "name": "id_unique"}, "value": unique_id},
        ],
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": MANTIS_AUTH_TOKEN,
    }
    
    try:
        print(f"📨 Creando ticket en Mantis con el asunto: '{payload['summary']}'...")
        response = requests.post(MANTIS_URL, data=json.dumps(payload), headers=headers)
        response.raise_for_status() # Lanza un error para códigos de estado 4xx/5xx
        
        issue_id = response.json().get('issue', {}).get('id')
        if issue_id:
            print(f"✅ Ticket de Mantis creado con el ID: '{issue_id}'.")
            return issue_id
        else:
            print("❌ No se pudo obtener el ID del ticket de la respuesta.")
            return None
    except requests.RequestException as e:
        print(f"❌ Error al crear ticket en MantisBT: {e}")
        return None

# --------------------------------------------------------------------------
# PASO 4: PROCESAMIENTO DE CORREOS EN OUTLOOK
# --------------------------------------------------------------------------
def procesar_correos_outlook(cantidad_a_leer):
    db_connection = conectar_base_datos()
    if not db_connection: return

    ioc_folder_path = os.path.join(os.getcwd(), IOC_FOLDER_NAME)
    if not os.path.exists(ioc_folder_path):
        os.makedirs(ioc_folder_path)

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        
        source_folder = namespace.Folders.Item(OUTLOOK_MAILBOX)
        for folder_name in SOURCE_FOLDER_PATH:
            source_folder = source_folder.Folders.Item(folder_name)
        
        try:
            processed_folder = source_folder.Folders.Item(PROCESSED_FOLDER_NAME)
        except Exception:
            print(f"  [INFO] Creando carpeta de destino '{PROCESSED_FOLDER_NAME}'...")
            processed_folder = source_folder.Folders.Add(PROCESSED_FOLDER_NAME)

        items = source_folder.Items
        items.Sort("[ReceivedTime]", True)
        num_a_procesar = min(cantidad_a_leer, items.Count)
        print(f"📬 Analizando los {num_a_procesar} correos más recientes en '{source_folder.Name}'...")
        if num_a_procesar == 0: return

        correos_a_procesar = [items.Item(i + 1) for i in range(num_a_procesar)]
        
        for email in tqdm(correos_a_procesar, desc="Procesando correos", unit="correo"):
            if email.Subject != REQUIRED_SUBJECT:
                continue
            if email.SenderEmailAddress != REQUIRED_SENDER:
                continue
            if email.Attachments.Count != 1:
                continue

            received_date = email.ReceivedTime
            unique_id = int(received_date.timestamp())
            
            print(f"\n✅ Correo validado. Asunto: '{email.Subject}', Remitente: '{email.SenderEmailAddress}'.")
            
            attachment = email.Attachments.Item(1)
            data_df, temp_path = procesar_adjunto_csv(attachment, ioc_folder_path)
            
            if data_df is not None and not data_df.empty:
                num_inserted = almacenar_datos(db_connection, data_df, unique_id, received_date, attachment.FileName)
                
                if num_inserted > 0:
                    mantis_id = create_mantis_ticket(email.Subject, email.HTMLBody, unique_id)
                    if mantis_id:
                        actualizar_id_mantis(db_connection, unique_id, mantis_id)
                    
                print(f"  [INFO] Moviendo correo a la carpeta '{processed_folder.Name}'...")
                email.Move(processed_folder)
            
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
                print(f"  [INFO] Archivo temporal '{os.path.basename(temp_path)}' eliminado.")

    except Exception as e:
        print(f"❌ Error general al procesar Outlook: {e}")
    finally:
        if db_connection and db_connection.is_connected():
            db_connection.close()
            print("🔌 Conexión a la base de datos cerrada.")

# PASO 5: EJECUCIÓN PRINCIPAL
if __name__ == "__main__":
    print(f"--- Iniciando Script de Monitoreo de Planes de Credito ---")
    print(f"Hora de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    CANTIDAD_DE_CORREOS_A_LEER = 100
    procesar_correos_outlook(CANTIDAD_DE_CORREOS_A_LEER)
    
    print("--- Script finalizado ---")