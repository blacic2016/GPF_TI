# --------------------------------------------------------------------------
# SCRIPT: 00_GPF_PDC_mail.py
# DESCRIPCIÓN: Script de ingesta y análisis de reportes diarios de tickets
#              de analistas (TI_GPF). Procesa archivos Excel desde Outlook,
#              extrae datos estructurados de especialistas y grupos, y los
#              almacena en la base de datos MySQL 'TI_GPF'.
# --------------------------------------------------------------------------

import os
import sys
import sqlite3
import win32com.client
import pandas as pd
import db
from datetime import datetime, time, date
from tqdm import tqdm
import json
import pytz

# Configurar encoding UTF-8 para stdout si es posible en Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def get_fecha_ecuador():
    """Retorna la fecha y hora actual en zona horaria de Ecuador (America/Guayaquil, UTC-5)."""
    tz_ec = pytz.timezone("America/Guayaquil")
    return datetime.now(tz_ec).strftime("%Y-%m-%d %H:%M:%S")

# PASO 1.2: Configuración de parámetros de conexión a la Base de Datos SQLite.
DB_PATH = db.DB_PATH
DB_ARCHIVOS_TABLE = db.DB_ARCHIVOS_TABLE
DB_DATA_TABLE = db.DB_DATA_TABLE

# PASO 1.3: Configuración del entorno y carpetas de Outlook.
OUTLOOK_MAILBOX = os.getenv("OUTLOOK_MAILBOX", "g_automatizaciones@corporaciongpf.com")
SOURCE_FOLDER_PATH = ["TI_GPF"]
PROCESSED_FOLDER_NAME = "TIGPF Procesados"
REVISADO_FOLDER_NAME = "Revisado"

# PASO 1.4: Configuración de filtros para adjuntos y almacenamiento local.
REQUIRED_SUBJECT = "Reporte Diario tickets Analistas"
NEW_ATTACHMENT_PREFIX = "ReporteTicketsAnalistas_"
IOC_FOLDER_NAME = "ioc"

# PASO 1.5: Configuración de horarios esperados para análisis diario.
HORARIOS_ESPERADOS = {
    time(8, 0): (time(8, 0), time(8, 10)),
    time(12, 0): (time(12, 0), time(12, 10)),
    time(16, 0): (time(16, 0), time(16, 10)),
    time(20, 0): (time(20, 0), time(20, 10)),
}

PROCESSED_WINDOWS_TODAY = set()

def registrar_log_ejecucion_json(estado="EXITO", detalle="Ejecución completada", metricas=None):
    """
    PASO 1.6: Registra la información de la ejecución actual en estadisticas.json.
    """
    try:
        if metricas:
            actividad_total = sum(metricas.values())
            if actividad_total == 0:
                print(" [LOG] No se registraron correos ni eventos en esta ejecucion. Omitiendo actualizacion de estadisticas.json.")
                return

        estadisticas_file = "estadisticas.json"
        ejecuciones = []
        
        if os.path.exists(estadisticas_file):
            try:
                with open(estadisticas_file, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        ejecuciones = content
            except Exception:
                ejecuciones = []

        resumen_actual = {
            "correos_totales": metricas.get("correos_totales", 0) if metricas else 0,
            "correos_almacenados": metricas.get("correos_almacenados", 0) if metricas else 0,
            "correos_no_almacenados": metricas.get("correos_no_almacenados", 0) if metricas else 0,
            "correos_no_cumplen_requisitos": metricas.get("correos_no_cumplen_requisitos", 0) if metricas else 0,
            "filas_adjuntadas_bdd": metricas.get("filas_adjuntadas_bdd", 0) if metricas else 0,
            "filas_analizadas_bdd": metricas.get("filas_analizadas_bdd", 0) if metricas else 0,
            "filas_duplicadas_bdd": metricas.get("filas_duplicadas_bdd", 0) if metricas else 0
        }

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        nueva_ejecucion = {
            "fecha_ejecucion": timestamp,
            "estado": estado,
            "detalle": detalle,
            "resumen_estadisticas": resumen_actual
        }
            
        ejecuciones.append(nueva_ejecucion)
        
        with open(estadisticas_file, "w", encoding="utf-8") as f:
            json.dump(ejecuciones, f, indent=4, ensure_ascii=False)
            
    except Exception as e:
        print(f"[ERROR] Error al registrar log de ejecucion en JSON: {e}")


# PASO 2: FUNCIONES DE BASE DE DATOS

def conectar_base_datos():
    """
    PASO 2.1: Establece conexión a la base de datos SQLite TI_GPF.db, inicializando las tablas si no existen.
    """
    print(f"[LOG] Conectando a SQLite Database en '{DB_PATH}'...")
    try:
        connection = db.get_connection()
        print(f"[OK] Conexión a SQLite '{DB_PATH}' exitosa y tablas verificadas.")
        return connection
    except sqlite3.Error as err:
        print(f"[ERROR] Error al conectar a SQLite: {err}")
        return None

def almacenar_metadatos_archivo(db_connection, unique_id, email_subject, email_sender,
                                  nombre_archivo_resultante, fecha_recepcion, estado_analisis):
    """
    PASO 2.2: Almacena los metadatos del archivo procesado en GPF_01_Archivos_Procesados.
    """
    if not db_connection: return
    cursor = db_connection.cursor()
    fecha_ec = get_fecha_ecuador()
    fecha_recepcion_str = fecha_recepcion.strftime("%Y-%m-%d %H:%M:%S") if isinstance(fecha_recepcion, datetime) else str(fecha_recepcion)
    query = f"""
    INSERT OR IGNORE INTO {DB_ARCHIVOS_TABLE}
    (id_unico, asunto_correo, remitente_correo, nombre_archivo_resultante, fecha_recepcion, estado_analisis, fecha_creacion_registro, fecha_creacion)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    try:
        cursor.execute(query, (
            unique_id,
            email_subject,
            email_sender,
            nombre_archivo_resultante,
            fecha_recepcion_str,
            estado_analisis,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            fecha_ec
        ))
        db_connection.commit()
        if cursor.rowcount > 0:
            print(f"[LOG] Metadatos del archivo almacenados. ID Unico: '{unique_id}'.")
        else:
            print(f"[LOG] Metadatos para ID '{unique_id}' ya existen. Ignorando insercion.")
    except sqlite3.Error as err:
        print(f"[ERROR] ERROR SQL al insertar metadatos: {err}")
        db_connection.rollback()
    finally:
        cursor.close()

def almacenar_datos_del_archivo(db_connection, data_df, id_unico, fecha_recepcion):
    """
    PASO 2.3: Almacena el DataFrame de datos de analistas en GPF_01_Reporte_Diario_Tickets_Analistas
    incluyendo identificador unico (id_unico), fecha_recepcion del correo y fecha_creacion.
    Retorna tupla (filas_insertadas, filas_duplicadas).
    """
    if not db_connection or data_df.empty: return 0, 0
    cursor = db_connection.cursor()
    total_filas = len(data_df)

    try:
        check_query = f"SELECT COUNT(*) FROM {DB_DATA_TABLE} WHERE id_unico = ?"
        cursor.execute(check_query, (id_unico,))
        exist_count = cursor.fetchone()[0]

        if exist_count > 0:
            print(f"[LOG] Los datos para id_unico '{id_unico}' ya existen en BDD ({exist_count} registros). Omitiendo re-insercion para evitar duplicados.")
            cursor.close()
            return 0, total_filas

        fecha_ec = get_fecha_ecuador()
        fecha_recepcion_str = fecha_recepcion.strftime("%Y-%m-%d %H:%M:%S") if isinstance(fecha_recepcion, datetime) else str(fecha_recepcion)
        query = f"""
        INSERT INTO {DB_DATA_TABLE}
        (id_unico, fecha_recepcion, fecha_creacion, assign_to_group, assign_to_individual, pending, queued, resolved)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """

        rows_to_insert = [
            (
                id_unico,
                fecha_recepcion_str,
                fecha_ec,
                str(row['assign_to_group']),
                str(row['assign_to_individual']),
                int(row['pending']) if pd.notna(row['pending']) else 0,
                int(row['queued']) if pd.notna(row['queued']) else 0,
                int(row['resolved']) if pd.notna(row['resolved']) else 0
            )
            for _, row in data_df.iterrows()
        ]

        cursor.executemany(query, rows_to_insert)
        db_connection.commit()
        count = cursor.rowcount
        cursor.close()

        print(f"[OK] EXITO: Se almacenaron {count} nuevos registros de analistas para id_unico '{id_unico}'.")
        return count, 0
    except sqlite3.Error as err:
        print(f"[ERROR] ERROR SQL al insertar datos: {err}")
        db_connection.rollback()
        return 0, 0


# PASO 3: FUNCIONES DE PROCESAMIENTO DE ADJUNTOS EXCEL

def procesar_adjunto_excel(attachment, ioc_folder_path, reception_date):
    """
    PASO 3.1: Almacena el adjunto Excel en el servidor (directorio /ioc), procesa el contenido estructurado
    de 'Assign To Group', 'Assign To Individual', 'Pending', 'Queued', 'Resolved', descartando filas de 'Total'.
    """
    file_name = attachment.FileName
    print(f"[LOG] Procesando adjunto Excel '{file_name}'.")

    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ['.xlsx', '.xls']:
        print(f"[WARNING] Ignorando adjunto: extension '{ext}' no es Excel valida.")
        return None, None

    timestamp = reception_date.strftime('%Y%m%d%H%M%S')
    new_file_name = f"{NEW_ATTACHMENT_PREFIX}{timestamp}{ext}"
    save_path = os.path.join(ioc_folder_path, new_file_name)

    try:
        attachment.SaveAsFile(save_path)
        print(f"[OK] Adjunto guardado permanentemente en el servidor: '{save_path}'.")
        
        raw_df = pd.read_excel(save_path, header=None)

        if raw_df.empty:
            print("[WARNING] El archivo Excel esta vacio.")
            return None, save_path

        header_idx = None
        for i in range(len(raw_df)):
            row_vals = [str(x).strip() for x in raw_df.iloc[i].tolist()]
            if 'Assign To Group' in row_vals and 'Assign To Individual' in row_vals:
                header_idx = i
                break

        if header_idx is None:
            print("[ERROR] No se encontro la fila de encabezados 'Assign To Group' / 'Assign To Individual'.")
            return None, save_path

        data_df = raw_df.iloc[header_idx + 1:].copy()
        data_df = data_df.iloc[:, :6]
        data_df.columns = ['assign_to_group', 'assign_to_individual', 'pending', 'queued', 'resolved', 'total']

        data_df['assign_to_group'] = data_df['assign_to_group'].ffill()

        rows = []
        for _, row in data_df.iterrows():
            indiv = str(row['assign_to_individual']).strip() if pd.notna(row['assign_to_individual']) else ''
            grp = str(row['assign_to_group']).strip() if pd.notna(row['assign_to_group']) else ''

            # Excluir valores vacíos, NaN y filas de Totales
            if not indiv or indiv.lower() in ['nan', 'none'] or 'total' in indiv.lower() or 'total' in grp.lower():
                continue

            def parse_num(val):
                if pd.notna(val):
                    try:
                        return int(float(str(val).strip()))
                    except ValueError:
                        return 0
                return 0

            rows.append({
                'assign_to_group': grp,
                'assign_to_individual': indiv,
                'pending': parse_num(row['pending']),
                'queued': parse_num(row['queued']),
                'resolved': parse_num(row['resolved'])
            })

        parsed_df = pd.DataFrame(rows)
        if parsed_df.empty:
            print("[WARNING] No se extrajeron filas de datos validas del Excel.")
            return None, save_path

        print(f"[OK] Extraidas {len(parsed_df)} filas estructuradas del reporte Excel.")
        return parsed_df, save_path

    except Exception as e:
        print(f"[ERROR] Error al leer/procesar el archivo Excel '{new_file_name}': {e}")
        return None, save_path


# PASO 4: LÓGICA PRINCIPAL DE PROCESAMIENTO DE CORREOS OUTLOOK

def get_corresponding_window(received_time):
    """
    PASO 4.1: Determina la ventana de monitoreo correspondiente según la hora de recepción.
    """
    received_time_obj = received_time.time()
    window_starts = sorted(HORARIOS_ESPERADOS.keys(), reverse=True)

    for start_time in window_starts:
        if received_time_obj >= start_time:
            return start_time
    return window_starts[-1]

def procesar_correos_outlook(cantidad_a_leer):
    """
    PASO 4.2: Lee la carpeta 'TI_GPF' de Outlook. Valida correos con asunto 'Reporte Diario tickets Analistas'.
    Si cumple requisitos: extrae adjunto Excel, guarda datos en BDD y lo mueve a 'TIGPF Procesados'.
    Caso contrario: lo mueve a 'Revisado'.
    """
    print("\n[LOG] Iniciando ciclo de procesamiento de correos de Outlook.")
    
    metricas_corrida = {
        "correos_totales": 0,
        "correos_almacenados": 0,
        "correos_no_almacenados": 0,
        "correos_no_cumplen_requisitos": 0,
        "filas_adjuntadas_bdd": 0,
        "filas_analizadas_bdd": 0,
        "filas_duplicadas_bdd": 0
    }

    db_connection = conectar_base_datos()
    if not db_connection: return metricas_corrida

    ioc_folder_path = os.path.join(os.getcwd(), IOC_FOLDER_NAME)
    os.makedirs(ioc_folder_path, exist_ok=True)

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        source_folder = namespace.Folders.Item(OUTLOOK_MAILBOX)
        for folder_name in SOURCE_FOLDER_PATH:
            source_folder = source_folder.Folders.Item(folder_name)
        
        # Carpeta para correos procesados exitosamente
        try:
            processed_folder = source_folder.Folders.Item(PROCESSED_FOLDER_NAME)
        except Exception:
            processed_folder = source_folder.Folders.Add(PROCESSED_FOLDER_NAME)

        # Carpeta para correos que no cumplen con los requisitos
        try:
            revisado_folder = source_folder.Folders.Item(REVISADO_FOLDER_NAME)
        except Exception:
            revisado_folder = source_folder.Folders.Add(REVISADO_FOLDER_NAME)

        items = source_folder.Items
        items.Sort("[ReceivedTime]", True)
        num_a_procesar = min(cantidad_a_leer, items.Count)
        metricas_corrida["correos_totales"] = num_a_procesar

        if num_a_procesar == 0:
            print("[LOG] No hay correos en la carpeta para procesar.")
            if db_connection:
                try: db_connection.close()
                except Exception: pass
            return metricas_corrida
        
        print(f"[LOG] Analizando los {num_a_procesar} correos mas recientes en '{SOURCE_FOLDER_PATH[0]}'.")
        correos_a_procesar = [items.Item(i + 1) for i in range(num_a_procesar)]

        for email in tqdm(correos_a_procesar, desc="Procesando correos", unit="correo"):
            subject_matches = REQUIRED_SUBJECT.lower() in email.Subject.lower()
            has_attachment = email.Attachments.Count >= 1

            if not (subject_matches and has_attachment):
                print(f"[WARNING] El correo '{email.Subject}' no cumple con los requisitos. Moviendo a '{REVISADO_FOLDER_NAME}'.")
                try:
                    email.Move(revisado_folder)
                    metricas_corrida["correos_no_cumplen_requisitos"] += 1
                except Exception as e:
                    print(f"[ERROR] ERROR al mover correo a '{REVISADO_FOLDER_NAME}': {e}.")
                continue

            received_time = email.ReceivedTime.replace(tzinfo=None)
            unique_id = int(received_time.timestamp())
            
            print(f"\n--- Procesando correo del {received_time} (ID Unico: {unique_id}) ---")

            estado = "OK"
            if received_time.date() < date.today():
                estado = "PRUEBA"
            else:
                window_start = get_corresponding_window(received_time)
                ventana_inicio, ventana_fin = HORARIOS_ESPERADOS[window_start]
                if not (ventana_inicio <= received_time.time() <= ventana_fin):
                    estado = "OUTTIME"
                PROCESSED_WINDOWS_TODAY.add(window_start)

            excel_attachment = None
            for idx in range(1, email.Attachments.Count + 1):
                att = email.Attachments.Item(idx)
                if os.path.splitext(att.FileName)[1].lower() in ['.xlsx', '.xls']:
                    excel_attachment = att
                    break

            if excel_attachment is None:
                print(f"[WARNING] No se encontro adjunto tipo Excel en el correo. Moviendo a '{REVISADO_FOLDER_NAME}'.")
                metricas_corrida["correos_no_almacenados"] += 1
                metricas_corrida["correos_no_cumplen_requisitos"] += 1
                try:
                    email.Move(revisado_folder)
                except Exception:
                    pass
                continue

            data_df, saved_path = procesar_adjunto_excel(excel_attachment, ioc_folder_path, received_time)
            nombre_archivo_resultante = os.path.basename(saved_path) if saved_path else None

            almacenar_metadatos_archivo(db_connection, unique_id, email.Subject, email.SenderEmailAddress,
                                        nombre_archivo_resultante, received_time, estado)
            
            if data_df is not None and not data_df.empty:
                total_filas = len(data_df)
                metricas_corrida["filas_analizadas_bdd"] += total_filas

                num_inserted, num_duplicated = almacenar_datos_del_archivo(db_connection, data_df, unique_id, received_time)
                metricas_corrida["filas_duplicadas_bdd"] += num_duplicated

                if num_inserted > 0:
                    metricas_corrida["correos_almacenados"] += 1
                    metricas_corrida["filas_adjuntadas_bdd"] += num_inserted
                    try:
                        email.Move(processed_folder)
                        print(f"[OK] Correo movido exitosamente a '{PROCESSED_FOLDER_NAME}'.")
                    except Exception as e:
                        print(f"[ERROR] ERROR al mover el correo procesado a '{PROCESSED_FOLDER_NAME}': {e}.")
                else:
                    print(f"[LOG] Correo duplicado en BDD. Moviendo a '{PROCESSED_FOLDER_NAME}'.")
                    try:
                        email.Move(processed_folder)
                    except Exception as e:
                        print(f"[ERROR] ERROR al mover correo duplicado: {e}.")
            else:
                print(f"[WARNING] Adjunto sin datos estructurados. Moviendo a '{REVISADO_FOLDER_NAME}'.")
                metricas_corrida["correos_no_almacenados"] += 1
                try:
                    email.Move(revisado_folder)
                except Exception:
                    pass

    except Exception as e:
        print(f"[ERROR] Error general al procesar Outlook: {e}")
    finally:
        if db_connection:
            try:
                db_connection.close()
                print("[LOG] Conexion a la base de datos cerrada.")
            except Exception:
                pass

    return metricas_corrida


# PASO 5: EJECUCIÓN PRINCIPAL DE UN SOLO USO

if __name__ == "__main__":
    print(f"--- Iniciando Script de Ingesta 'Reporte Diario tickets Analistas' (TI_GPF) ---")
    print(f"Hora de ejecucion: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        metricas_corrida = procesar_correos_outlook(cantidad_a_leer=100)
        registrar_log_ejecucion_json(estado="EXITO", detalle="Ejecucion completada exitosamente sin errores", metricas=metricas_corrida)
    except Exception as e_main:
        err_msg = f"Error en ejecucion principal: {str(e_main)}"
        print(f"[ERROR] {err_msg}")
        registrar_log_ejecucion_json(estado="ERROR", detalle=err_msg)

    print("\n--- [OK] Analisis completado. Script finalizado. ---")