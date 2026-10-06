# --------------------------------------------------------------------------
# SCRIPT: ioc_ingestor_final_v2.py
# DESCRIPCIÓN: Versión final que resuelve el error de mover correos y
#              guarda la fecha de recepción del correo en la base de datos.
# --------------------------------------------------------------------------

# PASO 1: CONFIGURACIÓN Y LIBRERÍAS
import os
import mysql.connector
import win32com.client
import pandas as pd
from datetime import datetime
from tqdm import tqdm

# --- Configuración de la Base de Datos ---
DB_HOST = "172.32.1.51"
DB_USER = "zabbixuser"
DB_PASSWORD = "zabbix"
DB_NAME = "your_database_name"
DB_TABLE = "GPF_00_Planesdecredito"

# --- Configuración de Outlook ---
OUTLOOK_MAILBOX = "monitoreosistemas@corporaciongpf.com"
SOURCE_FOLDER_PATH = ["Monitoreo Planes de Credito"]

# --- MODIFICACIÓN CLAVE: El nombre de la carpeta de destino DEBE SER DIFERENTE ---
PROCESSED_FOLDER_NAME = "PDC Procesados" # Cambiado de "IOC FIREWALLS" para evitar el error.

# --- Configuración de Archivos Adjuntos ---
COLUMN_NAMES = {
    "domains": "Domains",
    "hashes": "Hashes"
}
IOC_FOLDER_NAME = "ioc"

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

def almacenar_iocs(db_connection, iocs_dict, source_file, date_added):
    """Almacena un diccionario de IOCs en la BD, incluyendo la fecha de adición."""
    if not db_connection: return 0
    cursor = db_connection.cursor()
    query = f"INSERT IGNORE INTO {DB_TABLE} (ioc_value, ioc_type, source_file, date_added) VALUES (%s, %s, %s, %s)"
    count = 0
    try:
        for ip in iocs_dict.get('ips', []):
            cursor.execute(query, (ip, 'IP', source_file, date_added)); count += cursor.rowcount
        # Puedes añadir bucles para dominios y hashes si los necesitas
        db_connection.commit()
        cursor.close()
        if count > 0:
            print(f"📦 ÉXITO: Se almacenaron {count} nuevos IOCs del archivo '{source_file}'.")
        else:
            print(f"  [INFO] No se añadieron nuevos IOCs de '{source_file}'. Es posible que ya existieran en la BD.")
    except mysql.connector.Error as err:
        print(f"❌ ERROR SQL al insertar datos de '{source_file}': {err}")
        db_connection.rollback()
        return 0
    return count

def limpiar_ip(ip_address):
    """Limpia una dirección IP eliminando los corchetes."""
    return str(ip_address).replace('[', '').replace(']', '')

# PASO 3: PROCESAMIENTO DE ARCHIVOS ADJUNTOS
def procesar_adjunto_excel(attachment, ioc_folder_path):
    save_path = os.path.join(ioc_folder_path, attachment.FileName)
    attachment.SaveAsFile(save_path)
    iocs = {"ips": [], "domains": [], "hashes": []}
    try:
        df_dict = pd.read_excel(save_path, sheet_name=None, header=None)
        for sheet_name, df in df_dict.items():
            if not df.empty and 0 in df.columns:
                ips_sucias = df[0].dropna().astype(str).tolist()
                iocs['ips'].extend([limpiar_ip(ip) for ip in ips_sucias])
    except Exception as e:
        print(f"⚠️ Error CRÍTICO al leer el archivo Excel '{attachment.FileName}': {e}")
    return iocs

# PASO 4: PROCESAMIENTO DE CORREOS EN OUTLOOK
def procesar_correos_outlook(cantidad_a_leer):
    db_connection = conectar_base_datos()
    if not db_connection: return

    ioc_folder_path = os.path.join(os.getcwd(), IOC_FOLDER_NAME)
    if not os.path.exists(ioc_folder_path):
        os.makedirs(ioc_folder_path)

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        current_folder = namespace.Folders.Item(OUTLOOK_MAILBOX)
        for folder_name in SOURCE_FOLDER_PATH:
            current_folder = current_folder.Folders.Item(folder_name)
        source_folder = current_folder
        
        items = source_folder.Items
        items.Sort("[ReceivedTime]", True)
        num_a_procesar = min(cantidad_a_leer, items.Count)
        print(f"📬 Analizando los {num_a_procesar} correos más recientes en '{source_folder.Name}'...")
        if num_a_procesar == 0: return

        correos_a_procesar = [items.Item(i + 1) for i in range(num_a_procesar)]
        
        parent_folder = source_folder.Parent
        try:
            # Busca o crea la carpeta de destino en el mismo nivel que la de origen
            processed_folder = parent_folder.Folders.Item(PROCESSED_FOLDER_NAME)
        except Exception:
            print(f"  [INFO] Creando carpeta de destino '{PROCESSED_FOLDER_NAME}'...")
            processed_folder = parent_folder.Folders.Add(PROCESSED_FOLDER_NAME)

        for email in tqdm(correos_a_procesar, desc="Procesando correos", unit="correo"):
            email_received_date = email.ReceivedTime

            if email.Attachments.Count > 0:
                was_processed = False
                for attachment in email.Attachments:
                    if attachment.FileName.lower().endswith(('.xlsx', '.xls')):
                        print(f"\n📄 Procesando adjunto '{attachment.FileName}' del correo '{email.Subject}'...")
                        iocs_extraidos = procesar_adjunto_excel(attachment, ioc_folder_path)
                        
                        if any(iocs_extraidos.values()):
                            almacenar_iocs(db_connection, iocs_extraidos, attachment.FileName, email_received_date)
                            was_processed = True
                
                if was_processed:
                    print(f"  [INFO] Moviendo correo a la carpeta '{processed_folder.Name}'...")
                    email.Move(processed_folder)

    except Exception as e:
        print(f"❌ Error general al procesar Outlook: {e}")
    finally:
        if db_connection and db_connection.is_connected():
            db_connection.close()
            print("🔌 Conexión a la base de datos cerrada.")

# PASO 5: EJECUCIÓN PRINCIPAL
if __name__ == "__main__":
    print(f"--- Iniciando Script de Ingesta de IOCs (v2 - Fecha y Mover Corregido) ---")
    print(f"Hora de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Asegúrate de haber añadido la columna 'date_added' a tu tabla en MySQL.
    # ALTER TABLE iocs ADD COLUMN date_added DATETIME NULL;
    
    CANTIDAD_DE_CORREOS_A_LEER = 100 
    procesar_correos_outlook(CANTIDAD_DE_CORREOS_A_LEER)
    
    print("--- Script finalizado ---")