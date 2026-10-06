import os
import mysql.connector
import win32com.client
from tqdm import tqdm
from datetime import datetime
import requests
import re
import json
import subprocess

# ==========================================
# CONFIGURACIÓN DE INTEGRACIONES (ZABBIX, DB, MANTIS)
# ==========================================

zabbix_server = "172.32.1.50"
host_name = "Server_Correos"  
key_name = "GPF.hetrix"  
zabbix_sender_path = "C:\\zabbix\\bin\\zabbix_sender.exe"
zabbix_port = "10051"

# Credenciales - Reemplaza con tus datos reales
DB_HOST = os.getenv("DB_HOST", "172.32.1.51")
DB_USER = os.getenv("DB_USER", "zabbixuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "zabbix")
DB_NAME = "your_database_name" 
TABLE_NAME = "GPF_HETRIX"

# Configuración MantisBT
MANTIS_URL = "http://172.32.1.51:10090/api/rest/issues"
MANTIS_AUTH_TOKEN = "B6knU4vQYh9bSx-ukxmlcS9PgqcqOLTy"

# ==========================================
# FUNCIONES DE UTILIDAD Y LIMPIEZA
# ==========================================

def clean_hyperlinks(text):
    """Limpia el cuerpo del correo eliminando enlaces HTTP."""
    return re.sub(r'http\S+', '', text)

def get_operador():
    """Determina a qué operador asignar el ticket mediante el servicio de turnos."""
    url = "http://172.32.1.55:3001/turnos/actual-correo"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.text.strip() + " "
    except:
        pass
    return "oscar.guerra@sonda.com" 

# ==========================================
# GESTIÓN DE TICKETS EN MANTISBT
# ==========================================

def add_mantis_note(mantisid, note_text):
    """Añade una nota de seguimiento (Usado para eventos UP o actualizaciones)."""
    url = f"{MANTIS_URL}/{mantisid}/notes"
    headers = {"Content-Type": "application/json", "Authorization": MANTIS_AUTH_TOKEN}
    try:
        response = requests.post(url, json={"text": note_text}, headers=headers)
        return response.status_code == 201
    except Exception as e:
        print(f"Error nota Mantis: {e}")
        return False

def create_mantis_ticket_inmediato(data):
    """Crea ticket en MantisBT inmediatamente con el body del mail en la descripción."""
    operador = get_operador()
    # Se incluye el body completo procesado en la descripción según tu requerimiento
    payload = {
        "summary": f"Alerta Hetrix DOWN: {data['url_servicio']}",
        "description": f"Detalle obtenido del mail:\n\n{data['body_completo']}",
        "project": {"id": 43},
        "handler": {"name": operador},
        "status": {"id": 50}, # Permanece abierto / estado inicial
        "category": "General",
        "priority": {"name": "high"}
    }
    headers = {"Content-Type": "application/json", "Authorization": MANTIS_AUTH_TOKEN}
    try:
        response = requests.post(MANTIS_URL, json=payload, headers=headers)
        if response.status_code == 201:
            return response.json().get('issue', {}).get('id')
    except Exception as e:
        print(f"Error creando ticket: {e}")
    return None

# ==========================================
# OPERACIONES DE BASE DE DATOS Y ESTADOS
# ==========================================

def conectar_base_datos():
    try:
        return mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    except mysql.connector.Error as err:
        print(f"Error de conexión: {err}")
        return None

def registrar_evento_db(connection, data):
    """Procesa el correo, crea tickets inmediatos para DOWN y notas para UP."""
    cursor = connection.cursor(dictionary=True, buffered=True)
    try:
        # Verificar si el ID único ya existe para evitar duplicados
        cursor.execute(f"SELECT id_unique FROM {TABLE_NAME} WHERE id_unique = %s", (data['id_unique'],))
        if cursor.fetchone():
            return 

        # Buscar evento abierto para esta URL para saber si es una recuperación
        cursor.execute(f"SELECT * FROM {TABLE_NAME} WHERE url_servicio = %s AND fecha_fin IS NULL", (data['url_servicio'],))
        evento_activo = cursor.fetchone()

        if data['estado'] == "DOWN":
            # REGLA: Si detecta DOWN, crea ticket INMEDIATAMENTE
            mid = create_mantis_ticket_inmediato(data)
            
            query_ins = f"""INSERT INTO {TABLE_NAME} 
                            (id_unique, url_servicio, estado_actual, fecha_inicio, fecha_ultimo_update, body_completo, mantisid) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            cursor.execute(query_ins, (data['id_unique'], data['url_servicio'], "DOWN", data['fecha_dt'], data['fecha_dt'], data['body_completo'], mid))
        
        elif data['estado'] == "UP" and evento_activo:
            # REGLA: Si detecta UP, NO cierra el ticket, solo coloca una nota con el nuevo estado
            if evento_activo.get('mantisid'):
                nota_recuperacion = f"SISTEMA RECUPERADO - Nuevo estado: UP detectado a las {data['fecha_dt']}. El ticket permanece abierto para revisión manual."
                add_mantis_note(evento_activo['mantisid'], nota_recuperacion)
            
            # Actualizamos la base de datos para cerrar el ciclo de este evento específico
            query_upd = f"UPDATE {TABLE_NAME} SET estado_actual = 'UP', fecha_fin = %s WHERE id_unique = %s"
            cursor.execute(query_upd, (data['fecha_dt'], evento_activo['id_unique']))
                
        connection.commit()
    finally:
        cursor.close()

# ==========================================
# PROCESAMIENTO DE OUTLOOK
# ==========================================

def procesar_outlook():
    """Lee correos de la carpeta ALERTAS HETRIX y extrae datos."""
    try:
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        folder = outlook.Folders.Item("monitoreosistemas@corporaciongpf.com").Folders.Item("ALERTAS HETRIX")
        target = folder.Folders.Item("Analizados")
        
        items = list(folder.Items)
        items.sort(key=lambda x: x.ReceivedTime)
        
        procesados = []
        for item in items:
            asunto = (item.Subject or "").upper()
            estado = "DOWN" if "DOWN" in asunto else "UP" if "UP" in asunto else None
            
            if estado:
                url = asunto.replace("DOWN - ", "").replace("UP - ", "").strip()
                procesados.append({
                    "id_unique": int(item.ReceivedTime.timestamp()),
                    "url_servicio": url,
                    "estado": estado,
                    "fecha_dt": item.ReceivedTime.replace(tzinfo=None),
                    "body_completo": clean_hyperlinks(item.Body or ""),
                    "obj": item,
                    "target": target
                })
        return procesados
    except Exception as e:
        print(f"Error Outlook: {e}")
        return []

# ==========================================
# FLUJO PRINCIPAL
# ==========================================

if __name__ == "__main__":
    conn = conectar_base_datos()
    if conn:
        try:
            correos = procesar_outlook()
            if correos:
                print(f"Procesando {len(correos)} correos...")
                for c in tqdm(correos):
                    registrar_evento_db(conn, c)
                    c['obj'].Move(c['target']) # Mover a Analizados tras procesar
                print("Ciclo completado con éxito.")
            else:
                print("No se encontraron correos nuevos.")
        finally:
            conn.close()