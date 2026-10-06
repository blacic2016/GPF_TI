# --------------------------------------------------------------------------
# SCRIPT: ioc_ingestor_oneshot_final.py
# DESCRIPCIÓN: Script de ejecución única que analiza correos. Si el correo
#              es del día actual, sigue el flujo normal. Si es de días
#              anteriores, se marca como 'PRUEBA' y se le añade un prefijo
#              al estado del análisis.
# --------------------------------------------------------------------------

# PASO 1: CONFIGURACIÓN Y LIBRERÍAS
import os
import mysql.connector
import win32com.client
import pandas as pd
from datetime import datetime, time, date, timedelta
from tqdm import tqdm
import requests
import json
from bs4 import BeautifulSoup

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
HORARIOS_ESPERADOS = {
    time(8, 0): (time(8, 0), time(8, 10)),
    time(12, 0): (time(12, 0), time(12, 10)),
    time(16, 0): (time(16, 0), time(16, 10)),
    time(20, 0): (time(20, 0), time(20, 10)),
}

# PASO 2: FUNCIONES DE BASE DE DATOS
def conectar_base_datos():
    """Establece conexión a la base de datos MySQL."""
    print("?? [LOG] Intentando conectar a la base de datos...")
    try:
        connection = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        print("? [LOG] Conexión a la base de datos exitosa.")
        return connection
    except mysql.connector.Error as err:
        print(f"? [LOG] Error al conectar a la base de datos: {err}")
        return None

# --- CAMBIO: La función ahora acepta y almacena el 'tipo_ejecucion' ---
def almacenar_metadatos_archivo(db_connection, unique_id, email_subject, email_sender,
                                 nombre_archivo_resultante, fecha_recepcion, estado_analisis, tipo_ejecucion):
    """Almacena los metadatos del archivo, incluyendo el tipo de ejecución."""
    if not db_connection: return
    cursor = db_connection.cursor()
    query = f"""
    INSERT IGNORE INTO {DB_ARCHIVOS_TABLE}
    (id_unico, asunto_correo, remitente_correo, nombre_archivo_resultante, fecha_recepcion, estado_analisis, tipo_ejecucion, fecha_creacion_registro)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        cursor.execute(query, (
            unique_id,
            email_subject,
            email_sender,
            nombre_archivo_resultante,
            fecha_recepcion,
            estado_analisis,
            tipo_ejecucion, # Nuevo campo
            datetime.now()
        ))
        db_connection.commit()
        if cursor.rowcount > 0:
            print(f"?? [LOG] Metadatos almacenados. ID: '{unique_id}', Estado: '{estado_analisis}', Tipo: '{tipo_ejecucion}'.")
        else:
            print(f"?? [LOG] Metadatos para ID '{unique_id}' ya existen. Ignorando inserción.")
    except mysql.connector.Error as err:
        print(f"? [LOG] ERROR SQL al insertar metadatos: {err}")
        db_connection.rollback()
    finally:
        cursor.close()

# --- El resto de funciones de BDD no necesitan cambios, excepto donde se llama a 'almacenar_metadatos_archivo' ---
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
        print(f"?? [LOG] ÉXITO: Se almacenaron {count} nuevos registros de datos.")
    except mysql.connector.Error as err:
        print(f"? [LOG] ERROR SQL al insertar datos: {err}")
        db_connection.rollback()
        return 0
    return count

def actualizar_id_mantis(db_connection, unique_id, mantis_id):
    """Actualiza el ID del ticket de Mantis en la tabla de metadatos."""
    print(f"?? [LOG] Intentando actualizar el ID de Mantis '{mantis_id}' para el ID único '{unique_id}'.")
    if not db_connection: return
    cursor = db_connection.cursor()
    query = f"UPDATE {DB_ARCHIVOS_TABLE} SET id_mantis = %s WHERE id_unico = %s"
    try:
        cursor.execute(query, (mantis_id, unique_id))
        db_connection.commit()
        print(f"? [LOG] Se actualizó el ID de Mantis '{mantis_id}' para el ID único '{unique_id}'.")
    except mysql.connector.Error as err:
        print(f"? [LOG] ERROR SQL al actualizar ID de Mantis: {err}")
        db_connection.rollback()
    finally:
        cursor.close()
    print("? [LOG] Actualización de ID de Mantis finalizada.")

def verificar_ticket_existente_por_id(db_connection, unique_id):
    """Verifica si ya se ha registrado un ID de Mantis para un 'id_unico' específico."""
    if not db_connection: return True
    cursor = db_connection.cursor()
    query = f"SELECT id_mantis FROM {DB_ARCHIVOS_TABLE} WHERE id_unico = %s"
    try:
        cursor.execute(query, (unique_id,))
        result = cursor.fetchone()
        if result and result[0]:
            print(f"?? [LOG] Ya existe un ticket ({result[0]}) para el ID único '{unique_id}'. Omitiendo creación.")
            return True
        return False
    except mysql.connector.Error as err:
        print(f"? [LOG] ERROR SQL al verificar ticket por ID: {err}")
        return True
    finally:
        cursor.close()

def verificar_evento_en_ventana_10min(db_connection, window_start, fecha_actual):
    """Verifica si ya se registró un correo (OK o ERROR) para la ventana de 10 minutos."""
    if not db_connection: return True
    cursor = db_connection.cursor()
    start_time = window_start
    end_time = (datetime.combine(fecha_actual, start_time) + timedelta(minutes=10)).time()
    query = f"""
    SELECT COUNT(*) FROM {DB_ARCHIVOS_TABLE}
    WHERE DATE(fecha_recepcion) = %s
    AND TIME(fecha_recepcion) >= %s
    AND TIME(fecha_recepcion) < %s
    AND estado_analisis IN ('OK', 'ERROR')
    """
    try:
        cursor.execute(query, (fecha_actual, start_time, end_time))
        count = cursor.fetchone()[0]
        return count > 0
    except mysql.connector.Error as err:
        print(f"? [LOG] ERROR SQL al verificar evento en ventana de 10 min: {err}")
        return True
    finally:
        cursor.close()

def verificar_ticket_outtime_existente(db_connection, window_start, fecha_actual):
    """Verifica si ya existe un ticket 'OUTTIME' para una ventana de horario específica."""
    if not db_connection: return True
    cursor = db_connection.cursor()
    asunto_buscado = f"OUTTIME: No se recibió el correo de las {window_start.strftime('%H:%M')} a tiempo"
    query = f"""
    SELECT COUNT(*) FROM {DB_ARCHIVOS_TABLE}
    WHERE estado_analisis = 'OUTTIME'
    AND asunto_correo = %s
    AND DATE(fecha_creacion_registro) = %s
    """
    try:
        cursor.execute(query, (asunto_buscado, fecha_actual))
        count = cursor.fetchone()[0]
        return count > 0
    except mysql.connector.Error as err:
        print(f"? [LOG] ERROR SQL al verificar ticket OUTTIME existente: {err}")
        return True
    finally:
        cursor.close()


# PASO 3: FUNCIONES DE PROCESAMIENTO Y MANEJO DE MANTIS (Sin cambios)
def procesar_adjunto_csv(attachment, ioc_folder_path, reception_date):
    """Guarda el adjunto, lo renombra y extrae los datos."""
    print(f"?? [LOG] Iniciando procesamiento de adjunto '{attachment.FileName}'.")
    if not attachment.FileName.lower().startswith(ATTACHMENT_NAME_PREFIX.lower()):
        print(f"?? [LOG] Ignorando adjunto: El nombre no empieza con '{ATTACHMENT_NAME_PREFIX}'.")
        return None, None

    timestamp = reception_date.strftime('%Y%m%d%H%M%S')
    new_file_name = f"{NEW_ATTACHMENT_PREFIX}{timestamp}.csv"
    save_path = os.path.join(ioc_folder_path, new_file_name)

    try:
        attachment.SaveAsFile(save_path)
        print(f"? [LOG] Adjunto guardado permanentemente en '{save_path}'.")
        df = pd.read_csv(save_path, sep=';')
        
        if df.empty:
            print("  [LOG] INFO: El archivo está vacío (solo encabezado).")
        else:
            print("? [LOG] Datos extraídos del archivo correctamente.")
        return df, save_path
    except Exception as e:
        print(f"? [LOG] Error al leer el archivo CSV '{new_file_name}': {e}")
        return pd.DataFrame(), save_path

def get_operador():
    """Obtener el operador desde un servicio externo."""
    print("?? [LOG] Intentando obtener el operador de turno...")
    url = "http://172.32.1.55:3001/turnos/actual-correo"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            operador = response.text.strip()
            print(f"? [LOG] Operador de turno obtenido: '{operador}'.")
            return operador
        print(f"? [LOG] Error al obtener operador, código de estado: {response.status_code}")
    except requests.RequestException as e:
        print(f"? [LOG] Error de conexión al obtener operador: {e}")
    print("?? [LOG] Usando operador por defecto.")
    return "oscar.guerra@sonda.com"

def create_mantis_ticket(email, unique_id, subject_prefix=""):
    """Crear un ticket en MantisBT, adaptado para diferentes estados."""
    print(f"?? [LOG] Intentando crear ticket en MantisBT para ID único: '{unique_id}'.")
    html_body = email.HTMLBody
    soup = BeautifulSoup(html_body, 'html.parser')
    table_html = soup.find('table')

    if table_html:
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
        final_description = email.Body

    operador = get_operador()
    summary = f"{subject_prefix}Reporte de Planes de Crédito: ID:{unique_id} -> {email.Subject}"

    payload = {
        "summary": summary, "description": final_description, "project": {"id": MANTIS_PROJECT_ID},
        "handler": {"name": operador}, "category": MANTIS_CATEGORY, "priority": {"name": MANTIS_PRIORITY},
        "custom_fields": [{"field": {"id": 2, "name": "id_unique"}, "value": unique_id}],
    }
    headers = {"Content-Type": "application/json", "Authorization": MANTIS_AUTH_TOKEN}
    try:
        response = requests.post(MANTIS_URL, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        issue_id = response.json().get('issue', {}).get('id')
        if issue_id:
            print(f"? [LOG] Ticket de Mantis creado con el ID: '{issue_id}'.")
            return issue_id
        else:
            print(f"? [LOG] No se pudo obtener el ID del ticket. Respuesta: {response.text}")
            return None
    except requests.RequestException as e:
        print(f"? [LOG] Error de la API de MantisBT: {e}")
        return None

def create_mantis_ticket_for_outtime(unique_id, subject, description):
    """Crear un ticket en MantisBT para un correo que no llegó a tiempo."""
    print(f"?? [LOG] Intentando crear ticket en MantisBT para correo OUTTIME. ID: '{unique_id}'.")
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
            print(f"? [LOG] Ticket de Mantis para OUTTIME creado con el ID: '{issue_id}'.")
            return issue_id
        else:
            print(f"? [LOG] No se pudo obtener el ID del ticket. Respuesta: {response.text}")
            return None
    except requests.RequestException as e:
        print(f"? [LOG] Error de la API de MantisBT: {e}")
        return None


# --------------------------------------------------------------------------
# PASO 4: LÓGICA PRINCIPAL Y PROCESAMIENTO DE CORREOS
# --------------------------------------------------------------------------
def get_corresponding_window(received_time):
    """Determina a qué ventana de monitoreo pertenece un correo."""
    received_time_obj = received_time.time()
    window_starts = sorted(HORARIOS_ESPERADOS.keys(), reverse=True)
    for start_time in window_starts:
        if received_time_obj >= start_time:
            return start_time
    return window_starts[-1]

# --- CAMBIO: Lógica de procesamiento de correos modificada para manejar 'PRUEBA' vs 'EJECUTADO' ---
def procesar_correos_outlook(cantidad_a_leer):
    """Procesar correos, diferenciando entre ejecución normal y prueba para correos antiguos."""
    print("\n?? [LOG] Iniciando ciclo de procesamiento de correos de Outlook.")
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
            print("?? [LOG] No hay correos para procesar.")
            if db_connection and db_connection.is_connected(): db_connection.close()
            return
        
        print(f"?? [LOG] Analizando los {num_a_procesar} correos más recientes.")
        correos_a_procesar = [items.Item(i + 1) for i in range(num_a_procesar)]

        for email in tqdm(correos_a_procesar, desc="Procesando correos", unit="correo"):
            if not (email.Subject == REQUIRED_SUBJECT and 
                    email.SenderEmailAddress.lower() == REQUIRED_SENDER.lower() and 
                    email.Attachments.Count == 1):
                continue

            received_time = email.ReceivedTime.replace(tzinfo=None)
            unique_id = int(received_time.timestamp())
            
            print(f"\n--- Procesando correo de las {received_time} (ID: {unique_id}) ---")

            # --- NUEVA LÓGICA DE FECHA ---
            tipo_ejecucion = 'EJECUTADO'
            prefijo_estado = ''
            today = date.today()

            if received_time.date() < today:
                print(f"  [LOG] Correo del pasado ({received_time.date()}). Se procesará como PRUEBA.")
                tipo_ejecucion = 'PRUEBA'
                prefijo_estado = 'PR_'
            # -------------------------------

            attachment = email.Attachments.Item(1)
            data_df, saved_path = procesar_adjunto_csv(attachment, ioc_folder_path, received_time)
            nombre_archivo_resultante = os.path.basename(saved_path) if saved_path else None
            
            estado_base = "INDEFINIDO"
            ticket_subject_prefix = ""
            crear_ticket = False

            window_start = get_corresponding_window(received_time)
            ventana_inicio, ventana_fin = HORARIOS_ESPERADOS[window_start]

            if ventana_inicio <= received_time.time() < ventana_fin:
                if data_df.empty:
                    estado_base = "OK"
                else:
                    estado_base = "ERROR"
                    ticket_subject_prefix = "ERROR: "
                    crear_ticket = True
            else:
                if data_df.empty:
                    estado_base = "OK OUTTIME"
                else:
                    estado_base = "ERROR OUTTIME"
                    ticket_subject_prefix = "ERROR OUTTIME: "
                    crear_ticket = True
            
            # Aplicar prefijo si es una prueba
            estado_final = prefijo_estado + estado_base
            
            # Almacenar metadatos siempre con el tipo de ejecución
            almacenar_metadatos_archivo(db_connection, unique_id, email.Subject, email.SenderEmailAddress,
                                        nombre_archivo_resultante, received_time, estado_final, tipo_ejecucion)

            # La creación de tickets y almacenamiento de datos solo ocurre si es una ejecución normal
            if tipo_ejecucion == 'EJECUTADO':
                if not data_df.empty:
                    num_inserted = almacenar_datos_del_archivo(db_connection, data_df, unique_id)
                    
                    if num_inserted > 0 and crear_ticket:
                        if not verificar_ticket_existente_por_id(db_connection, unique_id):
                            mantis_id = create_mantis_ticket(email, unique_id, ticket_subject_prefix)
                            if mantis_id:
                                actualizar_id_mantis(db_connection, unique_id, mantis_id)
            else:
                print("  [LOG] Modo PRUEBA: No se almacenarán datos ni se crearán tickets.")

            try:
                email.Move(processed_folder)
            except Exception as e:
                print(f"? [LOG] ERROR al mover el correo: {e}.")
            
    except Exception as e:
        print(f"? [LOG] Error general al procesar Outlook: {e}")
    finally:
        if db_connection and db_connection.is_connected():
            db_connection.close()
            print("?? [LOG] Conexión a la base de datos cerrada.")

# --- CAMBIO: La función ahora pasa 'EJECUTADO' como tipo de ejecución ---
def manejar_correo_outtime(window_start):
    """Función para crear registro y ticket para un correo que no llegó a tiempo."""
    horario_str = window_start.strftime('%H:%M')
    print(f"  [LOG] ¡CORREO NO RECIBIDO A TIEMPO! Se creará registro y ticket OUTTIME para las {horario_str}.")
    
    db_connection = conectar_base_datos()
    if not db_connection: return

    now = datetime.now()
    unique_id = int(now.timestamp())
    subject = f"OUTTIME: No se recibió el correo de las {horario_str} a tiempo"
    description = f"No se recibió el correo de Monitoreo de Planes de Crédito que debía haber llegado en la ventana de las {horario_str}."

    # Un evento OUTTIME siempre es una ejecución en tiempo real
    almacenar_metadatos_archivo(db_connection, unique_id, subject, "", "", now, "OUTTIME", "EJECUTADO")
    
    mantis_id = create_mantis_ticket_for_outtime(unique_id, subject, description)
    if mantis_id:
        actualizar_id_mantis(db_connection, unique_id, mantis_id)

    if db_connection and db_connection.is_connected():
        db_connection.close()
        print("?? [LOG] Conexión a la base de datos cerrada.")

# --------------------------------------------------------------------------
# PASO 5: EJECUCIÓN PRINCIPAL DE UN SOLO USO
# --------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"--- Iniciando Script de Monitoreo (Modo Ejecución Única) ---")
    print(f"Hora de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print("\n[PASO A] Buscando y procesando correos recibidos...")
    procesar_correos_outlook(cantidad_a_leer=100)

    print("\n[PASO B] Verificando si faltan correos de horarios ya transcurridos...")
    now = datetime.now()
    
    db_connection_check = conectar_base_datos()

    if db_connection_check:
        try:
            for window_start, (start_time, end_time) in HORARIOS_ESPERADOS.items():
                
                cierre_ventana_hoy = now.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)

                if now > cierre_ventana_hoy:
                    horario_str = start_time.strftime('%H:%M')
                    print(f"\n? Verificando ventana de las {horario_str}...")

                    if not verificar_evento_en_ventana_10min(db_connection_check, window_start, now.date()):
                        
                        if not verificar_ticket_outtime_existente(db_connection_check, window_start, now.date()):
                            print(f"?? ¡Correo Faltante! No se encontró email para la ventana de las {horario_str}.")
                            manejar_correo_outtime(window_start)
                        else:
                            print(f"?? [LOG] Se omite la creación de un nuevo ticket OUTTIME para el horario '{horario_str}' pues ya fue reportado.")
                    else:
                        print(f"?? [LOG] Ya se procesó un correo a tiempo para la ventana de {horario_str}. No se creará ticket OUTTIME.")
                else:
                    print(f"\n? La ventana de las {start_time.strftime('%H:%M')} aún no ha cerrado. Omitiendo.")
        finally:
            if db_connection_check and db_connection_check.is_connected():
                db_connection_check.close()
                print("\n?? [LOG] Conexión de verificación de faltantes cerrada.")
    else:
        print("? [LOG] No se pudo conectar a la base de datos para verificar correos faltantes.")

    print("\n--- ? Análisis completado. El script se cerrará. ---")