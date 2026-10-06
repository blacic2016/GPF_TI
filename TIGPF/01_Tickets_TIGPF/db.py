# --------------------------------------------------------------------------
# MÓDULO DE BASE DE DATOS SQLITE: db.py
# UBICACIÓN: db.py (Raíz del proyecto)
# DESCRIPCIÓN: Administra la conexión, inicialización y compatibilidad SQL
#              para la persistencia local de Tickets TI_GPF en SQLite.
# --------------------------------------------------------------------------

import os
import sqlite3
from datetime import datetime

# Rutas estándar del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "TI_GPF.db")
DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

# Nombres de tablas
DB_ARCHIVOS_TABLE = "GPF_01_Archivos_Procesados"
DB_DATA_TABLE = "GPF_01_Reporte_Diario_Tickets_Analistas"
DB_HISTORIAL_TABLE = "GPF_01_Historial_Ejecuciones"
DB_OBSERVACIONES_TABLE = "GPF_01_Observaciones_Carga"
DB_STANDBY_TABLE = "GPF_01_Turnos_Standby"

def _sqlite_curdate():
    """Función de compatibilidad SQL: CURDATE() -> 'YYYY-MM-DD'."""
    return datetime.now().strftime("%Y-%m-%d")

def _sqlite_year(date_str):
    """Función de compatibilidad SQL: YEAR('YYYY-MM-DD...') -> int."""
    if not date_str:
        return None
    try:
        val = str(date_str).strip()
        return int(val[:4])
    except Exception:
        return None

def _sqlite_month(date_str):
    """Función de compatibilidad SQL: MONTH('YYYY-MM-DD...') -> int."""
    if not date_str:
        return None
    try:
        val = str(date_str).strip()
        return int(val[5:7])
    except Exception:
        return None

def _sqlite_date(date_str):
    """Función de compatibilidad SQL: DATE('YYYY-MM-DD HH:MM:SS') -> 'YYYY-MM-DD'."""
    if not date_str:
        return None
    val = str(date_str).strip()
    return val[:10]

def registrar_funciones_compatibilidad(conn):
    """Registra funciones SQL para que queries con CURDATE(), YEAR(), MONTH() funcionen nativamente."""
    conn.create_function("CURDATE", 0, _sqlite_curdate)
    conn.create_function("YEAR", 1, _sqlite_year)
    conn.create_function("MONTH", 1, _sqlite_month)
    conn.create_function("DATE", 1, _sqlite_date)

def init_db(db_path=None, schema_path=None):
    """
    Inicializa la base de datos SQLite ejecutando el archivo schema.sql si las tablas no existen.
    """
    path = db_path or DB_PATH
    schema_file = schema_path or SCHEMA_PATH
    
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        if os.path.exists(schema_file):
            with open(schema_file, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        else:
            # Esquema inline de respaldo
            conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS {DB_ARCHIVOS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_unico INTEGER UNIQUE,
                asunto_correo TEXT,
                remitente_correo TEXT,
                nombre_archivo_resultante TEXT,
                fecha_recepcion TEXT,
                estado_analisis TEXT,
                fecha_creacion_registro TEXT,
                fecha_creacion TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_archivos_id_unico ON {DB_ARCHIVOS_TABLE}(id_unico);
            CREATE INDEX IF NOT EXISTS idx_archivos_fecha_recepcion ON {DB_ARCHIVOS_TABLE}(fecha_recepcion);

            CREATE TABLE IF NOT EXISTS {DB_DATA_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_unico INTEGER,
                fecha_recepcion TEXT,
                fecha_creacion TEXT,
                assign_to_group TEXT,
                assign_to_individual TEXT,
                pending INTEGER DEFAULT 0,
                queued INTEGER DEFAULT 0,
                resolved INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_tickets_id_unico ON {DB_DATA_TABLE}(id_unico);
            CREATE INDEX IF NOT EXISTS idx_tickets_fecha_recepcion ON {DB_DATA_TABLE}(fecha_recepcion);
            CREATE INDEX IF NOT EXISTS idx_tickets_analista ON {DB_DATA_TABLE}(assign_to_individual);
            CREATE INDEX IF NOT EXISTS idx_tickets_grupo ON {DB_DATA_TABLE}(assign_to_group);
            """)
        conn.commit()
    finally:
        conn.close()

def get_connection(use_row_factory=False, db_path=None):
    """
    Retorna una conexión a SQLite con WAL mode, claves foráneas y funciones de compatibilidad.
    Si use_row_factory=True, las filas devueltas se comportan como diccionarios (sqlite3.Row).
    """
    path = db_path or DB_PATH
    
    # Asegurar inicialización previa
    init_db(path)
    
    conn = sqlite3.connect(path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    registrar_funciones_compatibilidad(conn)
    
    if use_row_factory:
        conn.row_factory = sqlite3.Row
        
    return conn
