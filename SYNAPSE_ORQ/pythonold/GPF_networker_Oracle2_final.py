import os
import re
import json
import requests
import mysql.connector
import win32com.client
from datetime import datetime
from tqdm import tqdm
import time
from dateutil import parser # Necesario para compatibilidad de fechas

# --- Variables Globales ---
# Las variables globales se declaran y se inicializan una sola vez aquí.

alarmas_nuevas = 0
alarmas_antiguas = 0
alarmas_erroneas = 0
issue_id = None
operador = ""
operador_siglas = ""


# --- Funciones de Utilidad y Conexión de API ---

def get_operador():
    """Obtiene el correo del operador de turno actual."""
    url = "http://172.32.1.55:3001/turnos/actual-correo"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return str(response.text).strip() + " "
        else:
            print(f"Advertencia: API de operador devolvió estado {response.status_code}")
            return "oscar.guerra@sonda.com"
    except requests.RequestException as e:
        print(f"Error al obtener el operador: {e}")
        return "oscar.guerra@sonda.com"
        
def get_operador_siglas():
    """
    Obtiene las siglas del operador de turno actual.
    
    MODIFICADO: Se ha eliminado la lógica de conexión a la API
    y siempre devuelve el valor por defecto 'OG'.
    """
    # Se ignora la URL y la lógica de la solicitud requests.get
    # url = "http://172.32.1.51/usuario/dataSiglas.php"
    
    # Se devuelve directamente el valor deseado (OG)
    return "OG"
        
def create_connection():
    """Establece la conexión a la base de datos MySQL."""
    try:
        connection = mysql.connector.connect(
            host="172.32.1.51",
            user="zabbixuser",
            password="zabbix",
            database="your_database_name" # Reemplace por el nombre real de su DB
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Error al conectar a MySQL: {err}")
        return None

# --- Funciones de Limpieza y Extracción de Datos ---

def clean_string(input_string):
    """Limpia el string de etiquetas HTML, URLs y caracteres especiales."""
    result = re.sub(r'<[^>]+>', '', input_string)
    result = re.sub(r'http[s]?://\S+', '', result)
    result = re.sub(r'www\.\S+', '', result)
    result = re.sub(r'mailto:\S+', '', result)
    result = re.sub(r'(\r\n|\r|\n|\t|\\|")', ' ', result)
    result = re.sub(r'\|', '', result) 
    return result.strip()
    
def extract_host(email):
    """Extrae el nombre de host a partir de la dirección de correo electrónico del remitente."""
    try:
        domain_part = email.split('@')[1]
        host = domain_part.split('.')[0]    
        return host
    except IndexError:
        return None  

def parse_email_body(body):
    """Analiza el cuerpo del correo para extraer campos clave de Networker."""
    parsed_content = {}
    lines = re.split(r'(\r\n|\r|\n)', body)
    
    for line in lines:
        if ':' in line:
            parts = line.split(':', 1)
            key = clean_string(parts[0].strip())
            value = clean_string(parts[1].strip())
            
            if key == "NSR Protection Group":
                 parsed_content["NSR_Protection_Group"] = value
            elif key == "Succeeded":
                 parsed_content["Succeeded"] = value
        elif "--- Successful" in line or "--- Unsuccessful" in line:
            status_line = clean_string(line)
            parsed_content["networker_status"] = status_line
            
    if "networker_status" not in parsed_content:
        if "--- Successful" in body:
            parsed_content["networker_status"] = "--- Successful ---"
        elif "--- Unsuccessful" in body:
            parsed_content["networker_status"] = "--- Unsuccessful ---"
        else:
             parsed_content["networker_status"] = "--Revisar correo--"

    if "NSR_Protection_Group" not in parsed_content:
        parsed_content["NSR_Protection_Group"] = "Sin Grupo"

    if "Succeeded" not in parsed_content:
        parsed_content["Succeeded"] = "SD" 
        
    return parsed_content

# --- Funciones de Integración con MantisBT ---

def create_mantis_summary(json_content, body_content):
    """Crea un nuevo ticket en MantisBT para alarmas fallidas."""
    
    # *** CORRECCIÓN CRÍTICA DEL SYNTAXERROR: global al principio ***
    global alarmas_erroneas 
    global operador 
    
    url_mn = "http://172.32.1.51:10090/api/rest/issues"
    
    description_text = json_content.get("subject", "Sin descripción")
    additional_info = "\n".join([f"{clave}: {valor}" for clave, valor in body_content.items()])

    payload = {
        "summary": f"Alarmas Networker ORACLE: ID:{json_content.get('id_unique', 'N/A')} -> {json_content.get('subject', 'N/A')} --> {json_content.get('host', 'N/A')}",
        "description": description_text,
        "additional_information": additional_info,
        "project": {"id": 11},
        "handler": {"name": operador.strip()},
        "category": {"name": "General"},
        "priority": {"name": "alta"},
        "custom_fields": [
            {"field": {"id": 1, "name": "Host"}, "value": json_content.get('host', "Sin valor")},
            {"field": {"id": 2, "name": "id_unique"}, "value": str(json_content.get('id_unique', "Sin valor"))},
            {"field": {"id": 3, "name": "Target_Lifecycle_Status"}, "value": json_content.get('NSR_Protection_Group', "Sin valor")},
            {"field": {"id": 4, "name": "Event_Name"}, "value": json_content.get('Succeeded', "Sin valor")},
            {"field": {"id": 5, "name": "Rule_Name"}, "value": json_content.get('networker_status', "Sin valor")},
            {"field": {"id": 6, "name": "Date_llegada"}, "value": json_content.get('date', "Sin valor")},
            {"field": {"id": 7, "name": "Fecha_creacion"}, "value": json_content.get('creation_date', "Sin valor")}
        ]
    }
    
    headers = {
        "cookie": "PHPSESSID=0taolevemh4k50psm684qa2qri; MANTIS_PROJECT_COOKIE=0",
        "Content-Type": "application/json",
        "Authorization": "jWma-n55OtqOd1j_HuS85LPRrWsdE-40" 
    }
    
    try:
        response = requests.post(url_mn, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 201:
            response_data = response.json()
            issue_id_created = response_data.get('issue', {}).get('id')
            return issue_id_created
        else:
            print(f"Error al crear el resumen en MantisBT: {response.status_code} - {response.text}")
            alarmas_erroneas += 1 # Uso correcto después de global
            return 0
            
    except requests.RequestException as e:
        print(f"Error de conexión al enviar datos a MantisBT: {e}")
        alarmas_erroneas += 1 # Uso correcto después de global
        return 0

# --- Funciones de Inserción y Lógica Principal ---

def crear_data_to_db(connection, json_content, body_content, issue_data):
    """Inserta los datos del correo en la base de datos MySQL."""
    
    # *** CORRECCIÓN CRÍTICA DEL SYNTAXERROR: global al principio ***
    global alarmas_nuevas, alarmas_erroneas, operador_siglas 
    
    try:
        cursor = connection.cursor()
        insert_query = (
            "INSERT INTO GPF_respaldos_Networker_Oracle (id_unique, sender, subject, host, hostserver, Sistema, "
            "NSR_Protection_Group, Succeeded, networker_status, date, Alarma, hora, "
            "creation_date, ubicacion, dia, mes, year, mantisid, siglas, grupo) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )

        cursor.execute(insert_query, (
            json_content["id_unique"],  
            json_content["sender"],
            json_content["subject"],
            json_content["host"],
            json_content["hostserver"],  
            json_content["Sistema"],
            json_content["NSR_Protection_Group"],  
            json_content["Succeeded"],  
            json_content["networker_status"],
            json_content["date"],  
            json_content["Succeeded"],  
            json_content["hora"],
            json_content["creation_date"],
            json_content["ubicacion"],
            json_content["dia"],
            json_content["mes"],
            json_content["year"],
            issue_data, 
            operador_siglas,
            json_content["grupo"]
        ))
        connection.commit()
        alarmas_nuevas += 1 # Uso correcto después de global
        
    except mysql.connector.Error as err:
        print(f"Database error al insertar datos: {err}")
        alarmas_erroneas += 1 # Uso correcto después de global
    finally:
        if cursor:
            cursor.close()

def insert_data_to_db(connection, json_content, body_content):
    """Verifica si la alarma existe y realiza la lógica de inserción/creación de Mantis."""
    
    # *** CORRECCIÓN CRÍTICA DEL SYNTAXERROR: global al principio ***
    global alarmas_nuevas, alarmas_antiguas, alarmas_erroneas
    
    cursor = None
    try:
        cursor = connection.cursor(buffered=True)
        # 1. Verifica si el id_unique ya existe
        check_query_inicial = "SELECT COUNT(*) FROM GPF_respaldos_Networker_Oracle WHERE id_unique = %s AND subject = %s LIMIT 1"
        cursor.execute(check_query_inicial, (json_content['id_unique'], json_content["subject"]))
        result = cursor.fetchone()
        
        if result[0] > 0:
            alarmas_antiguas += 1 # Uso correcto después de global
        else:
            issue_data = 0 
            
            # 2. Lógica de creación de ticket Mantis si el estado es 'Failed'
            if json_content["Succeeded"] == "Failed":
                issue_data = create_mantis_summary(json_content, body_content)
                
            # 3. Insertar datos en la base de datos (con o sin Mantis ID)
            crear_data_to_db(connection, json_content, body_content, issue_data)
            
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        alarmas_erroneas += 1 # Uso correcto después de global
    finally:
        if cursor:
            cursor.close()

# --- Función Principal ---

def process_emails():
    """Función principal para inicializar y procesar los correos."""
    # Estas variables se usan y modifican globalmente
    global operador, operador_siglas 

    connection = None
    try:
        # 1. Obtener Operador y Siglas
        operador = get_operador()
        operador_siglas = get_operador_siglas()
        
        print(f"Operador Actual: {operador.strip()} ({operador_siglas.strip()})")

        # 2. Conectar a Outlook
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        
        # RUTA DE LA CARPETA
        folder = namespace.Folders.Item("monitoreosistemas@corporaciongpf.com").Folders.Item("Respaldos").Folders.Item("RESPALDOS ORACLE 2")
        
        if not folder:
            print("Error: Carpeta de Outlook no encontrada.")
            return

        # 3. Conectar a la Base de Datos
        connection = create_connection()
        if connection is None:
            print("Database connection failed. Exiting.")
            return
            
        mails_to_process = 40
        total_emails_in_folder = folder.Items.Count
        
        folder.Items.Sort("[ReceivedTime]", True)
        
        if total_emails_in_folder == 0:
            print("No hay correos para procesar en la carpeta.")
            return
            
        # Determinar el rango: procesar los últimos 40 correos
        # El índice de los items en Outlook VBS/COM es 1-based, no 0-based
        start_index = max(1, total_emails_in_folder - mails_to_process + 1)
        end_index = total_emails_in_folder
        
        print(f"Total de correos: {total_emails_in_folder}. Procesando desde índice {start_index} hasta {end_index}.")

        # 4. Bucle principal de procesamiento
        # tqdm itera de forma creciente, usamos el índice 'i' directamente
        for i in tqdm(range(start_index, end_index + 1), desc="Procesando correos", unit="correo"):
            try:
                mail_item = folder.Items.Item(i)
                ubicacion_mail = i

                if not isinstance(mail_item, win32com.client.CDispatch):
                    continue

                sender_host = clean_string(mail_item.SenderEmailAddress)
                body_content = parse_email_body(mail_item.Body)
                titulo = mail_item.Subject
                titulols = titulo.lower()

                # --- Lógica de Extracción y Clasificación ---
                
                estado_asunto = "SD"
                if "!!! error !!!" in titulols or "!!! error !!" in titulols or "!!!error !!" in titulols:
                    estado_asunto = "Unsuccessful"
                elif "ejecucion respaldo" in titulols or "export pgposfy - geoconfigurator" in titulols:
                    estado_asunto = "Successful"

                titulo_limpio = titulo.replace("Ejecucion", "").replace("respaldo", "").replace("Respaldo", "").replace("!!! ERROR !!!", "").replace("!!! ERROR !!", "").replace("!!!ERROR !!", "").strip()

                # Obtener el Grupo basado en el día de la semana
                dias_semana = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                grupo = titulo_limpio
                for dia in dias_semana:
                    if f" {dia} " in titulo_limpio:
                        grupo, _ = titulo_limpio.split(f" {dia} ", 1)
                        break

                if "Unsuccessful" in estado_asunto:
                    status_final = "Failed"
                elif "Successful" in estado_asunto:
                    status_final = "OK"
                else:
                    status_final = "SD"
                
                # --- Preparación del JSON ---
                fecha_recibida = mail_item.ReceivedTime
                fecha_completa = fecha_recibida.strftime('%Y-%m-%d %H:%M:%S')
                
                # ID único: timestamp + índice para evitar colisiones
                id_unique = int(time.mktime(fecha_recibida.timetuple())) + i 

                json_content = {
                    "id_unique": id_unique,
                    "ubicacion": ubicacion_mail,
                    "sender": sender_host,
                    "subject": clean_string(mail_item.Subject),
                    "host": extract_host(sender_host) or "Unknown Host",
                    "hostserver": mail_item.Subject,
                    "Sistema": "Oracle2",
                    "NSR_Protection_Group": body_content.get("NSR_Protection_Group", grupo),
                    "grupo": clean_string(grupo),
                    "Succeeded": status_final,
                    "networker_status": body_content.get("networker_status", estado_asunto),
                    "date": fecha_completa,
                    "hora": fecha_recibida.strftime('%H'),
                    "dia": fecha_recibida.strftime('%d'),
                    "mes": fecha_recibida.strftime('%m'),
                    "year": fecha_recibida.strftime('%Y'),
                    "creation_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # 5. Insertar datos
                insert_data_to_db(connection, json_content, body_content)

            except Exception as e:
                print(f"\nError al procesar el correo en índice {i}: {e}")
                global alarmas_erroneas
                alarmas_erroneas += 1
                
        # 6. Reporte Final
        print(f"\n--- Resumen de Procesamiento ---")
        print(f"Alarmas Nuevas Insertadas: {alarmas_nuevas}")
        print(f"Alarmas Antiguas (Duplicadas): {alarmas_antiguas}")
        print(f"Errores de Procesamiento: {alarmas_erroneas}")

    except Exception as e:
        print(f"\nOcurrió un error grave en la ejecución principal: {e}")

    finally:
        # 7. Limpieza y Cierre
        if connection and connection.is_connected():
            connection.close()
        try:
            del namespace
            del outlook
        except NameError:
             pass 

if __name__ == "__main__":
    process_emails()