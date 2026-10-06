import os
import re
import json
import requests
import mysql.connector
import win32com.client
from datetime import datetime
from tqdm import tqdm
import time


# Variables for tracking the counts
global alarmas_nuevas 
global alarmas_antiguas
global alarmas_erroneas
global issue_id
global operador
global operador_siglas

alarmas_nuevas=0
alarmas_antiguas=0
alarmas_erroneas=0




def get_operador():
    url = "http://172.32.1.55:3001/turnos/actual-correo"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return str(response.text).strip() + " "
        else:
            return "oscar.guerra@sonda.com"
    except requests.RequestException as e:
        print(f"Error al obtener el operador: {e}")
        return "oscar.guerra@sonda.com"
        
def get_operador_siglas():
    url = "http://172.32.1.51/usuario/dataSiglas.php"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Elimina los corchetes y las comillas dobles
            siglas = response.text.strip().replace("[", "").replace("]", "").replace('"', '') + " "
            return siglas
        else:
            return "OG"
    except requests.RequestException as e:
        print(f"Error al obtener el operador: {e}")
        return "OG"
        

# Función para actualizar el summary en MantisBT
def update_mantis_summary(mantisid, new_summary):
    url = f"http://172.32.1.51:10090/api/rest/issues/{mantisid}"
    headers = {
        "cookie": "PHPSESSID=0taolevemh4k50psm684qa2qri; MANTIS_PROJECT_COOKIE=0",
        "Content-Type": "application/json",
        "Authorization": "jWma-n55OtqOd1j_HuS85LPRrWsdE-40"  # Token de autenticación de MantisBT
    }   
    data = {
        "summary": new_summary
    }
    response = requests.patch(url, json=data, headers=headers)
    return response.status_code == 200

# Función para actualizar el summary en MantisBT
# Función para actualizar el summary en MantisBT
def create_mantis_summary(json_content, body_content):
    #operador=get_operador()
    url_mn = "http://172.32.1.51:10090/api/rest/issues"
    payload = {
    "summary": f"Alarmas Networker MJS: ID:{json_content['id_unique']} -> {json_content['subject']} --> {json_content['host']}",
    "description": json_content["subject"],
    "additional_information": "\n".join([f"{clave}: {valor}" for clave, valor in body_content.items()]),
    "project": {"id": 9},  # ID del proyecto en Mantis
    "handler": {"name": operador},
    "category": {"name": "General"},
    "priority": {"name": "alta"},
    "custom_fields": [
        {
            "field": {
                "id": 1,  # ID del campo personalizado 'Host' en MantisBT
                "name": "Host"
            },
            "value": json_content['host']  # Valor que se enviará al campo 'Host'
        },
        {
            "field": {
                "id": 2,  # ID del campo personalizado 'Host' en MantisBT
                "name": "id_unique"
            },
            "value": json_content['id_unique']  # Valor que se enviará al campo 'Host'
        },
        {
            "field": {
                "id": 3,  # ID del campo personalizado 'Host' en MantisBT
                "name": "Target_Lifecycle_Status"
            },
            "value": json_content['NSR_Protection_Group']  # Valor que se enviará al campo 'Host'
        },
        {
            "field": {
                "id": 4,  # ID del campo personalizado 'Host' en MantisBT
                "name": "Event_Name"
            },
            "value": json_content['Succeeded']  # Valor que se enviará al campo 'Host'
        },
        {
            "field": {
                "id": 5,  # ID del campo personalizado 'Host' en MantisBT
                "name": "Rule_Name"
            },
            "value": json_content['networker_status']  # Valor que se enviará al campo 'Host'
        },
        {
            "field": {
                "id": 6,  # ID del campo personalizado 'Host' en MantisBT
                "name": "Date_llegada"
            },
            "value": json_content['date']  # Valor que se enviará al campo 'Host'
        },
        {
            "field": {
                "id": 7,  # ID del campo personalizado 'Host' en MantisBT
                "name": "Fecha_creacion"
            },
            "value": json_content['creation_date']  # Valor que se enviará al campo 'Host'
        }
    ]
}
   
    headers = {
        "cookie": "PHPSESSID=0taolevemh4k50psm684qa2qri; MANTIS_PROJECT_COOKIE=0",
        "Content-Type": "application/json",
        "Authorization": "jWma-n55OtqOd1j_HuS85LPRrWsdE-40"  # Token de autenticación de MantisBT
    }
 
    # Aquí puedes hacer la solicitud POST para crear el resumen en MantisBT
    response = requests.post(url_mn, json=payload, headers=headers)
    
    # Manejo de la respuesta
    try:
        if response.status_code == 201:
            #print("Resumen creado exitosamente en MantisBT.")
            response_data = response.json()
            issue_id = response_data.get('issue', {}).get('id')  # Extrae el ID del ticket
            #print(f"Ticket creado en MantisBT: {issue_id}")
            return (issue_id)
        else:
            print(f"Error al crear el resumen: {response.status_code} - {response.text}")
        
    except Exception as e:
        print(f"Error al enviar datos a MantisBT: {e}")
        alarmas_erroneas += 1  # Incrementa alarmas_erroneas






                    



   
    
def add_mantis_note(mantisid, note_text):
    url = f"http://172.32.1.51:10090/api/rest/issues/{mantisid}/notes"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "jWma-n55OtqOd1j_HuS85LPRrWsdE-40"
    }
    data = {"text": note_text}
    try:
        response = requests.post(url, json=data, headers=headers)
        return response.status_code == 201
    except requests.RequestException as e:
        print(f"Error agregando nota en Mantis: {e}")
        return False

def create_connection():
    try:
        connection = mysql.connector.connect(
            host="172.32.1.51",
            user="zabbixuser",
            password="zabbix",
            database="your_database_name"
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

def clean_string(input_string):
    result = re.sub(r'<[^>]+>', '', input_string)
    result = re.sub(r'http[s]?://\S+', '', input_string)  # Eliminar URLs con http/https
    result = re.sub(r'www\.\S+', '', input_string)  # Eliminar URLs que comienzan con www.
    result = re.sub(r'mailto:\S+', '', input_string)  # Eliminar enlaces mailto:
    result = re.sub(r'(\r\n|\r|\n|\t|\\|")', ' ', input_string)  # Eliminar saltos de línea y otros caracteres
    result = re.sub(r'\|', '', result)  # Eliminar tuberías "|"
    return result.strip()
    
    
def crear_data_to_db(connection, json_content, body_content,issue_data):
# Inserta los datos en la base de datos junto con el issue_id de MantisBT
    #operador_siglas=get_operador_siglas()
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
            issue_data,
            operador_siglas,
            json_content["grupo"]
        ))
        connection.commit()

        #alarmas_nuevas += 1  # Incrementa alarmas_nuevas
        #print("Data received and stored with Mantis ticket ID")
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
       # alarmas_erroneas += 1  # Incrementa alarmas_erroneas

    
    
def insert_data_to_db(connection, json_content, body_content):
    global alarmas_nuevas, alarmas_antiguas, alarmas_erroneas  # Necesario para modificar variables globales

    #print("......++++++INICIO++++++++............")
    #print(json_content["id_unique"])    
    #print(json_content["subject"])  
    try:
        cursor = connection.cursor(buffered=True)
        # Verifica si el id_unique ya existe en la base de datos
        check_query_inicial = "SELECT COUNT(*) FROM GPF_respaldos_Networker2 WHERE id_unique = %s AND subject = %s LIMIT  1"
        
        cursor.execute(check_query_inicial, (json_content['id_unique'], json_content["subject"]))
        #print(check_query_inicial)
        
        #cursor.execute(check_query_inicial)
        result = cursor.fetchone()
        #print("......++++++qUERY1++++++++............")
        #print(result)         
       
        if result[0] > 0:
                #print("Duplicate data, no insertion needed")
                alarmas_antiguas += 1  # Incrementa alarmas_antiguas
            
            
        else:
            #print("........RRRRinicioRRRRRRR............")
            #print(json_content["Succeeded"])
            
            if json_content["Succeeded"] == "Failed":
                issue_data = create_mantis_summary(json_content, body_content)
                crear_data_to_db(connection, json_content, body_content, issue_data)
    # print("New data MANTIS")
            else:
                issue_data = 0  # O asigna un valor predeterminado si necesario
                crear_data_to_db(connection, json_content, body_content, issue_data)
            
            
            
           
            # check_query_check = "SELECT mantisid FROM GPF_respaldos_Networker WHERE id_unique = %s and id_unique= %s"
            # cursor.execute(check_query_check, (json_content['id_unique'], json_content["id_unique"]))
            # result_check = cursor.fetchone()
            # if result_check is  None:
                # print("en base de datos notas")
                # print("++++++++++++++++++++++++++")
                #print("New dataBDD")
                
                
            # else:
                #print("actualizacion mantisbt Notes, no insertion needed")
                #print("........333...............")
                # mantisid=result_check[0]
                # new_summary=f"Alarmas Networker: ID:{json_content['id_unique']} -> {json_content["subject"]} --> {json_content['host']}"
                #update_mantis_summary(mantisid, new_summary)
                #note_text=json_content["subject"]+"  --->  "+json_content['date']+"  ----> "+json_content['creation_date']
                # add_mantis_note(mantisid, note_text)
                #print("New data repeat, no insertion needed")
                # crear_data_to_db(connection, json_content, body_content, mantisid)               
            
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        alarmas_erroneas += 1  # Incrementa alarmas_erroneas    
            
            
            
                
            
            
    
    

              
                

    


        
    


def format_event_reported_time(time_string):
    try:
        parsed_time = parser.parse(time_string)
        return parsed_time.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        print(f"Error parsing 'Event reported time': {e}")
        return time_string

def clean_file_name(file_name):
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in invalid_chars:
        file_name = file_name.replace(char, '_')
    return file_name

def escape_json(json_string):
    json_string = json_string.replace("\\", "\\\\")
    json_string = json_string.replace("\"", "\\\"")
    return json_string

def parse_email_body(body):
    parsed_content = {}
    lines = re.split(r'(\r\n|\r|\n)', body)
    networker_status_found = False
    for line in lines:
        if ':' in line:
            parts = line.split(':', 1)
            key = clean_string(parts[0].strip())
            value = clean_string(parts[1].strip())
            if key in ["NSR Protection Group", "Succeeded"] and value:
                parsed_content[key] = value
        elif "--- Successful" in line or "--- Unsuccessful" in line:
            status_line = clean_string(line)
            parsed_content["networker_status"] = status_line
            networker_status_found = True
    if not networker_status_found:
        parsed_content["networker_status"] = "--Revisar correo--"
    return parsed_content

try:
    operador=get_operador()
    operador_siglas=get_operador_siglas()
    outlook = win32com.client.Dispatch("Outlook.Application")
    namespace = outlook.GetNamespace("MAPI")
    folder = namespace.Folders.Item("monitoreosistemas@corporaciongpf.com").Folders.Item("Respaldos").Folders.Item("Mar-Jue-Sab")
    folder.Items.Sort("[ReceivedTime]", True)
    if not folder:
        print("Carpeta no encontrada.")
        exit()

    curl_file_name = "C:\\zabbix\\correo\\GPF\\NetWorker\\curl_commands.txt"
    
    with open(curl_file_name, 'w') as curl_file:
        mails=20
        total_emails = min(mails, folder.Items.Count)
        connection = create_connection()
        
        #folder.Items.Sort("[ReceivedTime]", False)

        
        if connection is None:
            print("Database connection failed")
            exit()
        
       
        for i in tqdm(range(0, total_emails + 1), desc="Procesando correos", unit="correo"):
            
            if folder.Items.Count - i >= 0:
                element=(folder.Items.Count-mails)
                mail_item = folder.Items.Item(element + i)
                ubicacion_mail=element + i
                
                #print(i)
                #print(folder.Items.Count - i)
                #print(total_emails)
                
                if isinstance(mail_item, win32com.client.CDispatch):
                    email_content = f"De: {mail_item.SenderName}\nAsunto: {mail_item.Subject}\nFecha: {mail_item.ReceivedTime}\nCuerpo: {clean_string(mail_item.Body)}\n\n"

                    # year_folder = f"C:\\zabbix\\correo\\GPF\\Networker\\{mail_item.ReceivedTime.strftime('%Y')}"
                    # month_folder = f"{year_folder}\\{mail_item.ReceivedTime.strftime('%m')}"
                    # day_folder = f"{month_folder}\\{mail_item.ReceivedTime.strftime('%d')}"

                    # try:
                        # if not os.path.exists(year_folder):
                            # os.makedirs(year_folder)
                        # if not os.path.exists(month_folder):
                            # os.makedirs(month_folder)
                        # if not os.path.exists(day_folder):
                            # os.makedirs(day_folder)
                    # except OSError as e:
                        # print(f"Error creando directorios: {e}")
                        # continue

                    # base_file_name = f"{day_folder}\\email_{mail_item.ReceivedTime.strftime('%Y-%m-%d_%H-%M-%S')}_{clean_file_name(mail_item.Subject)}"
                    # json_file_name = f"{base_file_name}.json"

                    body_content = parse_email_body(mail_item.Body)
                    
                    #print(body_content)
                    
                    
                    
                    # Extraer el host del subject
                    host = clean_string(mail_item.Subject).replace("NetWorker - ", "")
                    hostserver= mail_item.Subject
                    # bdd_items = ''#parse_bdd(bdd)
                    
                    fecha_completa = mail_item.ReceivedTime.strftime('%Y-%m-%d %H:%M:%S')
                    id_unique = int(time.mktime(mail_item.ReceivedTime.timetuple()))
                    
                    hora = mail_item.ReceivedTime.strftime('%H')
                    dia = mail_item.ReceivedTime.strftime('%d')
                    mes = mail_item.ReceivedTime.strftime('%m')
                    year = mail_item.ReceivedTime.strftime('%Y')
                    
                    string = body_content.get("NSR Protection Group", "")
                    grupo = string.replace(" completed", "")
                    
                
                    status = body_content.get("networker_status", "")
                    if "Unsuccessful" in status:
                        status = "Failed"
                    elif "Successful" in status:
                        status = "OK"
                    elif "Revisar correo" in status:
                        status = "SD"


                    json_content = {
                        "id_unique": id_unique,
                        "ubicacion": ubicacion_mail,
                        "sender": clean_string(mail_item.SenderEmailAddress),
                        "subject": clean_string(mail_item.Subject),
                        "host": host,
                        "hostserver": hostserver,
                        "Sistema": "Networker MJS",
                        "NSR_Protection_Group": body_content.get("NSR Protection Group", ""),
                        "grupo":grupo,
                        "Succeeded": status,
                        "networker_status": body_content.get("networker_status", ""),
                        "date": fecha_completa,
                        "hora": hora,  # Aquí agregamos la nueva variable con la hora
                        "dia": dia,  # Aquí agregamos la nueva variable con la hora
                        "mes": mes,  # Aquí agregamos la nueva variable con la hora
                        "year": year,  # Aquí agregamos la nueva variable con la hora
                        "creation_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    # Insert data into the database
                    
                    
                    #print(json_content)
                    insert_data_to_db(connection, json_content,body_content)

                    # try:
                        # with open(json_file_name, 'w') as json_file:
                            # json.dump(json_content, json_file, ensure_ascii=False, indent=4)
                    # except Exception as e:
                        # print(f"Error al escribir el archivo JSON {json_file_name}: {e}")

                    # Enviar los datos JSON al servidor
                   

    # Crear el contenido JSON con los contadores de alarmas
  
    # Enviar el JSON a Zabbix usando zabbix_sender
    try:
    # Crear el JSON con el formato solicitado
        alarmas_json = json.dumps({
            "alarmasnuevas": alarmas_nuevas,
            "alarmasantiguas": alarmas_antiguas,
            "alarmaserroneas": alarmas_erroneas
        })
        escaped_json = alarmas_json.replace('"', '\\"')

    # Comando para zabbix_sender, enviando el JSON serializado
        zabbix_sender_command = (
            'C:\\zabbix\\bin\\zabbix_sender.exe -z 172.32.1.50 -s "172.32.1.51" '
            '-k "gpf_cloud_alarmas" -o "{json_data}"'.format(json_data=escaped_json)
        )
    
    # Ejecutar el comando
        os.system(zabbix_sender_command)
    except Exception as e:
        print(f"Error al enviar los datos a Zabbix: {e}")

except Exception as e:
    print(f"Ocurrió un error: {e}")

finally:
    if connection:
        connection.close()
    del namespace
    del outlook
