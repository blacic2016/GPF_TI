import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "novaiops.db")

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tabla de Usuarios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'operator', 'viewer')),
        status TEXT NOT NULL DEFAULT 'active',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Tabla de Mapeo de Carpetas de Outlook
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder_path TEXT NOT NULL UNIQUE,
        folder_name TEXT NOT NULL,
        monitor_active INTEGER NOT NULL DEFAULT 1,
        assigned_script_id INTEGER,
        use_ai INTEGER NOT NULL DEFAULT 0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (assigned_script_id) REFERENCES automation_scripts(id)
    );
    """)

    # Tabla del Gestor de Scripts de Automatización
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS automation_scripts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        script_name TEXT UNIQUE NOT NULL,
        description TEXT,
        category TEXT NOT NULL DEFAULT 'GENERAL',
        target_client TEXT DEFAULT 'TODOS',
        rule_type TEXT NOT NULL CHECK(rule_type IN ('DETERMINISTIC', 'AI_N8N')),
        subject_pattern TEXT,
        sender_pattern TEXT,
        body_extraction_rules TEXT, -- JSON string de reglas de regex
        script_code TEXT,           -- Código Python o ruta de módulo
        is_ai_enabled INTEGER NOT NULL DEFAULT 0,
        ai_prompt_template TEXT,
        n8n_webhook_url TEXT,       -- URL Webhook para alertas a n8n
        alarm_action TEXT DEFAULT 'LOG_ONLY', -- N8N_WEBHOOK, ZABBIX_ALARM, MANTIS_TICKET, LOG_ONLY
        post_processing_action TEXT DEFAULT 'MOVE_ANALIZADO',
        forward_enabled INTEGER DEFAULT 0,
        forward_email_target TEXT,
        forward_timing TEXT DEFAULT 'AFTER_ANALYSIS', -- BEFORE_ANALYSIS o AFTER_ANALYSIS
        target_folder_path TEXT,                       -- Carpeta MAPI de Outlook elegida obligatoria
        step1_enabled INTEGER DEFAULT 1,               -- Paso 1: Lectura/Captura MAPI
        step3_enabled INTEGER DEFAULT 1,               -- Paso 3: Análisis por Plantilla Python
        step4_enabled INTEGER DEFAULT 1,               -- Paso 4: Alertas & Post-Procesamiento
        status TEXT NOT NULL DEFAULT 'active',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Migración de columnas si la tabla ya existía
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN n8n_webhook_url TEXT")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN alarm_action TEXT DEFAULT 'LOG_ONLY'")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN post_processing_action TEXT DEFAULT 'MOVE_ANALIZADO'")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN forward_enabled INTEGER DEFAULT 0")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN forward_email_target TEXT")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN forward_timing TEXT DEFAULT 'AFTER_ANALYSIS'")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN target_folder_path TEXT")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN target_subfolder_name TEXT DEFAULT 'analizados'")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN attachment_filter_enabled INTEGER DEFAULT 0")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN attachment_pattern TEXT")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN external_webhook_url TEXT")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN step1_enabled INTEGER DEFAULT 1")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN step2_forward_enabled INTEGER DEFAULT 0")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN step2_analysis_enabled INTEGER DEFAULT 1")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN step3_enabled INTEGER DEFAULT 1")
    except Exception: pass
    try: cursor.execute("ALTER TABLE automation_scripts ADD COLUMN step4_enabled INTEGER DEFAULT 1")
    except Exception: pass

    # Tabla de Auditoría de Ejecuciones
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS execution_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        email_unixtime INTEGER,
        unique_key TEXT,
        email_sender TEXT,
        email_subject TEXT,
        folder_path TEXT,
        script_id INTEGER,
        script_name TEXT,
        execution_status TEXT NOT NULL CHECK(execution_status IN ('SUCCESS', 'FAILED', 'WARNING', 'SKIPPED')),
        execution_time_ms REAL,
        extracted_params TEXT, -- JSON string
        ai_payload_response TEXT, -- JSON de la IA
        error_details TEXT,
        FOREIGN KEY (script_id) REFERENCES automation_scripts(id)
    );
    """)

    try: cursor.execute("ALTER TABLE execution_logs ADD COLUMN email_unixtime INTEGER")
    except Exception: pass
    try: cursor.execute("ALTER TABLE execution_logs ADD COLUMN unique_key TEXT")
    except Exception: pass

    # Tabla de Alarmas del Sistema
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_alarms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        alarm_type TEXT NOT NULL, -- MAPI_DISCONNECT, SCRIPT_ERROR, PARSING_ERROR
        severity TEXT NOT NULL CHECK(severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
        message TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, ACKNOWLEDGED, RESOLVED
        resolved_at DATETIME
    );
    """)

    # Tabla de Salud y Telemetría de Microservicios Entrelazados
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS microservices_heartbeat (
        service_id TEXT PRIMARY KEY,
        service_name TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ONLINE', -- ONLINE, DEGRADED, OFFLINE
        last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP,
        metrics_json TEXT,                     -- Estadísticas (correos leídos, uptime, latencia)
        details TEXT
    );
    """)

    # Datos semilla de usuarios por defecto
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO users (username, password_hash, full_name, role) VALUES
        ('admin', 'scrypt:32768:8:1$admin123$hash', 'Administrador General Sonda', 'admin'),
        ('operador', 'scrypt:32768:8:1$operador123$hash', 'Operador IT NOC Sonda', 'operator'),
        ('cliente_viewer', 'scrypt:32768:8:1$viewer123$hash', 'Auditor de Monitoreo', 'viewer');
        """)

    # Datos semilla para carpetas de correo comunes
    cursor.execute("SELECT COUNT(*) FROM email_folders")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO email_folders (folder_path, folder_name, monitor_active, use_ai) VALUES
        ('Bandeja de entrada', 'Bandeja de entrada', 1, 0),
        ('Bandeja de entrada/GPF/HETRIX', 'HETRIX GPF', 1, 0),
        ('Bandeja de entrada/GPF/TOTEM', 'TOTEM GPF', 1, 0),
        ('Bandeja de entrada/GPF/NETWORKER', 'NETWORKER GPF', 1, 0),
        ('Bandeja de entrada/SONDA_AI_SONDA', 'SONDA Analizador IA', 1, 1),
        ('Bandeja de entrada/ANTIGRAVITY_TELEMETRY', 'Antigravity Telemetry & Physics', 1, 0),
        ('marco.vizcaino@sonda.com/Bandeja de entrada/synapse_org', 'SYNAPSE_ORG (marco.vizcaino@sonda.com)', 1, 1);
        """)

    # Datos semilla para scripts legacy convertidos
    cursor.execute("SELECT COUNT(*) FROM automation_scripts")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO automation_scripts 
        (script_name, description, category, target_client, rule_type, subject_pattern, sender_pattern, body_extraction_rules, script_code, is_ai_enabled)
        VALUES
        ('GPF_HETRIX_TOTAL', 'Analizador de alertas Hetrix DOWN/UP para GPF y apertura de tickets MantisBT', 'MONITOREO', 'GPF', 'DETERMINISTIC', '.*Hetrix.*', '.*@hetrix.com.*', '{"url_servicio": "https?://\\\\S+", "estado": "(DOWN|UP)"}', 'gpf_hetrix_handler', 0),
        ('GPF_TOTEM_TOTAL', 'Analizador de disponibilidad de Totems de autoatención GPF', 'MONITOREO', 'GPF', 'DETERMINISTIC', '.*TOTEM.*', '.*', '{"totem_id": "TOTEM-\\\\d+", "ip": "\\\\d+\\\\.\\\\d+\\\\.\\\\d+\\\\.\\\\d+"}', 'gpf_totem_handler', 0),
        ('GPF_NETWORKER_DIARIO', 'Verificador de respaldos diarios Networker Oracle/Sistema', 'BACKUP', 'GPF', 'DETERMINISTIC', '.*Networker.*Daily.*', '.*', '{"status": "(SUCCESS|FAILED)", "client": "\\\\w+"}', 'gpf_networker_handler', 0),
        ('SONDA_AI_ANALYZER', 'Analizador Cognitivo mediante IA Gemini y n8n para incidentes complejos de clientes', 'SONDA_AI', 'TODOS', 'AI_N8N', '.*', '.*', '{}', 'ai_sonda_handler', 1),
        ('ANTIGRAVITY_TELEMETRY_ENGINE', 'Motor de Telemetría No Lineal & Vectores de Estabilidad Física Antigravity', 'TELEMETRIA', 'TODOS', 'DETERMINISTIC', '.*(Antigravity|Telemetry|TEMP:).*', '.*', '{"temp_c": "TEMP[:=]\\\\s*([\\\\d.]+)", "jitter_ms": "JITTER[:=]\\\\s*([\\\\d.]+)"}', 'antigravity_handler', 0);
        """)

    # Datos semilla de logs de ejecución para visualización inicial
    cursor.execute("SELECT COUNT(*) FROM execution_logs")
    if cursor.fetchone()[0] == 0:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        INSERT INTO execution_logs 
        (received_at, email_sender, email_subject, folder_path, script_id, script_name, execution_status, execution_time_ms, extracted_params, ai_payload_response, error_details)
        VALUES
        (?, 'alerts@hetrix.com', 'Hetrix Alert: Service DOWN https://hetrix.com/s/123', 'Bandeja de entrada/GPF/HETRIX', 1, 'GPF_HETRIX_TOTAL', 'SUCCESS', 342.5, '{"url_servicio": "https://hetrix.com/s/123", "estado": "DOWN"}', NULL, NULL),
        (?, 'backup@gpf.com.ec', 'Networker Daily Backup Failed for Oracle_DB01', 'Bandeja de entrada/GPF/NETWORKER', 3, 'GPF_NETWORKER_DIARIO', 'SUCCESS', 512.1, '{"status": "FAILED", "client": "Oracle_DB01"}', NULL, NULL),
        (?, 'telemetry@antigravity.sonda.com', 'Antigravity Physics Report: TEMP:85.5 JITTER:135.0 ENERGY:18.4', 'Bandeja de entrada/ANTIGRAVITY_TELEMETRY', 5, 'ANTIGRAVITY_TELEMETRY_ENGINE', 'WARNING', 145.2, '{"instability_vector": 18.421, "confidence_level_pct": 4.21, "severity": "CRITICAL_PHYSICS_ANOMALY", "metrics_evaluated": {"temperature_c": 85.5, "jitter_ms": 135.0, "energy_kw": 18.4, "pressure_bar": 1.05}}', NULL, NULL),
        (?, 'soporte@leterago.com.ec', 'Falla crítica en servidor SAP HANA - Error 500', 'Bandeja de entrada/SONDA_AI_SONDA', 4, 'SONDA_AI_ANALYZER', 'SUCCESS', 1250.0, '{"cliente": "Leterago", "severidad": "CRITICAL"}', '{"categoria": "INCIDENTE_INFRAESTRUCTURA", "cliente_detectado": "Leterago", "severidad": "CRITICAL", "script_destino": "gpf_hetrix_handler", "razonamiento": "Falla de servidor detectada en SAP HANA con impacto alto."}', NULL),
        (?, 'monitor@zabbix.sonda.com', 'Correo corrupto o mal formado sin estructura', 'Bandeja de entrada', 1, 'GPF_HETRIX_TOTAL', 'FAILED', 120.0, '{}', NULL, 'RegexError: No se pudo extraer la variable url_servicio del cuerpo del correo.');
        """, (now_str, now_str, now_str, now_str, now_str))

    # Datos semilla para alarmas
    cursor.execute("SELECT COUNT(*) FROM system_alarms")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO system_alarms (alarm_type, severity, message, status) VALUES
        ('PHYSICS_ANOMALY', 'CRITICAL', 'Antigravity Instability Vector > 15.0 detectado en sensor de telemetría', 'ACTIVE'),
        ('PARSING_ERROR', 'HIGH', 'Falla de lectura de Regex en script GPF_HETRIX_TOTAL (Correo ID #5)', 'ACTIVE'),
        ('MAPI_INFO', 'LOW', 'Demonio NOVAIOPS MAPI reiniciado correctamente', 'RESOLVED');
        """)

    conn.commit()
    conn.close()
    print("Base de datos NOVAIOPS inicializada exitosamente.")

if __name__ == "__main__":
    init_db()
