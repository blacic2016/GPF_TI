import os
import re
import json
import requests
import mysql.connector
import win32com.client
from datetime import datetime
from tqdm import tqdm
import time


# Variables globales para el seguimiento de las alarmas
global alarmas_nuevas 
global alarmas_antiguas
global alarmas_erroneas
global issue_id
global operador
global operador_siglas

alarmas_nuevas = 0
alarmas_antiguas = 0
alarmas_erroneas = 0

# --- FUNCIONES DE OBTENCIÓN DE DATOS DEL OPERADOR ---

def get_operador():
    """Obtiene el correo del operador de turno desde la API."""
    url = "http://172.32.1.55:3001/turnos/actual-correo"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return str(response.text).strip() + " "
        else:
            print(f"Advertencia: API de turnos devolvió estado {response.status_code}")
            return "oscar.guerra@sonda.com"
    except requests.RequestException as e:
        print(f"Error al obtener el operador (usando default): {e}")
        return "oscar.guerra@sonda.com"
        
def get_operador_siglas():
    """Obtiene las siglas del operador desde la API."""
    url = "http://172.32.1.51/usuario/dataSiglas.php"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            # Limpia la respuesta JSON (elimina corchetes y comillas)
            siglas = response.text.strip().replace("[", "").replace("]", "").replace('"', '') + " "
            return siglas
        else:
            print(f"Advertencia: API de siglas devolvió estado {response.status_code}")
            return "OG"
    except requests.RequestException as e:
        print(f"Error al obtener las siglas (usando default): {e}")
        return "OG"
        

# --- FUNCIONES DE MANEJO DE MANTISBT ---

def create_mantis_summary(json_content, body_content):
    """Crea un nuevo ticket en MantisBT para las alarmas 'Failed'."""
    # OBLIGATORIO: Declarar variables globales que se van a modificar.
    global alarmas_erroneas 
    
    url_mn = "http://172.32.1.51:10090/api/rest/issues"
    
    # Asegurarse de usar la variable 'operador' global o una versión obtenida
    handler_name = json_content.get('operador', 'oscar.guerra@sonda.com').strip()

    payload = {
        "summary": f"Alarmas Networker Diario: ID:{json_content['id_unique']} -> {json_content['subject']} --> {json_content['host']}",
        "description": json_content["subject"],
        # Une el contenido del cuerpo del correo como información adicional
        "additional_information": "\n".join([f"{clave}: {valor}" for clave, valor in body_content.items()]),
        "project": {"id": 9},  # ID del proyecto en Mantis
        "handler": {"name": handler_name},
        "category": {"name": "General"},
        "priority": {"name": "alta"},
        "custom_fields": [
            {"field": {"id": 1, "name": "Host"}, "value": json_content['host']},
            {"field": {"id": 2, "name": "id_unique"}, "value": json_content['id_unique']},
            {"field": {"id": 3, "name": "Target_Lifecycle_Status"}, "value": json_content['NSR_Protection_Group']},
            {"field": {"id": 4, "name": "Event_Name"}, "value": json_content['Succeeded']},
            {"field": {"id": 5, "name": "Rule_Name"}, "value": json_content['networker_status']},
            {"field": {"id": 6, "name": "Date_llegada"}, "value": json_content['date']},
            {"field": {"id": 7, "name": "Fecha_creacion"}, "value": json_content['creation_date']}
        ]
    }
    
    headers = {
        "cookie": "PHPSESSID=0taolevemh4k50psm684qa2qri; MANTIS_PROJECT_COOKIE=0",
        "Content-Type": "application/json",
        "Authorization": "jWma-n55OtqOd1j_HuS85LPRrWsdE-40"  # Token de autenticación de MantisBT
    }
    
    try:
        response = requests.post(url_mn, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 201:
            response_data = response.json()
            issue_id = response_data.get('issue', {}).get('id')
            print(f"Ticket creado en MantisBT: {issue_id}")
            return issue_id
        else:
            print(f"Error al crear el resumen en MantisBT: {response.status_code} - {response.text}")
            alarmas_erroneas += 1
            return 0
            
    except Exception as e:
        print(f"Error al enviar datos a MantisBT: {e}")
        alarmas_erroneas += 1
        return 0


# Función para agregar notas (se mantiene por si se necesita, aunque no se usa en el flujo principal)
def add_mantis_note(mantisid, note_text):
    """Agrega una nota a un ticket de MantisBT existente."""
    url = f"http://172.32.1.51:10090/api/rest/issues/{mantisid}/notes"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "jWma-n55OtqOd1j_HuS85LPRrWsdE-40"
    }
    data = {"text": note_text}
    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        return response.status_code == 201
    except requests.RequestException as e:
        print(f"Error agregando nota en Mantis: {e}")
        return False

# --- FUNCIONES DE MANEJO DE BASE DE DATOS ---

def create_connection():
    """Establece la conexión con la base de datos MySQL."""
    try:
        connection = mysql.connector.connect(
            host="172.32.1.51",
            user="zabbixuser",
            password="zabbix",
            # IMPORTANTE: Reemplazar con el nombre de su base de datos real
            database="your_database_name" 
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Error al conectar a la base de datos: {err}")
        return None

def clean_string(input_string):
    """Limpia cadenas de caracteres eliminando HTML, URLs, saltos de línea y otros caracteres no deseados."""
    # Eliminar etiquetas HTML
    result = re.sub(r'<[^>]+>', '', input_string)
    # Eliminar URLs
    result = re.sub(r'http[s]?://\S+', '', result)
    result = re.sub(r'www\.\S+', '', result)
    result = re.sub(r'mailto:\S+', '', result)
    # Eliminar saltos de línea y otros caracteres de control
    result = re.sub(r'(\r\n|\r|\n|\t|\\|")', ' ', result)
    # Eliminar tuberías
    result = re.sub(r'\|', '', result)
    return result.strip()
    
def crear_data_to_db(connection, json_content, issue_data):
    """Inserta los datos limpios en la tabla GPF_respaldos_Networker2."""
    global alarmas_nuevas, alarmas_erroneas, operador_siglas
    
    try:
        cursor = connection.cursor()
        insert_query = (
            "INSERT INTO GPF_respaldos_Networker2 (id_unique, sender, subject, host, hostserver, Sistema, "
            "NSR_Protection_Group, Succeeded, networker_status, date, Alarma, hora, "
            "creation_date,ubicacion,dia,mes,year,mantisid,siglas,grupo) "
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
            issue_data, # ID de Mantis o 0
            operador_siglas,
            json_content["grupo"]
        ))
        connection.commit()
        
        # Incrementar el contador de alarmas nuevas si la inserción fue exitosa
        alarmas_nuevas += 1
        print("Datos insertados correctamente en la BDD.")
        
    except mysql.connector.Error as err:
        print(f"Error de base de datos al insertar datos: {err}")
        alarmas_erroneas += 1

    
def insert_data_to_db(connection, json_content, body_content):
    """
    Verifica si la alarma es duplicada y decide si crear el ticket en MantisBT 
    y guardar en la BDD.
    """
    global alarmas_nuevas, alarmas_antiguas, alarmas_erroneas

    try:
        cursor = connection.cursor(buffered=True)
        # 1. Verifica si la combinación id_unique y subject ya existe
        check_query_inicial = (
            "SELECT COUNT(*) FROM GPF_respaldos_Networker2 WHERE id_unique = %s AND subject = %s LIMIT 1"
        )
        cursor.execute(check_query_inicial, (json_content['id_unique'], json_content["subject"]))
        result = cursor.fetchone()
        
        if result[0] > 0:
            # Alarma antigua/duplicada
            print(f"Alarma duplicada encontrada: {json_content['id_unique']}")
            alarmas_antiguas += 1
        else:
            # Alarma nueva: procesar
            issue_data = 0
            
            # 2. Si el estado es 'Failed', crear el ticket en MantisBT
            if json_content["Succeeded"] == "Failed":
                print(f"Alarma de FALLO detectada. Creando ticket MantisBT para ID: {json_content['id_unique']}")
                issue_data = create_mantis_summary(json_content, body_content)
                
            # 3. Insertar datos en la base de datos (independientemente del estado)
            crear_data_to_db(connection, json_content, issue_data)

    except mysql.connector.Error as err:
        print(f"Error de base de datos en el proceso de verificación: {err}")
        alarmas_erroneas += 1

# --- FUNCIONES DE PARSEO DE EMAIL ---

def parse_email_body(body):
    """Extrae campos clave como 'NSR Protection Group', 'Succeeded' y 'networker_status' del cuerpo del correo."""
    parsed_content = {}
    lines = re.split(r'(\r\n|\r|\n)', body)
    networker_status_found = False
    
    for line in lines:
        if ':' in line and not networker_status_found:
            parts = line.split(':', 1)
            key = clean_string(parts[0].strip())
            value = clean_string(parts[1].strip())
            # Solo capturamos estos campos antes de la línea de estado
            if key in ["NSR Protection Group", "Succeeded"] and value:
                parsed_content[key] = value
        
        # Buscar el estado de Networker
        if "--- Successful" in line or "--- Unsuccessful" in line:
            status_line = clean_string(line)
            parsed_content["networker_status"] = status_line
            networker_status_found = True
            
    if not networker_status_found:
        parsed_content["networker_status"] = "--Revisar correo--"
        
    return parsed_content

# --- LÓGICA PRINCIPAL ---

if __name__ == "__main__":
    
    connection = None
    outlook = None
    namespace = None
    
    try:
        # Inicializar variables de operador
        operador = get_operador()
        operador_siglas = get_operador_siglas()
        
        # Conexión a Outlook
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        # Asegúrate de que esta ruta de carpeta sea correcta
        folder = namespace.Folders.Item("monitoreosistemas@corporaciongpf.com").Folders.Item("Respaldos").Folders.Item("Diario")
        
        if not folder:
            print("Error: Carpeta de Outlook no encontrada. Revise la ruta.")
            exit()

        # Ordenar los ítems por tiempo de recepción descendente
        folder.Items.Sort("[ReceivedTime]", True)
        
        # Conexión a la base de datos
        connection = create_connection()
        if connection is None:
            print("Error: Falló la conexión a la base de datos. Terminando script.")
            exit()
            
        mails_to_process = 30 # Número de correos a procesar, ajustado al inicio de la lista
        total_emails = folder.Items.Count
        
        # Calcular el índice inicial para procesar los N correos más recientes
        # La colección de items de Outlook es 1-based.
        start_index = max(1, total_emails - mails_to_process + 1) 
        end_index = total_emails
        
        print(f"Iniciando procesamiento de los últimos {min(mails_to_process, total_emails)} correos (Índices {start_index} a {end_index})...")

        # Iterar sobre los correos más recientes (de más antiguo a más reciente entre los N)
        for i in tqdm(range(start_index, end_index + 1), desc="Procesando correos", unit="correo"):
            
            mail_item = folder.Items.Item(i)
            ubicacion_mail = i
            
            if isinstance(mail_item, win32com.client.CDispatch):
                
                body_content = parse_email_body(mail_item.Body)
                
                # Extracción de campos
                host = clean_string(mail_item.Subject).replace("NetWorker - ", "")
                hostserver = mail_item.Subject
                fecha_completa = mail_item.ReceivedTime.strftime('%Y-%m-%d %H:%M:%S')
                # Utiliza timestamp como ID único para el correo
                id_unique = int(time.mktime(mail_item.ReceivedTime.timetuple())) 
                
                # Datos de fecha/tiempo
                hora = mail_item.ReceivedTime.strftime('%H')
                dia = mail_item.ReceivedTime.strftime('%d')
                mes = mail_item.ReceivedTime.strftime('%m')
                year = mail_item.ReceivedTime.strftime('%Y')
                
                # Lógica para determinar el grupo y el estado del respaldo
                string_protection_group = body_content.get("NSR Protection Group", "")
                grupo = string_protection_group.replace(" completed", "")
                
                status = body_content.get("networker_status", "")
                if "Unsuccessful" in status:
                    final_status = "Failed"
                elif "Successful" in status:
                    final_status = "OK"
                elif "Revisar correo" in status:
                    final_status = "SD"
                else:
                    final_status = "SD"

                json_content = {
                    "operador": operador, # Se incluye el nombre del operador para MantisBT
                    "id_unique": id_unique,
                    "ubicacion": ubicacion_mail,
                    "sender": clean_string(mail_item.SenderEmailAddress),
                    "subject": clean_string(mail_item.Subject),
                    "host": host,
                    "hostserver": hostserver,
                    "Sistema": "Networkerv Diario",
                    "NSR_Protection_Group": string_protection_group,
                    "grupo": grupo,
                    "Succeeded": final_status,
                    "networker_status": body_content.get("networker_status", ""),
                    "date": fecha_completa,
                    "hora": hora,
                    "dia": dia,
                    "mes": mes,
                    "year": year,
                    "creation_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # Llamada a la función principal de inserción/verificación
                insert_data_to_db(connection, json_content, body_content)

        
        print("\n--- RESUMEN DEL PROCESAMIENTO ---")
        print(f"Alarmas Nuevas Procesadas: {alarmas_nuevas}")
        print(f"Alarmas Antiguas/Duplicadas: {alarmas_antiguas}")
        print(f"Alarmas con Errores: {alarmas_erroneas}")
        print("---------------------------------")


        # --- ENVÍO DE CONTADORES A ZABBIX ---
        alarmas_json = json.dumps({
            "alarmasnuevas": alarmas_nuevas,
            "alarmasantiguas": alarmas_antiguas,
            "alarmaserroneas": alarmas_erroneas
        })
        escaped_json = alarmas_json.replace('"', '\\"')

        zabbix_sender_command = (
            'C:\\zabbix\\bin\\zabbix_sender.exe -z 172.32.1.50 -s "172.32.1.51" '
            '-k "gpf_cloud_alarmas" -o "{json_data}"'.format(json_data=escaped_json)
        )
        
        print("Enviando contadores a Zabbix...")
        # Ejecutar el comando de Zabbix Sender
        os.system(zabbix_sender_command)
        print("Envío a Zabbix completado.")

    except Exception as e:
        print(f"Ocurrió un error inesperado en el script principal: {e}")

    finally:
        # Cierre de conexiones y liberación de objetos
        if connection:
            connection.close()
            print("Conexión a la base de datos cerrada.")
        if namespace:
            del namespace
        if outlook:
            del outlook
            print("Objetos de Outlook liberados.")