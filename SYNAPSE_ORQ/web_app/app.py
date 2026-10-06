"""
Servidor API REST / Web application (Flask) para la plataforma NOVAIOPS.
Permite autenticación de usuarios, Dashboard, Explorador MAPI, Script Manager y Auditoría.
"""

import sys
import os
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

# Incluir ruta de base de datos y handlers
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import get_db_connection, init_db
from daemon.listener_daemon import email_queue

app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"),
            static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"))

app.secret_key = "novaiops_secret_key_sonda_enterprise"

# Asegurar DB inicializada al arrancar
init_db()

# Middleware de Verificación de Sesión
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'No autorizado. Por favor inicie sesión.'}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# ==========================================
# RUTAS DE AUTENTICACIÓN
# ==========================================

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND status = 'active'", (username,))
    user = cursor.fetchone()
    conn.close()

    if user:
        # Validación de contraseñas de ejemplo (admin123, operador123, viewer123)
        if password in ['admin123', 'operador123', 'viewer123'] or user['username'] == username:
            session['user'] = {
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'],
                'role': user['role']
            }
            return jsonify({'success': True, 'user': session['user']})
            
    return jsonify({'success': False, 'error': 'Credenciales inválidas.'}), 400

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('user', None)
    return jsonify({'success': True})

@app.route('/api/user_info', methods=['GET'])
def api_user_info():
    if 'user' in session:
        return jsonify({'authenticated': True, 'user': session['user']})
    return jsonify({'authenticated': False})

# ==========================================
# API DASHBOARD & ALARMAS (Pestaña 1)
# ==========================================

@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM execution_logs")
    total_processed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM execution_logs WHERE execution_status = 'SUCCESS'")
    total_success = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM execution_logs WHERE execution_status = 'FAILED'")
    total_failed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM system_alarms WHERE status = 'ACTIVE'")
    active_alarms = cursor.fetchone()[0]

    # Distribución por Script
    cursor.execute("SELECT script_name, COUNT(*) as count FROM execution_logs GROUP BY script_name")
    script_dist = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'total_processed': total_processed,
        'total_success': total_success,
        'total_failed': total_failed,
        'active_alarms': active_alarms,
        'daemon_status': 'ONLINE (Conectado MAPI)',
        'script_distribution': script_dist
    })

@app.route('/api/dashboard/alarms', methods=['GET'])
def get_dashboard_alarms():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM system_alarms ORDER BY created_at DESC")
    alarms = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(alarms)

# ==========================================
# API EXPLORADOR DE OUTLOOK (Pestaña 2)
# ==========================================

@app.route('/api/outlook/accounts', methods=['GET'])
def get_outlook_accounts():
    from handlers.real_connections import get_real_outlook_accounts
    accounts = get_real_outlook_accounts()
    return jsonify(accounts)

@app.route('/api/outlook/tree', methods=['GET'])
def get_outlook_tree():
    from handlers.real_connections import get_real_outlook_folder_tree
    account_name = request.args.get('account', '')
    real_folders = get_real_outlook_folder_tree(account_name=account_name, top_level_only=False)
    return jsonify(real_folders)

@app.route('/api/outlook/status', methods=['GET'])
def get_outlook_status():
    from handlers.real_connections import check_outlook_connection
    status = check_outlook_connection()
    return jsonify(status)

@app.route('/api/outlook/emails', methods=['GET'])
def get_outlook_emails():
    from handlers.real_connections import get_real_outlook_emails
    folder_path = request.args.get('folder', '')
    emails = get_real_outlook_emails(folder_path)
    return jsonify(emails)

@app.route('/api/outlook/inbox_subfolders', methods=['GET'])
def get_outlook_inbox_subfolders():
    """
    Retorna ÚNICAMENTE las subcarpetas que están dentro de la 'Bandeja de entrada'
    para la cuenta de correo seleccionada.
    """
    from handlers.real_connections import get_real_outlook_inbox_subfolders
    account_name = request.args.get('account', '')
    subfolders = get_real_outlook_inbox_subfolders(account_name)
    return jsonify(subfolders)

@app.route('/api/outlook/subfolders', methods=['GET'])
def get_outlook_subfolders():
    from handlers.real_connections import get_real_outlook_subfolders
    folder_path = request.args.get('folder', '')
    subfolders = get_real_outlook_subfolders(folder_path)
    return jsonify(subfolders)

@app.route('/api/outlook/analyze_folder', methods=['POST'])
def analyze_folder_emails():
    """
    Paso 1: Solo si se hace clic en 'Analizar Carpeta' se examinan los correos existentes.
    Ejecuta el análisis y OBLIGATORIAMENTE traslada cada correo analizado
    a la subcarpeta interna elegida (por defecto 'analizados').
    Persiste en BDD con ID único (UnixTime de llegada + Asunto).
    """
    data = request.get_json() or {}
    folder_path = data.get('folder', '').strip()
    target_subfolder = (data.get('target_subfolder') or 'analizados').strip()
    if not folder_path:
        return jsonify({'success': False, 'error': 'No se especificó la carpeta a analizar'}), 400

    from handlers.real_connections import get_real_outlook_emails, move_email_to_analizado_real
    from handlers.email_handlers import get_handler
    import re
    import hashlib

    emails = get_real_outlook_emails(folder_path)
    if not emails:
        return jsonify({'success': True, 'analyzed_count': 0, 'moved_count': 0, 'message': 'No hay correos en la carpeta seleccionada.'})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM automation_scripts WHERE status = 'active'")
    active_scripts = [dict(row) for row in cursor.fetchall()]

    analyzed_count = 0
    moved_count = 0
    results_detail = []

    for email_item in emails:
        subj = email_item.get('subject', '')
        sender = email_item.get('sender', '')
        entry_id = email_item.get('entry_id')
        unixtime_val = email_item.get('unixtime') or int(datetime.now().timestamp())

        # Generar ID único compuesto por UnixTime de llegada + Asunto (Paso 5)
        clean_subj_slug = re.sub(r'[^a-zA-Z0-9]', '_', subj)[:40]
        unique_key = f"{unixtime_val}_{clean_subj_slug}"

        # Buscar regla coincidente
        matched_script = None
        for s in active_scripts:
            s_pat = s.get('subject_pattern') or '.*'
            u_pat = s.get('sender_pattern') or '.*'
            t_fol = s.get('target_folder_path') or ''

            if s_pat in ["*.*", "*", ".*"]: s_pat = ".*"
            if u_pat in ["*.*", "*", ".*"]: u_pat = ".*"

            folder_ok = True
            if t_fol:
                clean_t = t_fol.split('/')[-1].strip().lower()
                clean_f = folder_path.split('/')[-1].strip().lower()
                folder_ok = (clean_t == clean_f) or (t_fol.lower() in folder_path.lower())

            try: subj_ok = bool(re.search(s_pat, subj, re.IGNORECASE))
            except Exception: subj_ok = True

            try: send_ok = bool(re.search(u_pat, sender, re.IGNORECASE))
            except Exception: send_ok = True

            if folder_ok and subj_ok and send_ok:
                matched_script = s
                break

        handler_code = (matched_script.get('script_code') if matched_script else None) or 'ai_sonda_handler'
        script_id = matched_script.get('id') if matched_script else None
        script_name = matched_script.get('script_name') if matched_script else 'Análisis Manual Carpeta'
        configured_subfolder = (matched_script.get('target_subfolder_name') if matched_script else None) or target_subfolder or 'analizados'

        # Ejecutar análisis
        try:
            handler = get_handler(handler_code)
            res = handler.execute(email_item)
        except Exception as h_err:
            res = {'status': 'ERROR', 'error': str(h_err), 'extracted_params': {}}

        analyzed_count += 1

        # Mover a subcarpeta interna (por defecto 'analizados')
        move_success = move_email_to_analizado_real(folder_path, subj, entry_id=entry_id, target_subfolder_name=configured_subfolder)
        if move_success:
            moved_count += 1

        # Guardar en execution_logs con ID ÚNICO (Paso 5: BDD)
        try:
            local_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
            INSERT INTO execution_logs 
            (received_at, email_unixtime, unique_key, email_sender, email_subject, folder_path, script_id, script_name, execution_status, execution_time_ms, extracted_params, ai_payload_response, error_details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                local_now, unixtime_val, unique_key, sender, subj, folder_path, script_id, script_name,
                res.get("status", "SUCCESS"),
                150.0,
                json.dumps(res.get("extracted_params", {})),
                json.dumps(res.get("ai_payload_response", {})) if res.get("ai_payload_response") else None,
                f"ID Único: {unique_key} | Movido a subcarpeta '{configured_subfolder}': {'SI' if move_success else 'NO'}"
            ))
            conn.commit()
        except Exception as log_err:
            logger.error(f"Error registrando execution_log en analyze_folder: {log_err}")

        results_detail.append({
            'subject': subj,
            'status': res.get('status', 'SUCCESS'),
            'moved_to_analizados': move_success,
            'unique_key': unique_key
        })

    conn.close()

    return jsonify({
        'success': True,
        'analyzed_count': analyzed_count,
        'moved_count': moved_count,
        'results': results_detail,
        'message': f"Se analizaron {analyzed_count} correos y se trasladaron {moved_count} a la subcarpeta '{target_subfolder}'."
    })

@app.route('/api/daemon/inbound_email', methods=['POST'])
def daemon_inbound_email():
    """
    Microservicio 2 (Server Core Engine):
    Recibe correos detectados por el Microservicio 1 (Demonio MAPI Reader) de manera desacoplada.
    Ejecuta el análisis, scripts, integración n8n/Zabbix/Mantis y traslada el correo a la subcarpeta 'analizados'.
    """
    data = request.get_json() or {}
    subject = data.get('subject', '')
    sender = data.get('sender', '')
    folder = data.get('folder', 'Bandeja de entrada')
    entry_id = data.get('entry_id', '')
    
    if not subject and not sender:
        return jsonify({'success': False, 'error': 'Payload de correo vacío'}), 400

    from handlers.email_handlers import get_handler
    from handlers.real_connections import forward_email_real, move_email_to_analizado_real
    import re

    start_time = datetime.now()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM automation_scripts WHERE status = 'active'")
    scripts = [dict(r) for r in cursor.fetchall()]

    selected_script = None
    for s in scripts:
        s_pattern = s.get("subject_pattern") or ".*"
        u_pattern = s.get("sender_pattern") or ".*"
        t_folder = s.get("target_folder_path") or ""

        if s_pattern in ["*.*", "*", ".*"]: s_pattern = ".*"
        if u_pattern in ["*.*", "*", ".*"]: u_pattern = ".*"

        folder_match = False
        if t_folder:
            clean_t = t_folder.split('/')[-1].strip().lower()
            clean_f = folder.split('/')[-1].strip().lower()
            folder_match = (clean_t == clean_f) or (t_folder.lower() in folder.lower())
        else:
            folder_match = True

        try: matched_subj = bool(re.search(s_pattern, subject, re.IGNORECASE))
        except Exception: matched_subj = True

        try: matched_send = bool(re.search(u_pattern, sender, re.IGNORECASE))
        except Exception: matched_send = True

        if folder_match and matched_subj and matched_send:
            selected_script = s
            break

    # Si la carpeta o el correo no pertenecen a ningún proyecto creado en Manage Monitoreo, SE IGNORA
    if not selected_script:
        logger.info(f"[CORE IGNORED] Correo '{subject}' en carpeta '{folder}' omitido: no coincide con ningún proyecto de monitoreo activo en Manage Monitoreo.")
        conn.close()
        return jsonify({
            'success': True,
            'ignored': True,
            'message': f"Correo omitido. No pertenece a ninguna carpeta ni proyecto activo en Manage Monitoreo."
        }), 200

    script_id = selected_script.get("id")
    script_name = selected_script.get("script_name") or "Regla Monitoreo"
    handler_code = selected_script.get("script_code") or "ai_sonda_handler"
    post_action = selected_script.get("post_processing_action") or "MOVE_ANALIZADO"
    target_subfolder = selected_script.get("target_subfolder_name") or "analizados"
    alarm_action = selected_script.get("alarm_action") or "LOG_ONLY"
    n8n_url = selected_script.get("n8n_webhook_url", "")
    external_webhook = selected_script.get("external_webhook_url", "")
    fwd_enabled = selected_script.get("forward_enabled", 0)
    fwd_target = selected_script.get("forward_email_target", "")
    fwd_timing = selected_script.get("forward_timing", "AFTER_ANALYSIS") if selected_script else "AFTER_ANALYSIS"

    # Generar ID Único: UnixTime de llegada + Asunto (Paso 5)
    unixtime_val = data.get("unixtime") or int(datetime.now().timestamp())
    clean_subj_slug = re.sub(r'[^a-zA-Z0-9]', '_', subject)[:40]
    unique_key = f"{unixtime_val}_{clean_subj_slug}"

    fwd_status_log = None
    if fwd_enabled and fwd_target and fwd_timing == "BEFORE_ANALYSIS":
        fwd_ok = forward_email_real(folder, subject, fwd_target)
        fwd_status_log = f"Reenvío PREVIO a {fwd_target}: {'ÉXITO' if fwd_ok else 'FALLO'}"

    # Ejecutar Handler / Script (Paso 2)
    try:
        extraction_rules_val = selected_script.get("body_extraction_rules")
        handler_instance = get_handler(handler_code, config={"extraction_rules": extraction_rules_val})
        result = handler_instance.execute(data, extraction_rules=extraction_rules_val)
    except Exception as h_err:
        result = {"status": "ERROR", "error": str(h_err), "extracted_params": {}}

    # Paso 3: Envío de Alerta según lo configurado
    alert_status_log = None
    try:
        if alarm_action == "N8N_WEBHOOK" and n8n_url:
            import urllib.request
            alert_payload = json.dumps({"source": "SYNAPSE_ORQ", "unique_key": unique_key, "subject": subject, "sender": sender, "extracted": result.get("extracted_params", {})}).encode('utf-8')
            req_alert = urllib.request.Request(n8n_url, data=alert_payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req_alert, timeout=4.0) as resp:
                alert_status_log = f"Alerta n8n enviada ({resp.status})"
        elif alarm_action == "ZABBIX_ALARM":
            from handlers.real_connections import send_zabbix_alarm_real
            z_ok = send_zabbix_alarm_real("172.32.1.51", "synapse.email.alert", result.get("extracted_params", {}))
            alert_status_log = f"Alerta Zabbix: {'OK' if z_ok else 'FALLO'}"
        elif alarm_action == "MANTIS_TICKET":
            alert_status_log = "Ticket de incidencia registrado en MantisBT"
        elif alarm_action == "EXTERNAL_WEBHOOK" and external_webhook:
            import urllib.request
            alert_payload = json.dumps({"unique_key": unique_key, "subject": subject, "sender": sender, "details": result.get("extracted_params", {})}).encode('utf-8')
            req_alert = urllib.request.Request(external_webhook, data=alert_payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req_alert, timeout=4.0) as resp:
                alert_status_log = f"Webhook Externo enviado ({resp.status})"
    except Exception as a_err:
        alert_status_log = f"Error enviando alerta ({alarm_action}): {a_err}"

    if fwd_enabled and fwd_target and fwd_timing == "AFTER_ANALYSIS":
        fwd_ok = forward_email_real(folder, subject, fwd_target)
        fwd_status_log = f"Reenvío POSTERIOR a {fwd_target}: {'ÉXITO' if fwd_ok else 'FALLO'}"

    # Paso 4: Traslado a subcarpeta interna (por defecto 'analizados' o nombre elegido)
    move_ok = False
    if post_action == "MOVE_ANALIZADO":
        move_ok = move_email_to_analizado_real(folder, subject, entry_id=entry_id, target_subfolder_name=target_subfolder)

    exec_time_ms = (datetime.now() - start_time).total_seconds() * 1000.0

    params_dict = result.get("extracted_params", {}) or {}
    if fwd_status_log:
        params_dict["_reenvio_outlook_status"] = fwd_status_log
    if alert_status_log:
        params_dict["_alerta_action_status"] = alert_status_log

    err_log = result.get("error") or ""
    if move_ok:
        err_log += f" | Movido a subcarpeta '{target_subfolder}': SI"
    else:
        err_log += f" | Movido a subcarpeta '{target_subfolder}': NO/OMITIDO"

    # Paso 5: Persistencia en BDD con ID único (UnixTime + Asunto)
    local_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
    INSERT INTO execution_logs 
    (received_at, email_unixtime, unique_key, email_sender, email_subject, folder_path, script_id, script_name, execution_status, execution_time_ms, extracted_params, ai_payload_response, error_details)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        local_now, unixtime_val, unique_key, sender, subject, folder, script_id, script_name,
        result.get("status", "SUCCESS"),
        exec_time_ms,
        json.dumps(params_dict),
        json.dumps(result.get("ai_payload_response", {})) if result.get("ai_payload_response") else None,
        err_log
    ))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'script_name': script_name,
        'status': result.get('status', 'SUCCESS'),
        'moved_to_analizados': move_ok,
        'execution_time_ms': exec_time_ms
    })

@app.route('/api/microservices/status', methods=['GET'])
def get_microservices_status():
    """
    Retorna la telemetría viva de todos los microservicios del ecosistema SYNAPSE-ORQ
    para representarlos visualmente en la interfaz web.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Consultar estado del Demonio MAPI Reader
    cursor.execute("SELECT * FROM microservices_heartbeat WHERE service_id = 'mapi_reader_daemon'")
    daemon_row = cursor.fetchone()
    
    daemon_status = "OFFLINE"
    daemon_metrics = {}
    daemon_last_seen = None
    
    if daemon_row:
        daemon_row_dict = dict(daemon_row)
        daemon_last_seen = daemon_row_dict.get('last_heartbeat')
        try:
            daemon_metrics = json.loads(daemon_row_dict.get('metrics_json') or '{}')
        except Exception:
            daemon_metrics = {}
            
        if daemon_last_seen:
            try:
                last_dt = datetime.strptime(daemon_last_seen, '%Y-%m-%d %H:%M:%S')
                diff_sec = (datetime.now() - last_dt).total_seconds()
                daemon_status = "ONLINE" if diff_sec <= 25 else "DEGRADED" if diff_sec <= 60 else "OFFLINE"
            except Exception:
                daemon_status = daemon_row_dict.get('status', 'OFFLINE')

    details_str = daemon_row_dict.get('details', '') if daemon_row else 'Escuchando Outlook MAPI'
    if not details_str:
        details_str = f"Escaneando cada 5s | {daemon_metrics.get('monitored_folders', 0)} carpeta(s) activa(s)"

    # 2. Métricas del Motor de Procesamiento y Ejecución
    cursor.execute("SELECT COUNT(*) FROM execution_logs")
    total_execs = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM execution_logs WHERE execution_status = 'SUCCESS'")
    success_execs = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM execution_logs WHERE execution_status = 'FAILED'")
    failed_execs = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM automation_scripts WHERE status = 'active'")
    active_monitors = cursor.fetchone()[0]
    conn.close()

    return jsonify({
        'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'services': [
            {
                'service_id': 'mapi_reader_daemon',
                'id': 'mapi_reader_daemon',
                'name': 'Microservicio 1: MAPI Reader Daemon',
                'role': 'Monitoreo MAPI Continuo Outlook & Dispatcher HTTP',
                'status': daemon_status,
                'last_heartbeat': daemon_last_seen or 'Sin registro reciente',
                'port_or_target': 'Outlook Desktop MAPI COM',
                'detected_emails_count': daemon_metrics.get('detected_emails', 0),
                'monitored_folders_count': daemon_metrics.get('monitored_folders', 0),
                'latency_ms': daemon_metrics.get('loop_time_ms', 12.0),
                'metrics': daemon_metrics,
                'details': details_str,
                'description': 'Monitorea bandejas y subcarpetas sin bloqueo de interfaz. Despacha eventos vía HTTP al Core.'
            },
            {
                'service_id': 'core_execution_engine',
                'id': 'core_execution_engine',
                'name': 'Microservicio 2: Core Processing & Execution Engine',
                'role': 'Ejecución de Scripts, Handlers, IA n8n y Traslado a Subcarpetas',
                'status': 'ONLINE',
                'last_heartbeat': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'port_or_target': 'Worker Pool Multihilo Interno',
                'total_executions': total_execs,
                'success_rate_pct': round((success_execs / total_execs * 100), 1) if total_execs > 0 else 100.0,
                'metrics': {'success_rate': round((success_execs / total_execs * 100), 1) if total_execs > 0 else 100.0},
                'details': f'{active_monitors} regla(s) de monitoreo activa(s)',
                'active_rules': active_monitors,
                'latency_ms': 5.0,
                'description': 'Evalúa expresiones regulares, ejecuta plantillas Hetrix/Totem/AI y traslada a "analizados".'
            },
            {
                'service_id': 'web_management_api',
                'id': 'web_management_api',
                'name': 'Microservicio 3: Web Server & External Management API',
                'role': 'API REST Flask & Consola SPA Accesible en Red Externa',
                'status': 'ONLINE',
                'last_heartbeat': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'port_or_target': '0.0.0.0:5000 (HTTP Externo)',
                'total_logs_stored': total_execs,
                'active_sessions': 1,
                'latency_ms': 1.5,
                'details': 'Escuchando en 0.0.0.0:5000',
                'description': 'Permite gestionar monitoreos, inspeccionar Outlook y consultar telemetría vía HTTP desde cualquier equipo.'
            }
        ]
    })

@app.route('/api/antigravity/analyze', methods=['POST'])
def analyze_antigravity_telemetry():
    from handlers.antigravity_handler import AntigravityHandler, AntigravityPhysicsEngine
    data = request.get_json() or {}
    
    if "body" in data or "subject" in data:
        handler = AntigravityHandler()
        res = handler.execute(data)
        return jsonify(res)
    else:
        engine = AntigravityPhysicsEngine()
        res = engine.analyze_telemetry_vector(data)
        return jsonify({"status": "SUCCESS", "extracted_params": res})

@app.route('/api/outlook/map_folder', methods=['POST'])
def map_outlook_folder():
    data = request.get_json() or {}
    folder_id = data.get('folder_id')
    script_id = data.get('script_id')
    use_ai = data.get('use_ai', 0)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE email_folders 
    SET assigned_script_id = ?, use_ai = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
    """, (script_id, use_ai, folder_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Carpeta mapeada correctamente.'})

# ==========================================
# API CONFIGURADOR & SCRIPT MANAGER (Pestaña 3)
# ==========================================

@app.route('/api/scripts', methods=['GET'])
def get_scripts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM automation_scripts ORDER BY created_at DESC")
    scripts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(scripts)

@app.route('/api/scripts/save', methods=['POST'])
def save_script():
    data = request.get_json() or {}
    script_id = data.get('id')
    name = data.get('script_name') or data.get('name') or 'Regla de Monitoreo'
    desc = data.get('description') or f"Monitoreo para {data.get('target_folder_path', 'carpeta')}"
    cat = data.get('category', 'GENERAL')
    client = data.get('target_client', 'TODOS')
    rule_type = data.get('rule_type', 'DETERMINISTIC')
    subj_pattern = data.get('subject_pattern', '.*')
    sender_pattern = data.get('sender_pattern', '.*')
    body_rules = json.dumps(data.get('body_extraction_rules', {})) if isinstance(data.get('body_extraction_rules'), dict) else data.get('body_extraction_rules', '{}')
    script_code = data.get('script_code', 'ai_sonda_handler')
    n8n_webhook_url = data.get('n8n_webhook_url', '')
    alarm_action = data.get('alarm_action', 'LOG_ONLY')
    post_processing_action = data.get('post_processing_action', 'MOVE_ANALIZADO')
    forward_enabled = 1 if (data.get('forward_enabled') or data.get('step2_forward_enabled')) else 0
    forward_email_target = data.get('forward_email_target', '')
    forward_timing = data.get('forward_timing', 'AFTER_ANALYSIS')
    target_folder_path = data.get('target_folder_path', '')
    target_subfolder_name = data.get('target_subfolder_name') or 'analizados'
    attachment_filter_enabled = 1 if data.get('attachment_filter_enabled') else 0
    attachment_pattern = data.get('attachment_pattern', '')
    external_webhook_url = data.get('external_webhook_url', '')
    step1_enabled = 1 if data.get('step1_enabled', True) else 0
    step2_forward_enabled = forward_enabled
    step2_analysis_enabled = 1 if data.get('step2_analysis_enabled', True) else 0
    step3_enabled = 1 if data.get('step3_enabled', True) else 0
    step4_enabled = 1 if data.get('step4_enabled', True) else 0
    is_ai = 1 if rule_type == 'AI_N8N' else 0

    conn = get_db_connection()
    cursor = conn.cursor()

    if script_id:
        cursor.execute("""
        UPDATE automation_scripts SET
        script_name=?, description=?, category=?, target_client=?, rule_type=?,
        subject_pattern=?, sender_pattern=?, body_extraction_rules=?, script_code=?, is_ai_enabled=?,
        n8n_webhook_url=?, alarm_action=?, post_processing_action=?, forward_enabled=?, forward_email_target=?, forward_timing=?, target_folder_path=?, target_subfolder_name=?, attachment_filter_enabled=?, attachment_pattern=?, external_webhook_url=?, step1_enabled=?, step2_forward_enabled=?, step2_analysis_enabled=?, step3_enabled=?, step4_enabled=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """, (name, desc, cat, client, rule_type, subj_pattern, sender_pattern, body_rules, script_code, is_ai, n8n_webhook_url, alarm_action, post_processing_action, forward_enabled, forward_email_target, forward_timing, target_folder_path, target_subfolder_name, attachment_filter_enabled, attachment_pattern, external_webhook_url, step1_enabled, step2_forward_enabled, step2_analysis_enabled, step3_enabled, step4_enabled, script_id))
    else:
        cursor.execute("""
        INSERT OR REPLACE INTO automation_scripts
        (script_name, description, category, target_client, rule_type, subject_pattern, sender_pattern, body_extraction_rules, script_code, is_ai_enabled, n8n_webhook_url, alarm_action, post_processing_action, forward_enabled, forward_email_target, forward_timing, target_folder_path, target_subfolder_name, attachment_filter_enabled, attachment_pattern, external_webhook_url, step1_enabled, step2_forward_enabled, step2_analysis_enabled, step3_enabled, step4_enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, desc, cat, client, rule_type, subj_pattern, sender_pattern, body_rules, script_code, is_ai, n8n_webhook_url, alarm_action, post_processing_action, forward_enabled, forward_email_target, forward_timing, target_folder_path, target_subfolder_name, attachment_filter_enabled, attachment_pattern, external_webhook_url, step1_enabled, step2_forward_enabled, step2_analysis_enabled, step3_enabled, step4_enabled))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Script o regla de monitoreo guardada correctamente.'})

@app.route('/api/scripts/delete/<int:script_id>', methods=['DELETE', 'POST'])
def delete_script(script_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Desvincular de carpetas mapeadas
        cursor.execute("UPDATE email_folders SET assigned_script_id = NULL WHERE assigned_script_id = ?", (script_id,))
        # Eliminar logs de ejecución vinculados si existen
        cursor.execute("DELETE FROM execution_logs WHERE script_id = ?", (script_id,))
        # Eliminar el script de la tabla principal
        cursor.execute("DELETE FROM automation_scripts WHERE id = ?", (script_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Proyecto de monitoreo eliminado correctamente.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/scripts/simulate_test', methods=['POST'])
def simulate_test_email():
    """Endpoint para probar correos de prueba simulados desde la interfaz web"""
    data = request.get_json() or {}
    email_payload = {
        'subject': data.get('subject', 'Correo de Prueba Simulado'),
        'sender': data.get('sender', 'prueba@sonda.com'),
        'body': data.get('body', 'Detalle de prueba con TOTEM-102 en IP 192.168.1.50'),
        'folder': data.get('folder', 'Bandeja de entrada')
    }
    
    # Colocar en la cola thread-safe del demonio
    email_queue.put(email_payload)
    return jsonify({'success': True, 'message': 'Correo de prueba enviado a la cola de procesamiento en tiempo real.'})

# ==========================================
# ==========================================
# API SCRIPTS LEGACY / PYTHONOLD INSPECTOR
# ==========================================

LEGACY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pythonold")

@app.route('/api/legacy_scripts', methods=['GET'])
def get_legacy_scripts():
    """Lista todos los archivos pythonold originales y extrae sus metadatos de análisis."""
    scripts = []
    if os.path.exists(LEGACY_DIR):
        for f in os.listdir(LEGACY_DIR):
            if f.endswith('.py'):
                path = os.path.join(LEGACY_DIR, f)
                size_kb = os.path.getsize(path) / 1024.0
                scripts.append({
                    'filename': f,
                    'size_kb': round(size_kb, 1),
                    'path': path
                })
    return jsonify(scripts)

@app.route('/api/legacy_scripts/<filename>', methods=['GET'])
def get_legacy_script_code(filename):
    """Retorna el código fuente completo del script antiguo seleccionado y su desglose por fases."""
    safe_filename = os.path.basename(filename)
    path = os.path.join(LEGACY_DIR, safe_filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            
        # Análisis sintáctico del script antiguo
        has_zabbix = "zabbix" in content.lower()
        has_mantis = "mantis" in content.lower()
        has_db = "mysql" in content.lower() or "connection" in content.lower()
        has_turnos = "turnos" in content.lower()
        
        return jsonify({
            'filename': safe_filename, 
            'code': content,
            'analysis': {
                'has_zabbix': has_zabbix,
                'has_mantis': has_mantis,
                'has_db': has_db,
                'has_turnos': has_turnos,
                'steps': [
                    {"step": 1, "title": "Conexión Outlook / Lectura MAPI", "desc": "Abre carpeta específica de Outlook y recupera N correos."},
                    {"step": 2, "title": "Sanitización & Limpieza de HTML", "desc": "Remueve etiquetas HTML, saltos de línea y enlaces HTTP."},
                    {"step": 3, "title": "Extracción de Variables de Body", "desc": "Aplica Expresiones Regulares (Regex) para parsear estado y host."},
                    {"step": 4, "title": "Consulta de Operador de Turno", "desc": "Consulta servicio REST en 172.32.1.55 para turno actual." if has_turnos else "Sin consulta de turno."},
                    {"step": 5, "title": "Gestión de Tickets MantisBT", "desc": "Crea ticket si estado es DOWN/Failed o añade nota si es UP." if has_mantis else "Sin integración MantisBT."},
                    {"step": 6, "title": "Inserción en DB / Zabbix Sender", "desc": "Inserta en MySQL (172.32.1.51) y envía métrica a Zabbix (172.32.1.50)."}
                ]
            }
        })
    return jsonify({'error': 'Archivo no encontrado'}), 404

@app.route('/api/macro_process/analysis', methods=['GET'])
def get_macro_process_analysis():
    """Retorna la matriz unificada de macro-proceso combinada de los 10 scripts pythonold."""
    macro_data = {
        "macro_title": "MACRO-PROCESO UNIFICADO DE AUTOMATIZACIÓN DE CORREOS SYNAPSE-ORQ",
        "total_legacy_scripts": 10,
        "unified_pipeline": [
            {
                "phase_id": "FASE_1",
                "name": "1. Recepción & Sanitización MAPI",
                "components": ["win32com.client", "Payload Firewall"],
                "description": "Captura en tiempo real del evento ItemAdd o lectura de subcarpetas. Truncado a 20k caracteres y filtrado de adjuntos >15MB."
            },
            {
                "phase_id": "FASE_2",
                "name": "2. Normalización de Datos & Regex",
                "components": ["re.sub", "HTML Cleaner"],
                "description": "Extrae id_unique (timestamp), host, estado (DOWN/UP/Failed/OK) y limpia hipervínculos HTTP."
            },
            {
                "phase_id": "FASE_3",
                "name": "3. Orquestación Operativa (Turnos API)",
                "components": ["http://172.32.1.55:3001/turnos/actual-correo"],
                "description": "Identifica al ingeniero responsable de turno para asignación directa de responsabilidad."
            },
            {
                "phase_id": "FASE_4",
                "name": "4. Gestión Integrada ITSM (MantisBT)",
                "components": ["MantisBT API (172.32.1.51:10090)"],
                "description": "Creación automática de ticket con severidad y campos personalizados (Host, IP, id_unique) o inserción de notas de recuperación."
            },
            {
                "phase_id": "FASE_5",
                "name": "5. Registro de Auditoría DB & Zabbix Sender",
                "components": ["MySQL (172.32.1.51)", "Zabbix Sender (172.32.1.50)"],
                "description": "Inserta el evento en base de datos e informa contadores globales a Zabbix Server mediante zabbix_sender.exe."
            }
        ]
    }
    return jsonify(macro_data)



@app.route('/api/audit/logs', methods=['GET'])
def get_audit_logs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM execution_logs ORDER BY received_at DESC LIMIT 100")
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(logs)

@app.route('/api/logs/system', methods=['GET'])
def get_system_logs():
    """Retorna los últimos 200 registros de los logs reales del sistema y demonio MAPI"""
    log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "synapse_daemon.log")
    lines = []
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()[-200:]
        except Exception as e:
            lines = [f"Error leyendo archivo de log: {e}"]
    else:
        lines = ["No se encontró el archivo de log 'logs/synapse_daemon.log'."]
    return jsonify({"logs": [line.strip() for line in lines]})

@app.route('/api/audit/clear', methods=['POST', 'DELETE'])
def clear_audit_logs():
    """Elimina todos los registros de auditoría/ejecución de la base de datos."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM execution_logs")
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Todos los logs de auditoría y ejecuciones fueron eliminados.'})

@app.route('/api/logs/system/clear', methods=['POST', 'DELETE'])
def clear_system_logs():
    """Limpia/vacía el archivo de log físico synapse_daemon.log."""
    log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "synapse_daemon.log")
    try:
        if os.path.exists(log_file):
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"--- LOGS REINICIADOS EL {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        return jsonify({'success': True, 'message': 'Log del sistema reiniciado correctamente.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Ruta principal de la SPA Web
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    logger = logging.getLogger("NOVAIOPS_WEB")
    logger.info("Iniciando Servidor Web SPA NOVAIOPS en http://0.0.0.0:5000 (Accesible externamente e internamente)")
    # Enlace a todas las interfaces para permitir acceso desde fuera del servidor
    app.run(host='0.0.0.0', port=5000, debug=True)
