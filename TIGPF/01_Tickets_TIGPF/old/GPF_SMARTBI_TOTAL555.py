import os
import mysql.connector
import win32com.client
from tqdm import tqdm
from datetime import datetime
import requests
import re
import json
import subprocess

# Configuración de Zabbix
zabbix_server = "172.32.1.50"
host_name = "Server_Correos"  # Cambia esto al nombre de host configurado en tu Zabbix server
key_name = "GPF.smartbi"  # Cambia esto a la clave configurada en tu Zabbix server
zabbix_sender_path = "C:\\zabbix\\bin\\zabbix_sender.exe"
zabbix_port = "10051"

# Configuración de la base de datos
DB_HOST = os.getenv("DB_HOST", "172.32.1.51")
DB_USER = os.getenv("DB_USER", "zabbixuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "zabbix")
DB_NAME = os.getenv("DB_NAME", "your_database_name")
TABLE_NAME = "GPF_SMARTBI"

# Configuración de MantisBT
MANTIS_URL = "http://172.32.1.51:10090/api/rest/issues"
MANTIS_AUTH_TOKEN = "B6knU4vQYh9bSx-ukxmlcS9PgqcqOLTy"

def clean_hyperlinks(text):
    """Eliminar hipervínculos del texto."""
    return re.sub(r'http\S+', '', text)

def obtener_unix_time(fecha_str, formato="%d/%m/%Y %H:%M:%S"):
    """Obtener Unix Time de una fecha."""
    try:
        return int(datetime.strptime(fecha_str, formato).timestamp())
    except ValueError:
        print(f"Error al convertir fecha: {fecha_str}")
        return 0

def get_operador():
    """Obtener el operador desde un servicio externo."""
    url = "http://172.32.1.51/usuario/data.php"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.text.strip() + " "
        print(f"Error al obtener operador: {response.status_code}")
    except requests.RequestException as e:
        print(f"Error al obtener operador: {e}")
    return "oscar.guerra@sonda.com"

def add_mantis_note(mantisid, note_text):
    url = f"http://172.32.1.51:10090/api/rest/issues/{mantisid}/notes"
    headers = {
        "Content-Type": "application/json",
        "Authorization": MANTIS_AUTH_TOKEN
    }
    data = {"text": note_text}
    try:
        response = requests.post(url, json=data, headers=headers)
        return response.status_code == 201
    except requests.RequestException as e:
        print(f"Error agregando nota en Mantis: {e}")
        return False

def create_mantis_summary(json_content):
    """Crear un ticket en MantisBT."""
    operador = get_operador()
    payload = {
        "summary": f"Alarmas GPF SMARTBI: ID:{json_content['id_unique']} => {json_content['source']} -> {json_content['asunto']}",
        "description": json_content['subscription_id'],
        "project": {"id": 19},
        "handler": {"name": operador},
        "category": "General",
        "priority": {"name": "alta"},
        "custom_fields": [
            {"field": {"id": 1, "name": "Host"}, "value": json_content["source"]},
            {"field": {"id": 2, "name": "id_unique"}, "value": json_content["id_unique"]},
            {"field": {"id": 4, "name": "Event_Name"}, "value": json_content["azure_vault"]},
            {"field": {"id": 5, "name": "Rule_Name"}, "value": json_content["source_type"]},
            {"field": {"id": 9, "name": "IP"}, "value": json_content["source"]},
            {"field": {"id": 6, "name": "Date_llegada"}, "value": json_content["fecha_llegada"]},
            {"field": {"id": 7, "name": "Fecha_creacion"}, "value": json_content["fecha_creacion"]},
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": MANTIS_AUTH_TOKEN,
    }
    try:
        response = requests.post(MANTIS_URL, json=payload, headers=headers)
        response.raise_for_status()
        return response.json().get('issue', {}).get('id')
    except requests.RequestException as e:
        print(f"Error al crear ticket en MantisBT: {e}")
        return None

def procesar_cuerpo_correo(correo):
    """Procesar el cuerpo del correo y extraer datos clave."""
    try:
        asunto = correo.Subject or ""

        # Ignorar correos que comiencen con "RE:"
        if asunto.startswith("RE:"):
            return None

        remitente = correo.SenderEmailAddress or ""
        fecha = correo.ReceivedTime.strftime('%Y-%m-%d %H:%M:%S')
        body = re.sub(r'<[^>]*>', '', correo.Body or "").strip()
        body = re.sub(r'\n\s*\n', '\n', body)

        azure_vault = ""
        if "se ha realizado satisfactoriamente" in body or "ha finalizado correctamente" in body:
            azure_vault = "OK"
        elif "ha fallado" in body:
            azure_vault = "ERROR"

        source = ""
        keywords = ["modelo comercial DWH", "CARGA_INVENTARIO", "CARGA_STOCK", "CARGA_FUNC_TUKUNA", "modelo comercial Tukuna"]
        for keyword in keywords:
            if keyword in body:
                source = keyword
                break
        source_type = ""
        keywords1 = ["transaccional Tukuna - Comercial", "Stock", "Inventario DWH", "Comercial DWH", "presupuestos de convenios", "Comercial DWH"]
        for keyword1 in keywords1:
            if keyword1 in asunto:
                source_type = keyword1
                if source_type == "presupuestos de convenios":
                    source = "presupuestos de convenios"
                break

        fecha_creacion = datetime.now()

        data = {
            "asunto": asunto,
            "remitente": remitente,
            "fecha_llegada": fecha,
            "id_unique": obtener_unix_time(fecha, "%Y-%m-%d %H:%M:%S"),
            "subscription_id": body,
            "subscription_name": 0,
            "azure_vault": azure_vault,
            "source": source,
            "source_type": source_type,
            "time": 0,
            "fecha_creacion": fecha_creacion.strftime('%Y-%m-%d %H:%M:%S'),
            "amenaza": 0,
            "estado": azure_vault,
        }
        return data
    except Exception as e:
        print(f"Error procesando cuerpo del correo: {e}")
        return None

def conectar_base_datos():
    """Establecer conexión a la base de datos."""
    try:
        return mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
        )
    except mysql.connector.Error as err:
        print(f"Error al conectar a la base de datos: {err}")
        return None

def verificar_registro_existente(cursor, id_unique):
    """Verificar si un registro ya existe en la base de datos."""
    query = f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE id_unique = %s"
    cursor.execute(query, (id_unique,))
    return cursor.fetchone()[0] > 0

def almacenar_en_base_datos(connection, data):
    """Almacenar datos en la base de datos y crear ticket si es necesario."""
    try:
        cursor = connection.cursor()

        # Verificar si el registro ya existe
        if verificar_registro_existente(cursor, data["id_unique"]):
            return  # No almacenar registros duplicados

        # Insertar el nuevo registro
        cursor.execute(
            f"""
            INSERT INTO {TABLE_NAME} 
            (id_unique, subscription_id, subscription_name, azure_vault, source, source_type, time, fecha_creacion, asunto, remitente, fecha_llegada, cause_index) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                data["id_unique"],
                data["subscription_id"],
                data["subscription_name"],
                data["azure_vault"],
                data["source"],
                data["source_type"],
                data["time"],
                data["fecha_creacion"],
                data["asunto"],
                data["remitente"],
                data["fecha_llegada"],
                1,  # Cause index inicial
            ),
        )
        connection.commit()

        # Verificar si hay un mantisid existente
        cursor.execute(
            f"SELECT mantisid FROM {TABLE_NAME} WHERE id_unique = %s AND cause_index = 1",
            (data["id_unique"],),
        )
        result_check = cursor.fetchone()

        if not result_check or not result_check[0]:  # No existe mantisid
            if data["azure_vault"] == "ERROR":
                mantisid = create_mantis_summary(data)
                if mantisid:
                    add_mantis_note(mantisid, "Alarma creada.")
                    cursor.execute(
                        f"UPDATE {TABLE_NAME} SET mantisid = %s WHERE id_unique = %s",
                        (mantisid, data["id_unique"]),
                    )
                    connection.commit()
        else:  # Actualizar nota si existe
            mantisid = result_check[0]
            add_mantis_note(mantisid, "Alarma actualizada.")

    except KeyError as e:
        print(f"Faltan claves en los datos de entrada: {e}")
    except mysql.connector.Error as err:
        print(f"Error al almacenar en la base de datos: {err}")
    except Exception as ex:
        print(f"Error inesperado: {ex}")

def procesar_correos_outlook(cantidad_a_leer):
    """Procesar los últimos correos de Outlook con barra de progreso."""
    try:
        # Conectar a Outlook
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        folder = namespace.Folders.Item("monitoreosistemas@corporaciongpf.com").Folders.Item("SMART BI")

        if not folder:
            print("Carpeta no encontrada.")
            return []

        # Ordenar los correos por fecha de recepción descendente (más recientes primero)
        items = folder.Items
        items.Sort("[ReceivedTime]", True)

        # Leer los correos más recientes
        cantidad_a_leer = min(cantidad_a_leer, items.Count)
        correos = [items.Item(i+1) for i in range(cantidad_a_leer)]  # Los primeros n correos más recientes

        correos_procesados = []
        for correo in tqdm(correos, desc="Procesando correos", unit="correo"):
            datos_correo = procesar_cuerpo_correo(correo)
            if datos_correo:
                correos_procesados.append(datos_correo)

        return correos_procesados
    except Exception as e:
        print(f"Error procesando correos: {e}")
        return []

def enviar_datos_a_zabbix(data):
    """
    Enviar datos formateados a Zabbix directamente desde el JSON en memoria.
    """
    try:
        for key, value in data.items():
            # Formatear la clave y el valor para zabbix_sender
            command = [
                zabbix_sender_path,
                '-z', zabbix_server,
                '-p', zabbix_port,
                '-s', host_name,  # Host configurado en Zabbix
                '-k', f"{key_name}.{key}",  # Clave de la métrica
                '-o', str(value),  # Valor de la métrica
            ]

            print(f"Ejecutando comando: {' '.join(command)}")

            # Ejecutar el comando usando subprocess
            result = subprocess.run(command, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"Métrica {key} enviada exitosamente a Zabbix con valor {value}.")
            else:
                print(f"Error al enviar métrica {key}. Código de retorno: {result.returncode}")
                print(f"Salida estándar: {result.stdout}")
                print(f"Salida de error: {result.stderr}")

    except Exception as e:
        print(f"Error al enviar datos a Zabbix: {e}")



def registrar_estadisticas(stats):
    """Registrar estadísticas en un archivo JSON."""
    estadisticas = stats
    try:
        with open("estadisticas.json", "w") as file:
            json.dump(estadisticas, file, indent=4)
        print("Estadísticas registradas en 'estadisticas.json'")
    except Exception as e:
        print(f"Error al registrar estadísticas: {e}")


if __name__ == "__main__":
    connection = conectar_base_datos()
    if connection:
        try:
            correos = procesar_correos_outlook(50)  # Leer los últimos 50 correos
            total_correos = len(correos)
            print(f"Total de correos a procesar: {total_correos}")

            almacenados = 0
            no_almacenados = 0
            alarmas_creadas = 0
            precreados = 0

            for correo in tqdm(correos, desc="Almacenando en base de datos", unit="correo", total=total_correos):
                try:
                    if verificar_registro_existente(connection.cursor(), correo["id_unique"]):
                        precreados += 1
                    else:
                        almacenar_en_base_datos(connection, correo)
                        almacenados += 1

                        if correo["azure_vault"] == "ERROR":
                            alarmas_creadas += 1
                except Exception as e:
                    print(f"Error al procesar correo: {e}")
                    no_almacenados += 1

            # Registrar estadísticas
            stats = {
                "correos_totales": total_correos,
                "correos_almacenados": almacenados,
                "correos_no_almacenados": no_almacenados,
                "alarmas_creadas": alarmas_creadas,
                "correos_precreados": precreados,
            }
            print(stats)
            registrar_estadisticas(stats)

            # Enviar estadísticas a Zabbix
            enviar_datos_a_zabbix(stats)

        finally:
            connection.close()
