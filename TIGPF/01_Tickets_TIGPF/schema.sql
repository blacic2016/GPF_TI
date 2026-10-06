-- ============================================================================
-- ESQUEMA DE BASE DE DATOS SQLITE: TI_GPF.db
-- Sistema de Monitoreo, Ingesta y Dashboard de Tickets Analistas (TIGPF)
-- ============================================================================

-- Tabla 1: GPF_01_Archivos_Procesados
-- Almacena los metadatos de los correos procesados y archivos adjuntos descargados.
CREATE TABLE IF NOT EXISTS GPF_01_Archivos_Procesados (
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

-- Índices para GPF_01_Archivos_Procesados
CREATE INDEX IF NOT EXISTS idx_archivos_id_unico ON GPF_01_Archivos_Procesados(id_unico);
CREATE INDEX IF NOT EXISTS idx_archivos_fecha_recepcion ON GPF_01_Archivos_Procesados(fecha_recepcion);

-- Tabla 2: GPF_01_Reporte_Diario_Tickets_Analistas
-- Almacena los registros estructurados de tickets por analista y grupo.
CREATE TABLE IF NOT EXISTS GPF_01_Reporte_Diario_Tickets_Analistas (
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

-- Índices para GPF_01_Reporte_Diario_Tickets_Analistas
CREATE INDEX IF NOT EXISTS idx_tickets_id_unico ON GPF_01_Reporte_Diario_Tickets_Analistas(id_unico);
CREATE INDEX IF NOT EXISTS idx_tickets_fecha_recepcion ON GPF_01_Reporte_Diario_Tickets_Analistas(fecha_recepcion);
CREATE INDEX IF NOT EXISTS idx_tickets_analista ON GPF_01_Reporte_Diario_Tickets_Analistas(assign_to_individual);
CREATE INDEX IF NOT EXISTS idx_tickets_grupo ON GPF_01_Reporte_Diario_Tickets_Analistas(assign_to_group);

-- Tabla 3: GPF_01_Historial_Ejecuciones
-- Registra el historial de ejecuciones periódicas o manuales de la ingesta de correos Outlook.
CREATE TABLE IF NOT EXISTS GPF_01_Historial_Ejecuciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_inicio TEXT NOT NULL,
    fecha_fin TEXT,
    duracion_segundos REAL,
    tipo TEXT DEFAULT 'AUTOMATICA_HORARIA', -- 'AUTOMATICA_HORARIA' o 'MANUAL_WEB'
    estado TEXT DEFAULT 'EN_PROCESO',      -- 'EXITO', 'ERROR', 'EN_PROCESO'
    correos_encontrados INTEGER DEFAULT 0,
    correos_procesados INTEGER DEFAULT 0,
    filas_insertadas INTEGER DEFAULT 0,
    mensaje TEXT,
    log_salida TEXT
);

CREATE INDEX IF NOT EXISTS idx_historial_fecha_inicio ON GPF_01_Historial_Ejecuciones(fecha_inicio);
CREATE INDEX IF NOT EXISTS idx_historial_estado ON GPF_01_Historial_Ejecuciones(estado);

-- Tabla 4: GPF_01_Observaciones_Carga
-- Almacena notas y observaciones de supervisión para cada especialista en el análisis de carga de trabajo.
CREATE TABLE IF NOT EXISTS GPF_01_Observaciones_Carga (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assign_to_individual TEXT NOT NULL UNIQUE,
    observacion TEXT,
    usuario_registro TEXT DEFAULT 'Supervisor TI',
    fecha_actualizacion TEXT
);

CREATE INDEX IF NOT EXISTS idx_observaciones_analista ON GPF_01_Observaciones_Carga(assign_to_individual);

-- Tabla 5: GPF_01_Turnos_Standby
-- Administra la asignación y programación de turnos de standby/guardias (diario, semanal, mensual).
CREATE TABLE IF NOT EXISTS GPF_01_Turnos_Standby (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assign_to_individual TEXT NOT NULL,
    assign_to_group TEXT,
    tipo_periodo TEXT DEFAULT 'SEMANAL', -- 'DIARIO', 'SEMANAL', 'MENSUAL'
    fecha_inicio TEXT NOT NULL,          -- 'YYYY-MM-DD'
    fecha_fin TEXT NOT NULL,             -- 'YYYY-MM-DD'
    semana_anio INTEGER,
    dia_semana TEXT,
    mes INTEGER,
    anio INTEGER,
    telefono_contacto TEXT,
    estado TEXT DEFAULT 'ACTIVO',        -- 'ACTIVO', 'PROGRAMADO', 'COMPLETADO', 'CANCELADO'
    notas TEXT,
    fecha_creacion TEXT
);

CREATE INDEX IF NOT EXISTS idx_standby_fechas ON GPF_01_Turnos_Standby(fecha_inicio, fecha_fin);
CREATE INDEX IF NOT EXISTS idx_standby_analista ON GPF_01_Turnos_Standby(assign_to_individual);
CREATE INDEX IF NOT EXISTS idx_standby_semana ON GPF_01_Turnos_Standby(semana_anio, anio);


