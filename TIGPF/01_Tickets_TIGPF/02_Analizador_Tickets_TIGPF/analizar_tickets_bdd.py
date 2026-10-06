# --------------------------------------------------------------------------
# SCRIPT: analizar_tickets_bdd.py
# UBICACIÓN: 02_Analizador_Tickets_TIGPF/analizar_tickets_bdd.py
# DESCRIPCIÓN: Analizador avanzado de datos almacenados en MySQL 'TI_GPF'.
#              Genera reportes de tickets por usuario/analista, por grupo,
#              tasas de cierre/efectividad, resumen general de ejecución,
#              y exporta reportes en JSON y Excel.
# --------------------------------------------------------------------------

import os
import sys
import json
import sqlite3
import pandas as pd
from datetime import datetime

# Permitir importar db.py desde el directorio raíz
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)
import db

# Configurar encoding UTF-8 en consola Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Configuración de base de datos SQLite
DB_PATH = db.DB_PATH
DB_DATA_TABLE = db.DB_DATA_TABLE
DB_ARCHIVOS_TABLE = db.DB_ARCHIVOS_TABLE

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def conectar_bdd():
    """Conecta a la base de datos SQLite TI_GPF."""
    try:
        conn = db.get_connection()
        return conn
    except sqlite3.Error as err:
        print(f"[ERROR] No se pudo conectar a SQLite DB '{DB_PATH}': {err}")
        return None

def cargar_datos_bdd():
    """Carga los registros de tickets y metadatos desde SQLite."""
    conn = conectar_bdd()
    if not conn:
        return None, None

    try:
        query_data = f"""
        SELECT 
            id, id_unico, fecha_recepcion, fecha_creacion,
            assign_to_group, assign_to_individual,
            pending, queued, resolved, (pending + queued + resolved) AS total
        FROM {DB_DATA_TABLE}
        ORDER BY fecha_recepcion DESC, assign_to_group, assign_to_individual;
        """
        df_data = pd.read_sql(query_data, conn)

        query_archivos = f"""
        SELECT 
            id, id_unico, asunto_correo, remitente_correo,
            nombre_archivo_resultante, fecha_recepcion, estado_analisis, fecha_creacion
        FROM {DB_ARCHIVOS_TABLE}
        ORDER BY fecha_recepcion DESC;
        """
        df_archivos = pd.read_sql(query_archivos, conn)

        conn.close()
        return df_data, df_archivos

    except Exception as e:
        print(f"[ERROR] Error al consultar datos desde SQLite: {e}")
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return None, None

def realizar_analisis(df_data, df_archivos):
    """Realiza las agregaciones y métricas del análisis de tickets."""
    if df_data is None or df_data.empty:
        print("[WARNING] No hay datos de tickets almacenados en la base de datos.")
        return None

    # 1. Métricas Generales del Sistema
    total_reportes = df_data['id_unico'].nunique()
    total_tickets = int(df_data['total'].sum())
    total_resolved = int(df_data['resolved'].sum())
    total_pending = int(df_data['pending'].sum())
    total_queued = int(df_data['queued'].sum())
    
    tasa_cierre_global = round((total_resolved / total_tickets * 100), 2) if total_tickets > 0 else 0.0

    resumen_general = {
        "fecha_analisis": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_reportes_procesados": total_reportes,
        "total_archivos_registrados": len(df_archivos) if df_archivos is not None else 0,
        "total_tickets": total_tickets,
        "total_resueltos": total_resolved,
        "total_pendientes": total_pending,
        "total_en_cola": total_queued,
        "tasa_cierre_global_pct": tasa_cierre_global
    }

    # 2. Análisis por Usuario / Analista
    df_analista = df_data.groupby(['assign_to_group', 'assign_to_individual']).agg({
        'pending': 'sum',
        'queued': 'sum',
        'resolved': 'sum',
        'total': 'sum'
    }).reset_index()

    df_analista['tasa_cierre_pct'] = df_analista.apply(
        lambda r: round((r['resolved'] / r['total'] * 100), 2) if r['total'] > 0 else 0.0, axis=1
    )
    df_analista = df_analista.sort_values(by='total', ascending=False)

    # 3. Análisis por Grupo de Atención
    df_grupo = df_data.groupby('assign_to_group').agg({
        'pending': 'sum',
        'queued': 'sum',
        'resolved': 'sum',
        'total': 'sum',
        'assign_to_individual': 'nunique'
    }).reset_index().rename(columns={'assign_to_individual': 'total_analistas'})

    df_grupo['tasa_cierre_pct'] = df_grupo.apply(
        lambda r: round((r['resolved'] / r['total'] * 100), 2) if r['total'] > 0 else 0.0, axis=1
    )
    df_grupo = df_grupo.sort_values(by='total', ascending=False)

    # 4. Histórico por Reporte Recibido (Corte de Fecha)
    df_corte = df_data.groupby(['id_unico', 'fecha_recepcion']).agg({
        'pending': 'sum',
        'queued': 'sum',
        'resolved': 'sum',
        'total': 'sum',
        'assign_to_individual': 'nunique'
    }).reset_index().rename(columns={'assign_to_individual': 'analistas_reportados'})

    df_corte['tasa_cierre_pct'] = df_corte.apply(
        lambda r: round((r['resolved'] / r['total'] * 100), 2) if r['total'] > 0 else 0.0, axis=1
    )
    df_corte = df_corte.sort_values(by='fecha_recepcion', ascending=False)

    return {
        "resumen_general": resumen_general,
        "df_analista": df_analista,
        "df_grupo": df_grupo,
        "df_corte": df_corte
    }

def imprimir_dashboard_consola(analisis):
    """Muestra un informe ejecutivo formateado en consola."""
    gen = analisis["resumen_general"]
    df_analista = analisis["df_analista"]
    df_grupo = analisis["df_grupo"]

    print("\n" + "="*80)
    print("      📊 DASHBOARD Y ANÁLISIS GENERAL DE TICKETS - BASE DE DATOS TI_GPF      ")
    print("="*80)
    print(f" 📅 Fecha de Análisis:               {gen['fecha_analisis']}")
    print(f" 📑 Reportes Procesados:              {gen['total_reportes_procesados']}")
    print(f" 🏷️  Archivos Registrados BDD:        {gen['total_archivos_registrados']}")
    print(f" 🎟️  Total Tickets Evaluados:         {gen['total_tickets']}")
    print(f" ✅ Tickets Resueltos (Resolved):    {gen['total_resueltos']} ({gen['tasa_cierre_global_pct']}%)")
    print(f" ⏳ Tickets Pendientes (Pending):     {gen['total_pendientes']}")
    print(f" 📥 Tickets En Cola (Queued):         {gen['total_en_cola']}")
    print("="*80)

    print("\n--- 🏢 RESUMEN POR GRUPO DE ATENCIÓN ---")
    print(f"{'Grupo':<30} | {'Analistas':<10} | {'Pending':<8} | {'Queued':<8} | {'Resolved':<8} | {'Total':<8} | {'% Cierre':<8}")
    print("-" * 95)
    for _, r in df_grupo.iterrows():
        print(f"{r['assign_to_group']:<30} | {r['total_analistas']:<10} | {r['pending']:<8} | {r['queued']:<8} | {r['resolved']:<8} | {r['total']:<8} | {r['tasa_cierre_pct']:<8}%")

    print("\n--- 👤 RESUMEN POR ANALISTA / ESPECIALISTA ---")
    print(f"{'Especialista / Analista':<35} | {'Grupo':<25} | {'Pend.':<6} | {'Queue':<6} | {'Resul.':<6} | {'Total':<6} | {'% Cierre':<8}")
    print("-" * 105)
    for _, r in df_analista.iterrows():
        print(f"{r['assign_to_individual']:<35} | {r['assign_to_group']:<25} | {r['pending']:<6} | {r['queued']:<6} | {r['resolved']:<6} | {r['total']:<6} | {r['tasa_cierre_pct']:<8}%")

    print("="*105 + "\n")

def exportar_reportes(analisis, df_data, df_archivos):
    """Exporta el análisis a formato JSON y archivo Excel."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Exportar JSON
    json_data = {
        "resumen_general": analisis["resumen_general"],
        "desglose_grupos": analisis["df_grupo"].to_dict(orient="records"),
        "desglose_analistas": analisis["df_analista"].to_dict(orient="records"),
        "historico_reportes": analisis["df_corte"].to_dict(orient="records")
    }
    
    json_file = os.path.join(OUTPUT_DIR, "resumen_analisis_tickets.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4, ensure_ascii=False, default=str)
    print(f"[OK] Reporte JSON exportado en: '{json_file}'.")

    # Exportar Excel
    excel_file = os.path.join(OUTPUT_DIR, "Reporte_Analisis_Tickets_Analistas.xlsx")
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        pd.DataFrame([analisis["resumen_general"]]).to_excel(writer, sheet_name="Resumen General", index=False)
        analisis["df_grupo"].to_excel(writer, sheet_name="Por Grupo", index=False)
        analisis["df_analista"].to_excel(writer, sheet_name="Por Analista", index=False)
        analisis["df_corte"].to_excel(writer, sheet_name="Historico Reportes", index=False)
        if df_data is not None:
            df_data.to_excel(writer, sheet_name="Data Cruda BDD", index=False)
        if df_archivos is not None:
            df_archivos.to_excel(writer, sheet_name="Archivos Procesados", index=False)

    print(f"[OK] Reporte Excel exportado en: '{excel_file}'.")

def main():
    print("--- 🚀 Iniciando Analizador de Tickets de Base de Datos TI_GPF ---")
    df_data, df_archivos = cargar_datos_bdd()
    
    if df_data is None or df_data.empty:
        print("[WARNING] No se encontraron registros en la BDD para analizar.")
        return

    analisis = realizar_analisis(df_data, df_archivos)
    if analisis:
        imprimir_dashboard_consola(analisis)
        exportar_reportes(analisis, df_data, df_archivos)

if __name__ == "__main__":
    main()
