# --------------------------------------------------------------------------
# SERVIDOR WEB Y API REST: server.py
# UBICACIÓN: 02_Analizador_Tickets_TIGPF/server.py
# DESCRIPCIÓN: Servidor web Flask para el Dashboard Analítico de Tickets TI_GPF.
#              Conecta a MySQL 'TI_GPF', expone las APIs REST /api/tickets,
#              /api/carga_trabajo y /api/analista/<nombre>.
# --------------------------------------------------------------------------

import os
import sys
import sqlite3
import threading
import subprocess
import time
import socket
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request

# Permitir importar db.py desde el directorio raíz
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)
import db

# Configurar encoding UTF-8 en Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'), static_folder=os.path.join(BASE_DIR, 'static'))

DB_PATH = db.DB_PATH
DB_DATA_TABLE = db.DB_DATA_TABLE
DB_ARCHIVOS_TABLE = db.DB_ARCHIVOS_TABLE
DB_HISTORIAL_TABLE = getattr(db, 'DB_HISTORIAL_TABLE', 'GPF_01_Historial_Ejecuciones')
DB_OBSERVACIONES_TABLE = getattr(db, 'DB_OBSERVACIONES_TABLE', 'GPF_01_Observaciones_Carga')
DB_STANDBY_TABLE = getattr(db, 'DB_STANDBY_TABLE', 'GPF_01_Turnos_Standby')

# Estado de sincronización en vivo y scheduler
ingesta_lock = threading.Lock()
ejecucion_activa_info = {
    "en_proceso": False,
    "id": None,
    "tipo": None,
    "fecha_inicio": None
}
SCHEDULER_INTERVAL_SECONDS = 3600  # 1 hora = 3600 segundos
PROXIMA_EJECUCION_TIMESTAMP = datetime.now() + timedelta(seconds=SCHEDULER_INTERVAL_SECONDS)

def conectar_bdd():
    """Establece conexión con SQLite DB TI_GPF."""
    try:
        conn = db.get_connection(use_row_factory=True)
        return conn
    except sqlite3.Error as err:
        print(f"[ERROR] No se pudo conectar a SQLite DB '{DB_PATH}': {err}")
        return None

def ejecutar_proceso_ingesta(tipo='AUTOMATICA_HORARIA'):
    """
    Ejecuta el script 00_GPF_PDC_mail.py en un subproceso aislado,
    registrando los tiempos, métricas y log de salida en GPF_01_Historial_Ejecuciones.
    """
    global ejecucion_activa_info, PROXIMA_EJECUCION_TIMESTAMP
    
    if not ingesta_lock.acquire(blocking=False):
        return {
            "status": "ocupado",
            "mensaje": "Ya existe una sincronización de correos en curso.",
            "ejecucion_activa": ejecucion_activa_info
        }

    inicio_dt = datetime.now()
    inicio_str = inicio_dt.strftime("%Y-%m-%d %H:%M:%S")
    conn = conectar_bdd()
    ejecucion_id = None

    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {DB_ARCHIVOS_TABLE}")
        archivos_antes = cursor.fetchone()[0]
        cursor.execute(f"SELECT COUNT(*) FROM {DB_DATA_TABLE}")
        filas_antes = cursor.fetchone()[0]

        cursor.execute(f"""
            INSERT INTO {DB_HISTORIAL_TABLE} 
            (fecha_inicio, tipo, estado, mensaje)
            VALUES (?, ?, 'EN_PROCESO', 'Ejecución en curso...')
        """, (inicio_str, tipo))
        conn.commit()
        ejecucion_id = cursor.lastrowid

        ejecucion_activa_info = {
            "en_proceso": True,
            "id": ejecucion_id,
            "tipo": tipo,
            "fecha_inicio": inicio_str
        }

        # Ejecutar 00_GPF_PDC_mail.py en subproceso aislado
        script_path = os.path.join(PARENT_DIR, "00_GPF_PDC_mail.py")
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=PARENT_DIR,
            timeout=600
        )

        fin_dt = datetime.now()
        fin_str = fin_dt.strftime("%Y-%m-%d %H:%M:%S")
        duracion = round((fin_dt - inicio_dt).total_seconds(), 2)

        cursor.execute(f"SELECT COUNT(*) FROM {DB_ARCHIVOS_TABLE}")
        archivos_despues = cursor.fetchone()[0]
        cursor.execute(f"SELECT COUNT(*) FROM {DB_DATA_TABLE}")
        filas_despues = cursor.fetchone()[0]

        nuevos_archivos = max(0, archivos_despues - archivos_antes)
        nuevas_filas = max(0, filas_despues - filas_antes)

        stdout_log = proc.stdout or ""
        stderr_log = proc.stderr or ""
        log_completo = stdout_log
        if stderr_log:
            log_completo += f"\n\n--- [STDERR] ---\n{stderr_log}"

        if proc.returncode == 0:
            estado = "EXITO"
            if nuevos_archivos > 0 or nuevas_filas > 0:
                mensaje = f"Sincronización exitosa: {nuevos_archivos} archivo(s) procesado(s), {nuevas_filas} registros añadidos."
            else:
                mensaje = "Sincronización completada: Buzón revisado, no se encontraron nuevos reportes pendientes."
        else:
            estado = "ERROR"
            mensaje = f"Proceso finalizó con código de error {proc.returncode}."

        cursor.execute(f"""
            UPDATE {DB_HISTORIAL_TABLE}
            SET fecha_fin = ?, duracion_segundos = ?, estado = ?, correos_procesados = ?,
                filas_insertadas = ?, mensaje = ?, log_salida = ?
            WHERE id = ?
        """, (fin_str, duracion, estado, nuevos_archivos, nuevas_filas, mensaje, log_completo, ejecucion_id))
        conn.commit()

        return {
            "status": "completado",
            "id": ejecucion_id,
            "estado": estado,
            "mensaje": mensaje,
            "duracion_segundos": duracion,
            "nuevos_archivos": nuevos_archivos,
            "nuevas_filas": nuevas_filas
        }

    except subprocess.TimeoutExpired:
        fin_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duracion = round((datetime.now() - inicio_dt).total_seconds(), 2)
        if ejecucion_id and conn:
            try:
                cursor.execute(f"""
                    UPDATE {DB_HISTORIAL_TABLE}
                    SET fecha_fin = ?, duracion_segundos = ?, estado = 'ERROR',
                        mensaje = 'Tiempo de espera agotado (timeout 600s).', log_salida = 'Proceso cancelado por timeout.'
                    WHERE id = ?
                """, (fin_str, duracion, ejecucion_id))
                conn.commit()
            except Exception:
                pass
        return {"status": "error", "mensaje": "Tiempo de espera agotado en ingesta"}

    except Exception as e:
        fin_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duracion = round((datetime.now() - inicio_dt).total_seconds(), 2)
        if ejecucion_id and conn:
            try:
                cursor.execute(f"""
                    UPDATE {DB_HISTORIAL_TABLE}
                    SET fecha_fin = ?, duracion_segundos = ?, estado = 'ERROR',
                        mensaje = ?, log_salida = ?
                    WHERE id = ?
                """, (fin_str, duracion, str(e), str(e), ejecucion_id))
                conn.commit()
            except Exception:
                pass
        return {"status": "error", "mensaje": str(e)}

    finally:
        ejecucion_activa_info = {
            "en_proceso": False,
            "id": None,
            "tipo": None,
            "fecha_inicio": None
        }
        if conn:
            try: conn.close()
            except Exception: pass
        ingesta_lock.release()

def background_hourly_scheduler():
    """Hilo demonio en segundo plano que ejecuta la sincronización cada hora de cada día."""
    global PROXIMA_EJECUCION_TIMESTAMP
    print(f"🕒 [SCHEDULER] Planificador horaria activo. Próxima ejecución en 1 hora.")
    PROXIMA_EJECUCION_TIMESTAMP = datetime.now() + timedelta(seconds=SCHEDULER_INTERVAL_SECONDS)
    
    while True:
        try:
            time.sleep(SCHEDULER_INTERVAL_SECONDS)
            print(f"⏰ [SCHEDULER] Disparando ejecución automática horaria: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            ejecutar_proceso_ingesta(tipo='AUTOMATICA_HORARIA')
            PROXIMA_EJECUCION_TIMESTAMP = datetime.now() + timedelta(seconds=SCHEDULER_INTERVAL_SECONDS)
            print(f"🕒 [SCHEDULER] Próxima ejecución horaria: {PROXIMA_EJECUCION_TIMESTAMP.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"❌ [SCHEDULER ERROR] Error en ciclo de scheduler: {e}")
            time.sleep(60)

def start_scheduler_once():
    """Inicia el scheduler en un hilo demonio una sola vez y limpia ejecuciones pendientes de sesiones previas."""
    try:
        conn = conectar_bdd()
        if conn:
            cur = conn.cursor()
            cur.execute(f"UPDATE {DB_HISTORIAL_TABLE} SET estado = 'INTERRUMPIDO', mensaje = 'Sesión anterior reiniciada' WHERE estado = 'EN_PROCESO';")
            conn.commit()
            conn.close()
    except Exception:
        pass

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        t = threading.Thread(target=background_hourly_scheduler, daemon=True, name="HourlySchedulerThread")
        t.start()
        print("🚀 [SCHEDULER] Sincronización horaria iniciada en segundo plano (cada 60 min).")

def to_int(val):
    return int(val) if val is not None else 0

def fetchall_dicts(cursor):
    """Convierte los resultados de sqlite3.Row a diccionarios mutables estándar."""
    return [dict(row) for row in cursor.fetchall()]

def fetchone_dict(cursor):
    """Convierte una sola fila de sqlite3.Row a diccionario estándar."""
    row = cursor.fetchone()
    return dict(row) if row else None

# --------------------------------------------------------------------------
# RUTAS DE PÁGINAS HTML
# --------------------------------------------------------------------------

@app.route('/')
def index():
    """Ruta principal del Dashboard General."""
    return render_template('index.html')

@app.route('/carga_trabajo')
def carga_trabajo_page():
    """Ruta del Dashboard de Análisis de Carga de Trabajo."""
    return render_template('carga_trabajo.html')

@app.route('/reporte_grupos')
def reporte_grupos_page():
    """Ruta del Reporte Casos por Grupos - Detalle (Con Date Picker)."""
    return render_template('reporte_grupos.html')

@app.route('/analista')
def analista_page():
    """Ruta del Dashboard individual por Analista."""
    nombre = request.args.get('nombre', '')
    return render_template('analista.html', nombre=nombre)

@app.route('/historial')
def historial_page():
    """Ruta de la Vista de Historial de Ejecuciones y Monitoreo de Ingesta."""
    return render_template('historial.html')

@app.route('/standby')
def standby_page():
    """Ruta de la Vista de Gestión y Asignación de Turnos de Standby / Guardias."""
    return render_template('standby.html')

# --------------------------------------------------------------------------
# API ENDPOINTS REST
# --------------------------------------------------------------------------

@app.route('/api/tickets')
def get_tickets_api():
    """API REST para obtener datos filtrados por temporalidad (actual/día, mes, semestre, año, todos)."""
    temporalidad = request.args.get('temporalidad', 'actual').lower()
    fecha_param = request.args.get('fecha', '').strip()
    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos SQLite"}), 500

    try:
        cursor = conn.cursor()
        now = datetime.now()
        params = []

        # Obtener lista de fechas disponibles y fecha más reciente en BDD
        cursor.execute(f"SELECT DISTINCT DATE(fecha_recepcion) as fecha FROM {DB_DATA_TABLE} ORDER BY fecha DESC;")
        fechas_disponibles = [str(r['fecha']) for r in fetchall_dicts(cursor)]
        max_fecha = fechas_disponibles[0] if fechas_disponibles else now.strftime("%Y-%m-%d")

        cursor.execute(f"SELECT COUNT(*) FROM {DB_DATA_TABLE} WHERE DATE(fecha_recepcion) = CURDATE();")
        tiene_hoy = cursor.fetchone()[0] > 0
        fecha_corte = now.strftime("%Y-%m-%d") if tiene_hoy else max_fecha

        where_clause = ""
        fecha_activa_label = ""

        if fecha_param:
            where_clause = "WHERE DATE(fecha_recepcion) = ?"
            params.append(fecha_param)
            fecha_activa_label = fecha_param
            temporalidad = 'dia'
        elif temporalidad in ('dia', 'actual', 'hoy'):
            where_clause = "WHERE DATE(fecha_recepcion) = ?"
            params.append(fecha_corte)
            fecha_activa_label = fecha_corte
            temporalidad = 'actual'
        elif temporalidad == 'mes':
            where_clause = f"WHERE YEAR(fecha_recepcion) = {now.year} AND MONTH(fecha_recepcion) = {now.month}"
            fecha_activa_label = f"{now.year}-{now.month:02d}"
        elif temporalidad == 'semestre':
            current_sem = 1 if now.month <= 6 else 2
            if current_sem == 1:
                where_clause = f"WHERE YEAR(fecha_recepcion) = {now.year} AND MONTH(fecha_recepcion) BETWEEN 1 AND 6"
            else:
                where_clause = f"WHERE YEAR(fecha_recepcion) = {now.year} AND MONTH(fecha_recepcion) BETWEEN 7 AND 12"
            fecha_activa_label = f"Semestre {current_sem} {now.year}"
        elif temporalidad == 'ano':
            where_clause = f"WHERE YEAR(fecha_recepcion) = {now.year}"
            fecha_activa_label = f"Año {now.year}"
        elif temporalidad == 'todos':
            where_clause = ""
            fecha_activa_label = "Histórico Completo"

        query_data = f"""
        SELECT 
            id, id_unico, fecha_recepcion, fecha_creacion,
            assign_to_group, assign_to_individual,
            pending, queued, resolved, (pending + queued + resolved) as total
        FROM {DB_DATA_TABLE}
        {where_clause}
        ORDER BY fecha_recepcion DESC, assign_to_group, assign_to_individual;
        """
        cursor.execute(query_data, params)
        rows_data = fetchall_dicts(cursor)

        query_analistas = f"""
        SELECT 
            assign_to_group,
            assign_to_individual,
            SUM(pending) as pending,
            SUM(queued) as queued,
            SUM(resolved) as resolved,
            SUM(pending + queued + resolved) as total,
            MAX(fecha_recepcion) as ultima_fecha
        FROM {DB_DATA_TABLE}
        {where_clause}
        GROUP BY assign_to_group, assign_to_individual
        ORDER BY total DESC;
        """
        cursor.execute(query_analistas, params)
        rows_analistas = fetchall_dicts(cursor)

        query_grupos = f"""
        SELECT 
            assign_to_group,
            COUNT(DISTINCT assign_to_individual) as total_analistas,
            SUM(pending) as pending,
            SUM(queued) as queued,
            SUM(resolved) as resolved,
            SUM(pending + queued + resolved) as total
        FROM {DB_DATA_TABLE}
        {where_clause}
        GROUP BY assign_to_group
        ORDER BY total DESC;
        """
        cursor.execute(query_grupos, params)
        rows_grupos = fetchall_dicts(cursor)

        cursor.close()
        conn.close()

        for r in rows_data:
            if isinstance(r.get('fecha_recepcion'), datetime):
                r['fecha_recepcion'] = r['fecha_recepcion'].strftime("%Y-%m-%d %H:%M:%S")
            elif r.get('fecha_recepcion'):
                r['fecha_recepcion'] = str(r['fecha_recepcion']).strip()

            if isinstance(r.get('fecha_creacion'), datetime):
                r['fecha_creacion'] = r['fecha_creacion'].strftime("%Y-%m-%d %H:%M:%S")
            elif r.get('fecha_creacion'):
                r['fecha_creacion'] = str(r['fecha_creacion']).strip()

        for r in rows_analistas:
            if isinstance(r.get('ultima_fecha'), datetime):
                r['ultima_fecha'] = r['ultima_fecha'].strftime("%Y-%m-%d %H:%M:%S")
            elif r.get('ultima_fecha'):
                r['ultima_fecha'] = str(r['ultima_fecha']).strip()
            r['pending'] = to_int(r['pending'])
            r['queued'] = to_int(r['queued'])
            r['resolved'] = to_int(r['resolved'])
            r['total'] = to_int(r['total'])
            r['tasa_cierre_pct'] = round((r['resolved'] / r['total'] * 100), 2) if r['total'] > 0 else 0.0

        for r in rows_grupos:
            r['pending'] = to_int(r['pending'])
            r['queued'] = to_int(r['queued'])
            r['resolved'] = to_int(r['resolved'])
            r['total'] = to_int(r['total'])
            r['tasa_cierre_pct'] = round((r['resolved'] / r['total'] * 100), 2) if r['total'] > 0 else 0.0

        total_tickets = sum(r['total'] for r in rows_grupos)
        total_resolved = sum(r['resolved'] for r in rows_grupos)
        total_pending = sum(r['pending'] for r in rows_grupos)
        total_queued = sum(r['queued'] for r in rows_grupos)
        tasa_cierre_global = round((total_resolved / total_tickets * 100), 2) if total_tickets > 0 else 0.0

        return jsonify({
            "temporalidad": temporalidad,
            "fecha_corte": fecha_corte,
            "fecha_activa_label": fecha_activa_label,
            "es_corte_actual": (fecha_corte == now.strftime("%Y-%m-%d")),
            "resumen_general": {
                "total_tickets": total_tickets,
                "total_resueltos": total_resolved,
                "total_pendientes": total_pending,
                "total_en_cola": total_queued,
                "tasa_cierre_global_pct": tasa_cierre_global,
                "total_analistas": len(rows_analistas),
                "total_grupos": len(rows_grupos)
            },
            "analistas": rows_analistas,
            "grupos": rows_grupos,
            "fechas_disponibles": fechas_disponibles,
            "registros_crudos": rows_data
        })
    except Exception as e:
        print(f"[ERROR] Error al procesar API /api/tickets: {e}")
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500

@app.route('/api/reporte_casos_grupos')
def get_reporte_casos_grupos_api():
    """API REST para generar el reporte de Casos por Grupos - Detalle filtrado por rango de fechas (Time Picker)."""
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')
    temporalidad = request.args.get('temporalidad', 'actual').lower()

    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos SQLite"}), 500

    try:
        cursor = conn.cursor()
        now = datetime.now()

        # Obtener lista de fechas disponibles y fecha más reciente en BDD
        cursor.execute(f"SELECT DISTINCT DATE(fecha_recepcion) as fecha FROM {DB_DATA_TABLE} ORDER BY fecha DESC;")
        fechas_disponibles = [str(r['fecha']) for r in fetchall_dicts(cursor)]
        max_fecha = fechas_disponibles[0] if fechas_disponibles else now.strftime("%Y-%m-%d")

        cursor.execute(f"SELECT COUNT(*) FROM {DB_DATA_TABLE} WHERE DATE(fecha_recepcion) = CURDATE();")
        tiene_hoy = cursor.fetchone()[0] > 0
        fecha_corte = now.strftime("%Y-%m-%d") if tiene_hoy else max_fecha

        where_clauses = []
        params = []

        if fecha_inicio:
            where_clauses.append("DATE(fecha_recepcion) >= ?")
            params.append(fecha_inicio)
        if fecha_fin:
            where_clauses.append("DATE(fecha_recepcion) <= ?")
            params.append(fecha_fin)

        if not (fecha_inicio or fecha_fin):
            if temporalidad in ('actual', 'dia', 'hoy'):
                where_clauses.append("DATE(fecha_recepcion) = ?")
                params.append(fecha_corte)
                fecha_inicio = fecha_corte
                fecha_fin = fecha_corte
            elif temporalidad == 'mes':
                where_clauses.append(f"YEAR(fecha_recepcion) = {now.year} AND MONTH(fecha_recepcion) = {now.month}")
            elif temporalidad == 'semestre':
                current_sem = 1 if now.month <= 6 else 2
                if current_sem == 1:
                    where_clauses.append(f"YEAR(fecha_recepcion) = {now.year} AND MONTH(fecha_recepcion) BETWEEN 1 AND 6")
                else:
                    where_clauses.append(f"YEAR(fecha_recepcion) = {now.year} AND MONTH(fecha_recepcion) BETWEEN 7 AND 12")
            elif temporalidad == 'ano':
                where_clauses.append(f"YEAR(fecha_recepcion) = {now.year}")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        query_data = f"""
        SELECT 
            assign_to_group,
            assign_to_individual,
            SUM(pending) as pending,
            SUM(queued) as queued,
            SUM(resolved) as resolved,
            SUM(pending + queued + resolved) as total
        FROM {DB_DATA_TABLE}
        {where_sql}
        GROUP BY assign_to_group, assign_to_individual
        ORDER BY assign_to_group, assign_to_individual;
        """
        cursor.execute(query_data, params)
        rows = fetchall_dicts(cursor)

        cursor.execute(f"SELECT MIN(DATE(fecha_recepcion)) as min_fecha, MAX(DATE(fecha_recepcion)) as max_fecha FROM {DB_DATA_TABLE};")
        rango_fechas = fetchone_dict(cursor)

        cursor.close()
        conn.close()

        grupos_dict = {}
        for r in rows:
            grp = r['assign_to_group']
            p = to_int(r['pending'])
            q = to_int(r['queued'])
            res = to_int(r['resolved'])
            tot = to_int(r['total'])

            if grp not in grupos_dict:
                grupos_dict[grp] = {
                    "assign_to_group": grp,
                    "analistas": [],
                    "subtotal": {"pending": 0, "queued": 0, "resolved": 0, "total": 0}
                }

            grupos_dict[grp]["analistas"].append({
                "assign_to_individual": r['assign_to_individual'],
                "pending": p,
                "queued": q,
                "resolved": res,
                "total": tot
            })

            grupos_dict[grp]["subtotal"]["pending"] += p
            grupos_dict[grp]["subtotal"]["queued"] += q
            grupos_dict[grp]["subtotal"]["resolved"] += res
            grupos_dict[grp]["subtotal"]["total"] += tot

        gran_total = {
            "pending": sum(g["subtotal"]["pending"] for g in grupos_dict.values()),
            "queued": sum(g["subtotal"]["queued"] for g in grupos_dict.values()),
            "resolved": sum(g["subtotal"]["resolved"] for g in grupos_dict.values()),
            "total": sum(g["subtotal"]["total"] for g in grupos_dict.values())
        }

        min_fecha_str = str(rango_fechas['min_fecha']) if rango_fechas and rango_fechas['min_fecha'] else ''
        max_fecha_str = str(rango_fechas['max_fecha']) if rango_fechas and rango_fechas['max_fecha'] else ''

        return jsonify({
            "fecha_inicio": fecha_inicio or min_fecha_str,
            "fecha_fin": fecha_fin or max_fecha_str,
            "temporalidad": temporalidad,
            "fecha_corte": fecha_corte,
            "fechas_disponibles": fechas_disponibles,
            "es_corte_actual": (fecha_corte == now.strftime("%Y-%m-%d")),
            "min_fecha_bdd": min_fecha_str,
            "max_fecha_bdd": max_fecha_str,
            "grupos": list(grupos_dict.values()),
            "gran_total": gran_total
        })

    except Exception as e:
        print(f"[ERROR] Error al procesar API /api/reporte_casos_grupos: {e}")
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500


@app.route('/api/carga_trabajo')
def get_carga_trabajo_api():
    """API REST para el análisis completo de Carga de Trabajo basada en el archivo procesado."""
    archivo_id = request.args.get('archivo_id', '').strip()
    corte_param = request.args.get('corte', '').strip()
    fecha_param = request.args.get('fecha', '').strip()
    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos SQLite"}), 500

    try:
        cursor = conn.cursor()
        now = datetime.now()

        # 1. Obtener lista completa de archivos procesados disponibles en orden cronológico descendente
        cursor.execute(f"""
        SELECT id, id_unico, nombre_archivo_resultante, fecha_recepcion, asunto_correo, remitente_correo, estado_analisis, fecha_creacion
        FROM {DB_ARCHIVOS_TABLE}
        ORDER BY fecha_recepcion DESC, id DESC;
        """)
        archivos_disponibles = fetchall_dicts(cursor)

        if not archivos_disponibles:
            # Respaldo si no hay archivos registrados en GPF_01_Archivos_Procesados
            cursor.execute(f"SELECT DISTINCT fecha_recepcion FROM {DB_DATA_TABLE} ORDER BY fecha_recepcion DESC LIMIT 1;")
            fallback_row = fetchone_dict(cursor)
            fallback_fecha = fallback_row['fecha_recepcion'] if fallback_row else now.strftime("%Y-%m-%d %H:%M:%S")
            archivos_disponibles = [{
                "id": 1,
                "id_unico": 1,
                "nombre_archivo_resultante": "Reporte_Tickets_Analistas.xlsx",
                "fecha_recepcion": fallback_fecha,
                "asunto_correo": "Reporte Diario tickets Analistas",
                "remitente_correo": "analistas@corporaciongpf.com",
                "estado_analisis": "PROCESADO",
                "fecha_creacion": fallback_fecha
            }]

        # 2. Determinar el archivo seleccionado (por ID, corte, fecha, o por defecto el último archivo cargado)
        archivo_seleccionado = None
        if archivo_id:
            for a in archivos_disponibles:
                if str(a['id']) == str(archivo_id):
                    archivo_seleccionado = a
                    break
        elif corte_param:
            for a in archivos_disponibles:
                if str(a['fecha_recepcion']) == corte_param or str(a.get('id_unico')) == corte_param:
                    archivo_seleccionado = a
                    break
        elif fecha_param:
            for a in archivos_disponibles:
                if str(a['fecha_recepcion']).startswith(fecha_param):
                    archivo_seleccionado = a
                    break

        # Si no se encontró o no se especificó, tomar estrictamente el ÚLTIMO ARCHIVO CARGADO
        if not archivo_seleccionado:
            archivo_seleccionado = archivos_disponibles[0]

        es_ultimo = (archivo_seleccionado['id'] == archivos_disponibles[0]['id'])
        selected_fecha_recepcion = str(archivo_seleccionado['fecha_recepcion'])
        selected_id_unico = archivo_seleccionado.get('id_unico')

        # 3. Identificar archivo anterior inmediato para análisis diferencial dinámico de flujo
        archivo_anterior = None
        current_idx = None
        for idx, a in enumerate(archivos_disponibles):
            if a['id'] == archivo_seleccionado['id']:
                current_idx = idx
                break
        
        if current_idx is not None and current_idx + 1 < len(archivos_disponibles):
            archivo_anterior = archivos_disponibles[current_idx + 1]

        rows_ant_dict = {}
        if archivo_anterior:
            f_ant_rec = str(archivo_anterior['fecha_recepcion'])
            cursor.execute(f"""
            SELECT 
                assign_to_group,
                assign_to_individual,
                SUM(pending) as pending,
                SUM(queued) as queued,
                SUM(resolved) as resolved,
                SUM(pending + queued + resolved) as total
            FROM {DB_DATA_TABLE}
            WHERE fecha_recepcion = ?
            GROUP BY assign_to_group, assign_to_individual;
            """, (f_ant_rec,))
            rows_ant = fetchall_dicts(cursor)
            if not rows_ant and archivo_anterior.get('id_unico'):
                cursor.execute(f"""
                SELECT 
                    assign_to_group,
                    assign_to_individual,
                    SUM(pending) as pending,
                    SUM(queued) as queued,
                    SUM(resolved) as resolved,
                    SUM(pending + queued + resolved) as total
                FROM {DB_DATA_TABLE}
                WHERE id_unico = ?
                GROUP BY assign_to_group, assign_to_individual;
                """, (archivo_anterior.get('id_unico'),))
                rows_ant = fetchall_dicts(cursor)
            rows_ant_dict = {r['assign_to_individual']: r for r in rows_ant}

        # 4. Query de analistas estrictamente para este archivo cargado (Snapshot sin suma temporal)
        query_analistas = f"""
        SELECT 
            assign_to_group,
            assign_to_individual,
            SUM(pending) as pending,
            SUM(queued) as queued,
            SUM(resolved) as resolved,
            SUM(pending + queued + resolved) as total
        FROM {DB_DATA_TABLE}
        WHERE fecha_recepcion = ?
        GROUP BY assign_to_group, assign_to_individual
        ORDER BY (SUM(pending) + SUM(queued)) DESC, SUM(pending) DESC;
        """
        cursor.execute(query_analistas, (selected_fecha_recepcion,))
        rows_analistas = fetchall_dicts(cursor)

        # Si por alguna discrepancia de timestamp no devuelve filas con fecha_recepcion exacta, intentar por id_unico
        if not rows_analistas and selected_id_unico:
            query_analistas_fallback = f"""
            SELECT 
                assign_to_group,
                assign_to_individual,
                SUM(pending) as pending,
                SUM(queued) as queued,
                SUM(resolved) as resolved,
                SUM(pending + queued + resolved) as total
            FROM {DB_DATA_TABLE}
            WHERE id_unico = ?
            GROUP BY assign_to_group, assign_to_individual
            ORDER BY (SUM(pending) + SUM(queued)) DESC, SUM(pending) DESC;
            """
            cursor.execute(query_analistas_fallback, (selected_id_unico,))
            rows_analistas = fetchall_dicts(cursor)

        # 5. Query de grupos estrictamente para este archivo cargado
        query_grupos = f"""
        SELECT 
            assign_to_group,
            COUNT(DISTINCT assign_to_individual) as total_analistas,
            SUM(pending) as pending,
            SUM(queued) as queued,
            SUM(resolved) as resolved,
            SUM(pending + queued + resolved) as total
        FROM {DB_DATA_TABLE}
        WHERE fecha_recepcion = ?
        GROUP BY assign_to_group
        ORDER BY (SUM(pending) + SUM(queued)) DESC;
        """
        cursor.execute(query_grupos, (selected_fecha_recepcion,))
        rows_grupos = fetchall_dicts(cursor)
        if not rows_grupos and selected_id_unico:
            cursor.execute(f"""
            SELECT 
                assign_to_group,
                COUNT(DISTINCT assign_to_individual) as total_analistas,
                SUM(pending) as pending,
                SUM(queued) as queued,
                SUM(resolved) as resolved,
                SUM(pending + queued + resolved) as total
            FROM {DB_DATA_TABLE}
            WHERE id_unico = ?
            GROUP BY assign_to_group
            ORDER BY (SUM(pending) + SUM(queued)) DESC;
            """, (selected_id_unico,))
            rows_grupos = fetchall_dicts(cursor)

        # 6. Rango de la semana del corte (Lunes a Domingo) para la comparativa semanal
        try:
            corte_dt = datetime.strptime(selected_fecha_recepcion[:10], "%Y-%m-%d")
        except Exception:
            corte_dt = now
        lunes_dt = corte_dt - timedelta(days=corte_dt.weekday())
        domingo_dt = lunes_dt + timedelta(days=6)
        lunes_str = lunes_dt.strftime("%Y-%m-%d")
        domingo_str = domingo_dt.strftime("%Y-%m-%d")
        semana_num = corte_dt.isocalendar()[1]
        anio_corte = corte_dt.year

        # 7. Carga Semanal Generada por Ticket (de Lunes a Domingo de la semana evaluada)
        cursor.execute(f"""
        SELECT 
            assign_to_individual,
            SUM(pending) as pending_semana,
            SUM(queued) as queued_semana,
            SUM(resolved) as resolved_semana,
            SUM(pending + queued + resolved) as total_semana
        FROM {DB_DATA_TABLE}
        WHERE DATE(fecha_recepcion) BETWEEN ? AND ?
        GROUP BY assign_to_individual;
        """, (lunes_str, domingo_str))
        rows_semana = {r['assign_to_individual']: r for r in fetchall_dicts(cursor)}

        # 8. Observaciones de supervisión
        cursor.execute(f"SELECT assign_to_individual, observacion, usuario_registro, fecha_actualizacion FROM {DB_OBSERVACIONES_TABLE};")
        rows_obs = {r['assign_to_individual']: r for r in fetchall_dicts(cursor)}

        # 9. Turnos de Standby / Guardias activos esta semana
        cursor.execute(f"""
        SELECT id, assign_to_individual, assign_to_group, tipo_periodo, fecha_inicio, fecha_fin,
               semana_anio, dia_semana, mes, anio, telefono_contacto, estado, notas
        FROM {DB_STANDBY_TABLE}
        WHERE (? BETWEEN fecha_inicio AND fecha_fin) 
           OR (semana_anio = ? AND anio = ? AND estado = 'ACTIVO')
           OR (estado = 'ACTIVO');
        """, (selected_fecha_recepcion[:10], semana_num, anio_corte))
        standby_activos = fetchall_dicts(cursor)
        standby_dict = {r['assign_to_individual']: r for r in standby_activos}

        # 10. Query de evolución histórica por corte para gráficos de tendencia
        query_evolucion = f"""
        SELECT 
            fecha_recepcion,
            DATE(fecha_recepcion) as fecha,
            assign_to_individual,
            assign_to_group,
            SUM(pending) as pending,
            SUM(queued) as queued,
            SUM(resolved) as resolved,
            SUM(pending + queued) as carga_activa,
            SUM(pending + queued + resolved) as total
        FROM {DB_DATA_TABLE}
        GROUP BY fecha_recepcion, assign_to_individual
        ORDER BY fecha_recepcion ASC, assign_to_individual ASC;
        """
        cursor.execute(query_evolucion)
        rows_evolucion = fetchall_dicts(cursor)

        cursor.close()
        conn.close()

        # Agrupar historial cronológico por analista y consolidado por fecha
        evolucion_por_analista = {}
        consolidado_fechas = {}

        for r in rows_evolucion:
            f = str(r['fecha_recepcion'])
            f_corta = f[:16]
            ind = r['assign_to_individual']
            p = to_int(r['pending'])
            q = to_int(r['queued'])
            res = to_int(r['resolved'])
            act = p + q
            tot = to_int(r['total'])

            if ind not in evolucion_por_analista:
                evolucion_por_analista[ind] = []
            
            evolucion_por_analista[ind].append({
                "fecha": f_corta,
                "fecha_completa": f,
                "assign_to_group": r['assign_to_group'],
                "pending": p,
                "queued": q,
                "resolved": res,
                "carga_activa": act,
                "total": tot
            })

            if f_corta not in consolidado_fechas:
                consolidado_fechas[f_corta] = {
                    "fecha": f_corta,
                    "fecha_completa": f,
                    "pending": 0,
                    "queued": 0,
                    "resolved": 0,
                    "carga_activa": 0,
                    "total": 0
                }
            consolidado_fechas[f_corta]["pending"] += p
            consolidado_fechas[f_corta]["queued"] += q
            consolidado_fechas[f_corta]["resolved"] += res
            consolidado_fechas[f_corta]["carga_activa"] += act
            consolidado_fechas[f_corta]["total"] += tot

        consolidado_temporal = [consolidado_fechas[k] for k in sorted(consolidado_fechas.keys())]

        # Calcular métricas temporales por analista (tendencias, picos, promedios)
        analistas_metricas_tiempo = {}
        for ind, hist in evolucion_por_analista.items():
            if not hist:
                continue
            hist_sorted = sorted(hist, key=lambda x: x['fecha_completa'])
            avg_p = round(sum(h['pending'] for h in hist_sorted) / len(hist_sorted), 1)
            avg_act = round(sum(h['carga_activa'] for h in hist_sorted) / len(hist_sorted), 1)
            avg_res = round(sum(h['resolved'] for h in hist_sorted) / len(hist_sorted), 1)
            
            pico_act = max(hist_sorted, key=lambda x: x['carga_activa'])
            pico_p = max(hist_sorted, key=lambda x: x['pending'])

            # Tendencia comparando el corte actual con el anterior
            if len(hist_sorted) >= 2:
                diff_act = hist_sorted[-1]['carga_activa'] - hist_sorted[-2]['carga_activa']
                diff_p = hist_sorted[-1]['pending'] - hist_sorted[-2]['pending']
                if diff_act > 0:
                    tendencia_activa = "SUBIENDO"
                elif diff_act < 0:
                    tendencia_activa = "BAJANDO"
                else:
                    tendencia_activa = "ESTABLE"
            else:
                diff_act = 0
                diff_p = 0
                tendencia_activa = "ESTABLE"

            analistas_metricas_tiempo[ind] = {
                "avg_pending_diario": avg_p,
                "avg_activa_diaria": avg_act,
                "avg_resolved_diario": avg_res,
                "pico_activa": pico_act['carga_activa'],
                "pico_activa_fecha": pico_act['fecha'],
                "pico_pending": pico_p['pending'],
                "pico_pending_fecha": pico_p['fecha'],
                "diff_activa": diff_act,
                "diff_pending": diff_p,
                "tendencia_activa": tendencia_activa,
                "total_cortes_registrados": len(hist_sorted)
            }

        total_pending = sum(to_int(r['pending']) for r in rows_analistas)
        total_queued = sum(to_int(r['queued']) for r in rows_analistas)
        total_resolved = sum(to_int(r['resolved']) for r in rows_analistas)
        total_tickets = sum(to_int(r['total']) for r in rows_analistas)
        carga_activa_total = total_pending + total_queued

        analistas_carga = []
        for r in rows_analistas:
            p = to_int(r['pending'])
            q = to_int(r['queued'])
            res = to_int(r['resolved'])
            tot = to_int(r['total'])
            carga_activa = p + q
            tasa_desahogo = round((res / tot * 100), 2) if tot > 0 else 0.0

            if p > 15 or carga_activa >= 25:
                nivel_carga = "CRITICA"
                nivel_texto = "🔴 Sobrecargado / Alerta Crítica"
            elif p >= 10 or carga_activa >= 10:
                nivel_carga = "MODERADA"
                nivel_texto = "🟡 Carga Moderada"
            else:
                nivel_carga = "BALANCEADA"
                nivel_texto = "🟢 Carga Balanceada"

            ind_name = r['assign_to_individual']
            tiempo_stats = analistas_metricas_tiempo.get(ind_name, {
                "avg_pending_diario": round(p, 1),
                "avg_activa_diaria": round(carga_activa, 1),
                "avg_resolved_diario": round(res, 1),
                "pico_activa": carga_activa,
                "pico_activa_fecha": selected_fecha_recepcion,
                "pico_pending": p,
                "pico_pending_fecha": selected_fecha_recepcion,
                "diff_activa": 0,
                "diff_pending": 0,
                "tendencia_activa": "ESTABLE",
                "total_cortes_registrados": 1
            })

            # Snapshot del archivo analizado
            u_p = p
            u_q = q
            u_res = res
            u_tot = tot
            u_act = carga_activa

            # Carga Semanal Generada por Ticket
            w_data = rows_semana.get(ind_name, {})
            w_p = to_int(w_data.get('pending_semana', 0))
            w_q = to_int(w_data.get('queued_semana', 0))
            w_res = to_int(w_data.get('resolved_semana', 0))
            w_tot = to_int(w_data.get('total_semana', 0))
            w_act = w_p + w_q
            w_tasa = round((w_res / w_tot * 100), 1) if w_tot > 0 else 0.0

            # -------------------------------------------------------------
            # ANÁLISIS DIFERENCIAL DINÁMICO: CORTE ACTUAL VS. ANTERIOR
            # -------------------------------------------------------------
            ant_item = rows_ant_dict.get(ind_name, {})
            ant_p = to_int(ant_item.get('pending', 0))
            ant_q = to_int(ant_item.get('queued', 0))
            ant_res = to_int(ant_item.get('resolved', 0))
            ant_act = ant_p + ant_q
            ant_tot = to_int(ant_item.get('total', 0))

            tiene_anterior = bool(archivo_anterior and ind_name in rows_ant_dict)
            diff_p = (p - ant_p) if tiene_anterior else 0
            diff_q = (q - ant_q) if tiene_anterior else 0
            diff_activa = (carga_activa - ant_act) if tiene_anterior else 0
            diff_res = max(0, res - ant_res) if tiene_anterior else 0
            inflow_estimado = max(0, diff_res + diff_activa) if tiene_anterior else 0

            # Clasificación operativa del flujo entre cortes
            if not tiene_anterior:
                estado_flujo = 'INICIAL'
                estado_flujo_label = 'Primer Registro'
                estado_flujo_color = '#94a3b8'
                estado_flujo_desc = 'Sin corte anterior registrado para comparación'
            elif diff_res >= 3 and carga_activa <= 3:
                estado_flujo = 'ALTA_VELOCIDAD'
                estado_flujo_label = f'🟢 Alta Velocidad (+{diff_res} cerrados)'
                estado_flujo_color = '#10b981'
                estado_flujo_desc = f'Excelente rendimiento: resolvió {diff_res} tickets en el periodo y mantiene su mesa despejada ({carga_activa} activos).'
            elif diff_activa > 0 and diff_res <= 1:
                estado_flujo = 'CUELLO_BOTELLA'
                estado_flujo_label = f'🔴 Atasco / Acumulando (+{diff_activa} activa)'
                estado_flujo_color = '#ef4444'
                estado_flujo_desc = f'Alerta de saturación: acumuló +{diff_activa} tickets activos ({carga_activa} en total) y solo cerró {diff_res}.'
            elif diff_res == 0 and carga_activa > 0 and diff_activa == 0:
                estado_flujo = 'ESTANCADO'
                estado_flujo_label = f'⚠️ Sin Avance (>24h)'
                estado_flujo_color = '#f59e0b'
                estado_flujo_desc = f'Tickets detenidos: {carga_activa} activos sin movimientos ni resoluciones entre cortes.'
            elif diff_res > 0 and diff_activa < 0:
                estado_flujo = 'DESAHOGANDO'
                estado_flujo_label = f'🟢 Desahogando ({diff_activa:+d} activa)'
                estado_flujo_color = '#10b981'
                estado_flujo_desc = f'Desahogo positivo: resolvió {diff_res} tickets y redujo su carga activa en {abs(diff_activa)}.'
            elif diff_res > 0 and diff_activa == 0:
                estado_flujo = 'RITMO_CONTINUO'
                estado_flujo_label = f'🟡 Ritmo Continuo (+{diff_res} cerrados)'
                estado_flujo_color = '#3b82f6'
                estado_flujo_desc = f'Flujo balanceado: cerró {diff_res} tickets al mismo ritmo que ingresaron nuevos.'
            elif carga_activa == 0 and ant_act == 0:
                estado_flujo = 'DISPONIBLE'
                estado_flujo_label = '🟢 Mesa Despejada'
                estado_flujo_color = '#10b981'
                estado_flujo_desc = 'Sin tickets pendientes ni en cola. Disponible para nuevas asignaciones.'
            else:
                estado_flujo = 'ESTABLE'
                estado_flujo_label = '⚪ Estable'
                estado_flujo_color = '#94a3b8'
                estado_flujo_desc = 'Carga de trabajo en límites operativos habituales.'

            # Workload Saturation Index (0 - 100%)
            presion = min(100.0, (u_p * 7.0) + (u_q * 3.0))
            deficit = max(0.0, 100.0 - w_tasa) if w_tot > 0 else 40.0
            score_saturacion = round(max(5.0, min(100.0, (presion * 0.65) + (deficit * 0.35))), 1)

            if score_saturacion >= 85.0:
                nivel_sat = 'SOBRECARGA_CRITICA'
                nivel_sat_label = '🔴 Sobrecarga Crítica'
                nivel_sat_color = '#ef4444'
            elif score_saturacion >= 70.0:
                nivel_sat = 'ALTA_DEMANDA'
                nivel_sat_label = '🟠 Alta Demanda'
                nivel_sat_color = '#f97316'
            elif score_saturacion >= 40.0:
                nivel_sat = 'CARGA_MODERADA'
                nivel_sat_label = '🟡 Carga Moderada'
                nivel_sat_color = '#eab308'
            else:
                nivel_sat = 'BAJA_DEMANDA'
                nivel_sat_label = '🟢 Baja Demanda / Disponible'
                nivel_sat_color = '#10b981'

            # Turno de Standby activo esta semana
            st_info = standby_dict.get(ind_name)
            en_standby = True if st_info else False

            # Observaciones de supervisión
            obs_item = rows_obs.get(ind_name, {})
            observacion = obs_item.get('observacion', '')
            fecha_observacion = obs_item.get('fecha_actualizacion', '')
            usuario_observacion = obs_item.get('usuario_registro', '')

            analistas_carga.append({
                "assign_to_group": r['assign_to_group'],
                "assign_to_individual": ind_name,
                "pending": p,
                "queued": q,
                "resolved": res,
                "total": tot,
                "carga_activa": carga_activa,
                "pct_carga_sobre_total": round((carga_activa / carga_activa_total * 100), 2) if carga_activa_total > 0 else 0.0,
                "tasa_desahogo_pct": tasa_desahogo,
                "nivel_carga": nivel_carga,
                "nivel_texto": nivel_texto,
                "metricas_tiempo": tiempo_stats,
                "ultimo_corte": {
                    "fecha": selected_fecha_recepcion,
                    "pending": u_p,
                    "queued": u_q,
                    "resolved": u_res,
                    "carga_activa": u_act,
                    "total": u_tot
                },
                "diferencial_corte": {
                    "tiene_anterior": tiene_anterior,
                    "corte_anterior_fecha": archivo_anterior['fecha_recepcion'] if archivo_anterior else None,
                    "corte_anterior_nombre": archivo_anterior['nombre_archivo_resultante'] if archivo_anterior else None,
                    "pending_anterior": ant_p,
                    "queued_anterior": ant_q,
                    "resolved_anterior": ant_res,
                    "activa_anterior": ant_act,
                    "diff_pending": diff_p,
                    "diff_queued": diff_q,
                    "diff_activa": diff_activa,
                    "diff_resolved": diff_res,
                    "inflow_estimado": inflow_estimado,
                    "estado_flujo": estado_flujo,
                    "estado_flujo_label": estado_flujo_label,
                    "estado_flujo_color": estado_flujo_color,
                    "estado_flujo_desc": estado_flujo_desc
                },
                "carga_semanal": {
                    "fecha_inicio": lunes_str,
                    "fecha_fin": domingo_str,
                    "semana_anio": semana_num,
                    "pending": w_p,
                    "queued": w_q,
                    "resolved": w_res,
                    "carga_activa": w_act,
                    "total": w_tot,
                    "tasa_cierre_pct": w_tasa
                },
                "indice_saturacion_pct": score_saturacion,
                "nivel_saturacion": nivel_sat,
                "nivel_saturacion_label": nivel_sat_label,
                "nivel_saturacion_color": nivel_sat_color,
                "en_standby": en_standby,
                "standby_info": st_info,
                "observacion": observacion,
                "fecha_observacion": fecha_observacion,
                "usuario_observacion": usuario_observacion
            })

        grupos_carga = []
        for r in rows_grupos:
            p = to_int(r['pending'])
            q = to_int(r['queued'])
            res = to_int(r['resolved'])
            tot = to_int(r['total'])
            carga_activa = p + q

            grupos_carga.append({
                "assign_to_group": r['assign_to_group'],
                "total_analistas": to_int(r['total_analistas']),
                "pending": p,
                "queued": q,
                "resolved": res,
                "total": tot,
                "carga_activa": carga_activa,
                "promedio_carga_por_analista": round((carga_activa / to_int(r['total_analistas'])), 1) if to_int(r['total_analistas']) > 0 else 0.0,
                "tasa_desahogo_pct": round((res / tot * 100), 2) if tot > 0 else 0.0
            })

        num_analistas = len(analistas_carga) if analistas_carga else 1
        promedios_equipo = {
            "avg_pending": round(total_pending / num_analistas, 1),
            "avg_queued": round(total_queued / num_analistas, 1),
            "avg_carga_activa": round(carga_activa_total / num_analistas, 1),
            "avg_resolved": round(total_resolved / num_analistas, 1),
            "avg_total": round(total_tickets / num_analistas, 1)
        }

        sorted_by_pending = sorted(analistas_carga, key=lambda a: a['pending'], reverse=True)
        sorted_by_active = sorted(analistas_carga, key=lambda a: a['carga_activa'], reverse=True)
        sorted_by_resolved = sorted(analistas_carga, key=lambda a: a['resolved'], reverse=True)

        top_pending = sorted_by_pending[0] if sorted_by_pending else None
        top_active = sorted_by_active[0] if sorted_by_active else None
        top_resolved = sorted_by_resolved[0] if sorted_by_resolved else None

        top_2_activos = sum(a['carga_activa'] for a in sorted_by_active[:2]) if len(sorted_by_active) >= 2 else 0
        concentrada = (top_2_activos / carga_activa_total > 0.50) if carga_activa_total > 0 else False

        diagnostico = {
            "top_pending": top_pending,
            "top_active": top_active,
            "top_resolved": top_resolved,
            "carga_concentrada": concentrada,
            "pct_concentracion_top2": round((top_2_activos / carga_activa_total * 100), 1) if carga_activa_total > 0 else 0.0,
            "total_criticos": sum(1 for a in analistas_carga if a['nivel_carga'] == 'CRITICA'),
            "total_moderados": sum(1 for a in analistas_carga if a['nivel_carga'] == 'MODERADA'),
            "total_balanceados": sum(1 for a in analistas_carga if a['nivel_carga'] == 'BALANCEADA'),
            "total_en_standby": sum(1 for a in analistas_carga if a['en_standby'])
        }

        # Preparar métricas diferenciales globales del equipo
        total_resueltos_periodo = sum(a['diferencial_corte']['diff_resolved'] for a in analistas_carga)
        balance_neto_activa = sum(a['diferencial_corte']['diff_activa'] for a in analistas_carga)
        total_inflow_periodo = sum(a['diferencial_corte']['inflow_estimado'] for a in analistas_carga)
        total_estancados = sum(1 for a in analistas_carga if a['diferencial_corte']['estado_flujo'] == 'ESTANCADO')
        total_alta_velocidad = sum(1 for a in analistas_carga if a['diferencial_corte']['estado_flujo'] == 'ALTA_VELOCIDAD')
        total_atascos = sum(1 for a in analistas_carga if a['diferencial_corte']['estado_flujo'] == 'CUELLO_BOTELLA')

        diferencial_global = {
            "tiene_anterior": bool(archivo_anterior),
            "archivo_anterior": {
                "id": archivo_anterior['id'] if archivo_anterior else None,
                "nombre_archivo": archivo_anterior['nombre_archivo_resultante'] if archivo_anterior else None,
                "fecha_recepcion": archivo_anterior['fecha_recepcion'] if archivo_anterior else None
            } if archivo_anterior else None,
            "total_resueltos_periodo": total_resueltos_periodo,
            "balance_neto_activa": balance_neto_activa,
            "total_inflow_periodo": total_inflow_periodo,
            "total_estancados": total_estancados,
            "total_alta_velocidad": total_alta_velocidad,
            "total_atascos": total_atascos
        }

        # Preparar listado de archivos disponibles para el frontend selector
        archivos_dropdown = []
        for idx, a in enumerate(archivos_disponibles):
            f_rec = str(a['fecha_recepcion'])
            is_first = (idx == 0)
            tag = " (Último Archivo Cargado)" if is_first else ""
            archivos_dropdown.append({
                "id": a['id'],
                "id_unico": a['id_unico'],
                "nombre_archivo": a['nombre_archivo_resultante'],
                "fecha_recepcion": f_rec,
                "asunto_correo": a.get('asunto_correo') or 'Reporte Diario tickets Analistas',
                "estado_analisis": a.get('estado_analisis') or 'PROCESADO',
                "label": f"{a['nombre_archivo_resultante']} — {f_rec}{tag}",
                "es_ultimo": is_first
            })

        archivo_info = {
            "id": archivo_seleccionado['id'],
            "id_unico": archivo_seleccionado['id_unico'],
            "nombre_archivo": archivo_seleccionado['nombre_archivo_resultante'],
            "fecha_recepcion": selected_fecha_recepcion,
            "fecha_corte": selected_fecha_recepcion[:10],
            "hora_corte": selected_fecha_recepcion[11:19] if len(selected_fecha_recepcion) >= 19 else '',
            "asunto_correo": archivo_seleccionado.get('asunto_correo') or 'Reporte Diario tickets Analistas',
            "remitente_correo": archivo_seleccionado.get('remitente_correo') or '',
            "estado_analisis": archivo_seleccionado.get('estado_analisis') or 'PROCESADO',
            "es_ultimo": es_ultimo,
            "total_analistas": len(analistas_carga),
            "total_tickets": total_tickets
        }

        return jsonify({
            "archivo_info": archivo_info,
            "archivos_disponibles": archivos_dropdown,
            "diferencial_global": diferencial_global,
            "fecha_corte": selected_fecha_recepcion[:10],
            "fecha_corte_completa": selected_fecha_recepcion,
            "fecha_activa_label": f"{archivo_info['nombre_archivo']} ({selected_fecha_recepcion})",
            "es_corte_actual": es_ultimo,
            "info_semanal": {
                "semana_numero": semana_num,
                "anio": anio_corte,
                "fecha_inicio_semana": lunes_str,
                "fecha_fin_semana": domingo_str,
                "label": f"Semana {semana_num} ({lunes_str} al {domingo_str})",
                "turnos_standby_activos": standby_activos
            },
            "resumen_carga": {
                "carga_activa_total": carga_activa_total,
                "total_pending": total_pending,
                "total_queued": total_queued,
                "total_resolved": total_resolved,
                "total_tickets": total_tickets,
                "tasa_desahogo_global_pct": round((total_resolved / total_tickets * 100), 2) if total_tickets > 0 else 0.0,
                "sobrecargados_count": diagnostico["total_criticos"],
                "moderados_count": diagnostico["total_moderados"],
                "balanceados_count": diagnostico["total_balanceados"]
            },
            "promedios_equipo": promedios_equipo,
            "diagnostico": diagnostico,
            "analistas": analistas_carga,
            "grupos": grupos_carga,
            "evolucion_analistas": evolucion_por_analista,
            "consolidado_temporal": consolidado_temporal
        })

    except Exception as e:
        print(f"[ERROR] Error al procesar API /api/carga_trabajo: {e}")
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500


@app.route('/api/analista/<path:nombre>')
def get_analista_api(nombre):
    """API REST para obtener el análisis histórico y métricas individuales de un analista."""
    temporalidad = request.args.get('temporalidad', 'todos').lower()
    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos SQLite"}), 500

    try:
        cursor = conn.cursor()
        now = datetime.now()

        # Obtener lista de fechas disponibles y fecha más reciente en BDD
        cursor.execute(f"SELECT DISTINCT DATE(fecha_recepcion) as fecha FROM {DB_DATA_TABLE} ORDER BY fecha DESC;")
        fechas_disponibles = [str(r['fecha']) for r in fetchall_dicts(cursor)]
        max_fecha = fechas_disponibles[0] if fechas_disponibles else now.strftime("%Y-%m-%d")

        cursor.execute(f"SELECT COUNT(*) FROM {DB_DATA_TABLE} WHERE DATE(fecha_recepcion) = CURDATE();")
        tiene_hoy = cursor.fetchone()[0] > 0
        fecha_corte = now.strftime("%Y-%m-%d") if tiene_hoy else max_fecha

        where_clause = f"WHERE assign_to_individual = ?"
        params = [nombre]

        if temporalidad in ('dia', 'actual', 'hoy'):
            where_clause += " AND DATE(fecha_recepcion) = ?"
            params.append(fecha_corte)
        elif temporalidad == 'mes':
            where_clause += f" AND YEAR(fecha_recepcion) = {now.year} AND MONTH(fecha_recepcion) = {now.month}"
        elif temporalidad == 'semestre':
            current_sem = 1 if now.month <= 6 else 2
            if current_sem == 1:
                where_clause += f" AND YEAR(fecha_recepcion) = {now.year} AND MONTH(fecha_recepcion) BETWEEN 1 AND 6"
            else:
                where_clause += f" AND YEAR(fecha_recepcion) = {now.year} AND MONTH(fecha_recepcion) BETWEEN 7 AND 12"
        elif temporalidad == 'ano':
            where_clause += f" AND YEAR(fecha_recepcion) = {now.year}"

        query_history = f"""
        SELECT 
            id, id_unico, fecha_recepcion, fecha_creacion,
            assign_to_group, assign_to_individual,
            pending, queued, resolved, (pending + queued + resolved) as total
        FROM {DB_DATA_TABLE}
        {where_clause}
        ORDER BY fecha_recepcion ASC;
        """
        cursor.execute(query_history, params)
        rows_history = fetchall_dicts(cursor)

        cursor.close()
        conn.close()

        tot_pending = sum(to_int(r['pending']) for r in rows_history)
        tot_queued = sum(to_int(r['queued']) for r in rows_history)
        tot_resolved = sum(to_int(r['resolved']) for r in rows_history)
        tot_tickets = sum(to_int(r['total']) for r in rows_history)
        tasa_cierre = round((tot_resolved / tot_tickets * 100), 2) if tot_tickets > 0 else 0.0

        group_name = rows_history[0]['assign_to_group'] if rows_history else 'Desconocido'

        for r in rows_history:
            f_val = r.get('fecha_recepcion')
            if isinstance(f_val, datetime):
                f_str = f_val.strftime("%Y-%m-%d %H:%M:%S")
                f_corta = f_val.strftime("%Y-%m-%d %H:%M")
            elif f_val:
                f_str = str(f_val).strip()
                f_corta = f_str[:16]
            else:
                f_str = "Sin Fecha"
                f_corta = "Sin Fecha"

            r['fecha_recepcion'] = f_str
            r['fecha_recepcion_str'] = f_str
            r['fecha_corta'] = f_corta
            r['pending'] = to_int(r['pending'])
            r['queued'] = to_int(r['queued'])
            r['resolved'] = to_int(r['resolved'])
            r['total'] = to_int(r['total'])

        return jsonify({
            "nombre": nombre,
            "grupo": group_name,
            "temporalidad": temporalidad,
            "totales": {
                "pending": tot_pending,
                "queued": tot_queued,
                "resolved": tot_resolved,
                "total": tot_tickets,
                "tasa_cierre_pct": tasa_cierre
            },
            "historico": rows_history
        })

    except Exception as e:
        print(f"[ERROR] Error al procesar API /api/analista: {e}")
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500


@app.route('/api/historial_ejecuciones')
def get_historial_ejecuciones_api():
    """API REST para obtener el listado histórico de ejecuciones del proceso de ingesta."""
    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a SQLite"}), 500
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT id, fecha_inicio, fecha_fin, duracion_segundos, tipo, estado,
                   correos_encontrados, correos_procesados, filas_insertadas, mensaje,
                   SUBSTR(log_salida, 1, 300) as log_resumen
            FROM {DB_HISTORIAL_TABLE}
            ORDER BY id DESC
            LIMIT 100;
        """)
        rows = fetchall_dicts(cursor)
        cursor.close()
        conn.close()
        return jsonify({
            "total_registros": len(rows),
            "ejecuciones": rows
        })
    except Exception as e:
        print(f"[ERROR] Error al consultar historial: {e}")
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500


@app.route('/api/historial_ejecuciones/<int:id_ejecucion>')
def get_detalle_ejecucion_api(id_ejecucion):
    """API REST para obtener el detalle y log completo de una ejecución específica."""
    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a SQLite"}), 500
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {DB_HISTORIAL_TABLE} WHERE id = ?;", (id_ejecucion,))
        row = fetchone_dict(cursor)
        cursor.close()
        conn.close()
        if not row:
            return jsonify({"error": "Ejecución no encontrada"}), 404
        return jsonify(row)
    except Exception as e:
        print(f"[ERROR] Error al consultar ejecución {id_ejecucion}: {e}")
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500


@app.route('/api/ejecutar_ingesta', methods=['POST'])
def post_ejecutar_ingesta_api():
    """API REST para disparar una sincronización manual e inmediata de correos Outlook en segundo plano."""
    if ejecucion_activa_info["en_proceso"]:
        return jsonify({
            "status": "ocupado",
            "mensaje": "Ya existe una sincronización de correos en curso en el servidor.",
            "ejecucion_activa": ejecucion_activa_info
        }), 409

    t = threading.Thread(target=ejecutar_proceso_ingesta, args=('MANUAL_WEB',), daemon=True, name="ManualIngestionThread")
    t.start()
    return jsonify({
        "status": "iniciado",
        "mensaje": "Sincronización manual iniciada en segundo plano con Outlook."
    }), 202


@app.route('/api/estado_scheduler')
def get_estado_scheduler_api():
    """API REST para consultar el estado del servicio programador y métricas globales."""
    proxima_str = PROXIMA_EJECUCION_TIMESTAMP.strftime("%Y-%m-%d %H:%M:%S") if PROXIMA_EJECUCION_TIMESTAMP else None
    conn = conectar_bdd()
    ultima_ejecucion = None
    metricas = {"total": 0, "exitosas": 0, "errores": 0, "en_proceso": 0}
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT id, fecha_inicio, fecha_fin, duracion_segundos, tipo, estado, mensaje FROM {DB_HISTORIAL_TABLE} ORDER BY id DESC LIMIT 1;")
            ultima_ejecucion = fetchone_dict(cur)

            cur.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN estado = 'EXITO' THEN 1 ELSE 0 END) as exitosas,
                    SUM(CASE WHEN estado = 'ERROR' THEN 1 ELSE 0 END) as errores,
                    SUM(CASE WHEN estado = 'EN_PROCESO' THEN 1 ELSE 0 END) as en_proceso
                FROM {DB_HISTORIAL_TABLE};
            """)
            m = fetchone_dict(cur)
            if m:
                metricas = {
                    "total": to_int(m.get('total')),
                    "exitosas": to_int(m.get('exitosas')),
                    "errores": to_int(m.get('errores')),
                    "en_proceso": to_int(m.get('en_proceso'))
                }
            cur.close()
            conn.close()
        except Exception:
            pass

    return jsonify({
        "servicio_activo": True,
        "intervalo_segundos": SCHEDULER_INTERVAL_SECONDS,
        "intervalo_horas": 1,
        "en_proceso": ejecucion_activa_info["en_proceso"],
        "ejecucion_activa": ejecucion_activa_info,
        "proxima_ejecucion": proxima_str,
        "ultima_ejecucion": ultima_ejecucion,
        "metricas": metricas
    })


# --------------------------------------------------------------------------
# API REST: OBSERVACIONES DE CARGA DE TRABAJO
# --------------------------------------------------------------------------
@app.route('/api/observaciones_carga', methods=['GET', 'POST'])
def api_observaciones_carga():
    """API REST para consultar y guardar observaciones de supervisión para cada especialista."""
    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos SQLite"}), 500
    try:
        cur = conn.cursor()
        if request.method == 'GET':
            cur.execute(f"SELECT * FROM {DB_OBSERVACIONES_TABLE} ORDER BY fecha_actualizacion DESC;")
            rows = fetchall_dicts(cur)
            cur.close()
            conn.close()
            return jsonify({"observaciones": rows})

        elif request.method == 'POST':
            data = request.get_json(force=True, silent=True) or {}
            individual = data.get('assign_to_individual', '').strip()
            observacion = data.get('observacion', '').strip()
            usuario = data.get('usuario_registro', 'Supervisor TI').strip()
            ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not individual:
                cur.close()
                conn.close()
                return jsonify({"error": "assign_to_individual es obligatorio"}), 400

            cur.execute(f"""
                INSERT INTO {DB_OBSERVACIONES_TABLE} (assign_to_individual, observacion, usuario_registro, fecha_actualizacion)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(assign_to_individual) DO UPDATE SET
                    observacion = excluded.observacion,
                    usuario_registro = excluded.usuario_registro,
                    fecha_actualizacion = excluded.fecha_actualizacion;
            """, (individual, observacion, usuario, ahora_str))
            conn.commit()

            cur.execute(f"SELECT * FROM {DB_OBSERVACIONES_TABLE} WHERE assign_to_individual = ?;", (individual,))
            saved = fetchone_dict(cur)
            cur.close()
            conn.close()
            return jsonify({"status": "ok", "registro": saved})

    except Exception as e:
        print(f"[ERROR] Error en api_observaciones_carga: {e}")
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------------------------------
# API REST: GESTIÓN DE TURNOS DE STANDBY / GUARDIAS
# --------------------------------------------------------------------------
@app.route('/api/standby', methods=['GET', 'POST'])
def api_standby():
    """API REST para listar turnos de standby con filtros y crear nuevos turnos."""
    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a SQLite"}), 500
    try:
        cur = conn.cursor()
        if request.method == 'GET':
            tipo_periodo = request.args.get('tipo_periodo', '').upper()
            anio = request.args.get('anio', '')
            mes = request.args.get('mes', '')
            semana = request.args.get('semana', '')
            estado = request.args.get('estado', '').upper()

            where_clauses = []
            params = []

            if tipo_periodo and tipo_periodo != 'TODOS':
                where_clauses.append("tipo_periodo = ?")
                params.append(tipo_periodo)
            if anio and anio != 'TODOS':
                where_clauses.append("anio = ?")
                params.append(int(anio))
            if mes and mes != 'TODOS':
                where_clauses.append("mes = ?")
                params.append(int(mes))
            if semana and semana != 'TODOS':
                where_clauses.append("semana_anio = ?")
                params.append(int(semana))
            if estado and estado != 'TODOS':
                where_clauses.append("estado = ?")
                params.append(estado)

            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
            query = f"""
                SELECT * FROM {DB_STANDBY_TABLE}
                {where_sql}
                ORDER BY anio DESC, semana_anio DESC, fecha_inicio DESC;
            """
            cur.execute(query, params)
            rows = fetchall_dicts(cur)

            hoy_str = datetime.now().strftime("%Y-%m-%d")
            cur.execute(f"""
                SELECT * FROM {DB_STANDBY_TABLE}
                WHERE (? BETWEEN fecha_inicio AND fecha_fin) OR estado = 'ACTIVO'
                ORDER BY CASE WHEN estado = 'ACTIVO' THEN 1 ELSE 2 END, fecha_inicio DESC
                LIMIT 1;
            """, (hoy_str,))
            turno_actual = fetchone_dict(cur)

            # Obtener semanas disponibles registradas
            cur.execute(f"SELECT DISTINCT semana_anio, anio FROM {DB_STANDBY_TABLE} ORDER BY anio DESC, semana_anio DESC;")
            semanas_registradas = fetchall_dicts(cur)

            cur.close()
            conn.close()
            return jsonify({
                "total": len(rows),
                "turnos": rows,
                "turno_actual": turno_actual,
                "semanas_registradas": semanas_registradas,
                "fecha_consulta": hoy_str
            })

        elif request.method == 'POST':
            data = request.get_json(force=True, silent=True) or {}
            individual = data.get('assign_to_individual', '').strip()
            group = data.get('assign_to_group', '').strip()
            tipo_periodo = data.get('tipo_periodo', 'SEMANAL').upper()
            fecha_inicio = data.get('fecha_inicio', '').strip()
            fecha_fin = data.get('fecha_fin', '').strip()
            telefono = data.get('telefono_contacto', '').strip()
            estado = data.get('estado', 'PROGRAMADO').upper()
            notas = data.get('notas', '').strip()

            if not individual or not fecha_inicio or not fecha_fin:
                cur.close()
                conn.close()
                return jsonify({"error": "individual, fecha_inicio y fecha_fin son obligatorios"}), 400

            try:
                ini_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
                semana_anio = int(data.get('semana_anio')) if data.get('semana_anio') else ini_dt.isocalendar()[1]
                mes = int(data.get('mes')) if data.get('mes') else ini_dt.month
                anio = int(data.get('anio')) if data.get('anio') else ini_dt.year
            except Exception:
                semana_anio = 1
                mes = 1
                anio = datetime.now().year

            dia_semana = data.get('dia_semana', '') or 'Lunes a Domingo'
            ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(f"""
                INSERT INTO {DB_STANDBY_TABLE}
                (assign_to_individual, assign_to_group, tipo_periodo, fecha_inicio, fecha_fin,
                 semana_anio, dia_semana, mes, anio, telefono_contacto, estado, notas, fecha_creacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (individual, group, tipo_periodo, fecha_inicio, fecha_fin,
                  semana_anio, dia_semana, mes, anio, telefono, estado, notas, ahora_str))
            conn.commit()
            new_id = cur.lastrowid

            cur.execute(f"SELECT * FROM {DB_STANDBY_TABLE} WHERE id = ?;", (new_id,))
            created = fetchone_dict(cur)
            cur.close()
            conn.close()
            return jsonify({"status": "creado", "turno": created}), 201

    except Exception as e:
        print(f"[ERROR] Error en api_standby POST/GET: {e}")
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500


@app.route('/api/standby/<int:turno_id>', methods=['GET', 'PUT', 'DELETE'])
def api_standby_detalle(turno_id):
    """API REST para obtener, modificar o eliminar un turno de standby específico."""
    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a SQLite"}), 500
    try:
        cur = conn.cursor()
        if request.method == 'GET':
            cur.execute(f"SELECT * FROM {DB_STANDBY_TABLE} WHERE id = ?;", (turno_id,))
            row = fetchone_dict(cur)
            cur.close()
            conn.close()
            if not row:
                return jsonify({"error": "Turno no encontrado"}), 404
            return jsonify(row)

        elif request.method == 'PUT':
            data = request.get_json(force=True, silent=True) or {}
            individual = data.get('assign_to_individual', '').strip()
            group = data.get('assign_to_group', '').strip()
            tipo_periodo = data.get('tipo_periodo', 'SEMANAL').upper()
            fecha_inicio = data.get('fecha_inicio', '').strip()
            fecha_fin = data.get('fecha_fin', '').strip()
            telefono = data.get('telefono_contacto', '').strip()
            estado = data.get('estado', 'PROGRAMADO').upper()
            notas = data.get('notas', '').strip()

            if not individual or not fecha_inicio or not fecha_fin:
                cur.close()
                conn.close()
                return jsonify({"error": "individual, fecha_inicio y fecha_fin son obligatorios"}), 400

            try:
                ini_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
                semana_anio = int(data.get('semana_anio')) if data.get('semana_anio') else ini_dt.isocalendar()[1]
                mes = int(data.get('mes')) if data.get('mes') else ini_dt.month
                anio = int(data.get('anio')) if data.get('anio') else ini_dt.year
            except Exception:
                semana_anio = 1
                mes = 1
                anio = datetime.now().year

            dia_semana = data.get('dia_semana', '') or 'Lunes a Domingo'

            cur.execute(f"""
                UPDATE {DB_STANDBY_TABLE}
                SET assign_to_individual = ?,
                    assign_to_group = ?,
                    tipo_periodo = ?,
                    fecha_inicio = ?,
                    fecha_fin = ?,
                    semana_anio = ?,
                    dia_semana = ?,
                    mes = ?,
                    anio = ?,
                    telefono_contacto = ?,
                    estado = ?,
                    notas = ?
                WHERE id = ?;
            """, (individual, group, tipo_periodo, fecha_inicio, fecha_fin,
                  semana_anio, dia_semana, mes, anio, telefono, estado, notas, turno_id))
            conn.commit()

            cur.execute(f"SELECT * FROM {DB_STANDBY_TABLE} WHERE id = ?;", (turno_id,))
            updated = fetchone_dict(cur)
            cur.close()
            conn.close()
            return jsonify({"status": "actualizado", "turno": updated})

        elif request.method == 'DELETE':
            cur.execute(f"DELETE FROM {DB_STANDBY_TABLE} WHERE id = ?;", (turno_id,))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"status": "eliminado", "id": turno_id})

    except Exception as e:
        print(f"[ERROR] Error en api_standby_detalle: {e}")
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500


@app.route('/api/standby/actual')
def api_standby_actual():
    """Retorna quién está de turno de standby esta semana / fecha actual."""
    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a SQLite"}), 500
    try:
        cur = conn.cursor()
        hoy_str = datetime.now().strftime("%Y-%m-%d")
        
        cur.execute(f"""
            SELECT * FROM {DB_STANDBY_TABLE}
            WHERE (? BETWEEN fecha_inicio AND fecha_fin) OR estado = 'ACTIVO'
            ORDER BY CASE WHEN estado = 'ACTIVO' THEN 1 ELSE 2 END, fecha_inicio DESC
            LIMIT 1;
        """, (hoy_str,))
        row = fetchone_dict(cur)
        cur.close()
        conn.close()
        return jsonify({"turno_actual": row, "fecha": hoy_str})
    except Exception as e:
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500


@app.route('/api/analistas_lista')
def api_analistas_lista():
    """Retorna lista única de analistas y sus grupos para poblar dropdowns."""
    conn = conectar_bdd()
    if not conn:
        return jsonify({"error": "No se pudo conectar a SQLite"}), 500
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT assign_to_individual, assign_to_group, COUNT(*) as reportes_total
            FROM {DB_DATA_TABLE}
            GROUP BY assign_to_individual
            ORDER BY assign_to_individual ASC;
        """)
        rows = fetchall_dicts(cur)
        cur.close()
        conn.close()
        return jsonify({"analistas": rows})
    except Exception as e:
        if conn:
            try: conn.close()
            except Exception: pass
        return jsonify({"error": str(e)}), 500

# Iniciar planificador automático horaria
start_scheduler_once()

def find_available_port(preferred_port=5000, fallback_port=5050):
    env_port = os.environ.get('PORT')
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('0.0.0.0', preferred_port))
        s.close()
        return preferred_port
    except OSError:
        print(f"⚠️ Puerto {preferred_port} ocupado (otro servicio activo en el servidor). Usando puerto alterno {fallback_port}...")
        return fallback_port

if __name__ == '__main__':
    port = find_available_port()
    print(f"🚀 Servidor Web TI_GPF iniciado en http://127.0.0.1:{port} y http://172.22.14.27:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
