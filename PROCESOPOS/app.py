import os
from flask import Flask, render_template, request, jsonify, session
from config import config_instance
from services.auth_service import auth_service_instance, ROLES
from services.orchestrator import orchestrator_instance
from services.db_service import db_service_instance
from services.worker_client import worker_client_instance

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = config_instance.SECRET_KEY

def get_current_user():
    return session.get("user")

@app.route("/")
def index():
    return render_template("index.html")

# ================= AUTHENTICATION & USERS =================
@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    user = auth_service_instance.authenticate(username, password)
    if not user:
        return jsonify({"error": "Credenciales inválidas o usuario inactivo"}), 401
    
    session["user"] = user
    return jsonify({"success": True, "user": user})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return jsonify({"success": True})

@app.route("/api/session", methods=["GET"])
def check_session():
    user = get_current_user()
    return jsonify({"authenticated": user is not None, "user": user})

@app.route("/api/users", methods=["GET"])
def list_users():
    user = get_current_user()
    if not user:
        return jsonify({"error": "No autorizado"}), 401
    return jsonify({"users": auth_service_instance.list_users(), "roles": ROLES})

@app.route("/api/users", methods=["POST"])
def create_user():
    user = get_current_user()
    if not user or user.get("role") != "ADMIN":
        return jsonify({"error": "Solo administradores pueden crear usuarios"}), 403
    
    data = request.json or {}
    try:
        new_user = auth_service_instance.create_user(
            username=data.get("username"),
            fullname=data.get("fullname"),
            password=data.get("password"),
            role=data.get("role", "OPERATOR")
        )
        return jsonify({"success": True, "user": {"username": new_user["username"], "fullname": new_user["fullname"], "role": new_user["role"]}})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/users/<username>", methods=["PUT"])
def update_user(username):
    user = get_current_user()
    if not user or user.get("role") != "ADMIN":
        return jsonify({"error": "Solo administradores pueden modificar usuarios"}), 403
    
    data = request.json or {}
    try:
        updated = auth_service_instance.update_user(
            username=username,
            fullname=data.get("fullname"),
            password=data.get("password"),
            role=data.get("role"),
            active=data.get("active")
        )
        return jsonify({"success": True, "user": {"username": updated["username"], "fullname": updated["fullname"], "role": updated["role"]}})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/users/<username>", methods=["DELETE"])
def delete_user(username):
    user = get_current_user()
    if not user or user.get("role") != "ADMIN":
        return jsonify({"error": "Solo administradores pueden eliminar usuarios"}), 403
    
    try:
        auth_service_instance.delete_user(username)
        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

# ================= CONFIGURATION & RUNTIME OVERRIDES =================
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(config_instance.to_dict())

@app.route("/api/config", methods=["POST"])
def update_config():
    user = get_current_user()
    if not user or user.get("role") not in ("ADMIN", "OPERATOR"):
        return jsonify({"error": "No autorizado para modificar parámetros"}), 403
    
    data = request.json or {}
    config_instance.update_runtime(data)
    orchestrator_instance.log("SISTEMA", f"Parámetros de entorno modificados en vivo por {user['username']}", "INFO")
    return jsonify({"success": True, "config": config_instance.to_dict()})

@app.route("/api/config/toggle-simulation", methods=["POST"])
def toggle_simulation_mode():
    data = request.json or {}
    new_mode = bool(data.get("simulation_mode", not config_instance.SIMULATION_MODE))
    config_instance.SIMULATION_MODE = new_mode
    worker_client_instance.set_simulation_mode(new_mode)
    mode_str = "SIMULACIÓN" if new_mode else "PRODUCCIÓN REAL"
    orchestrator_instance.log("SISTEMA", f"Modo de operación cambiado a: {mode_str}", "INFO")
    return jsonify({"success": True, "simulation_mode": new_mode, "mode_label": mode_str})

@app.route("/api/deploy/execute-phase-step", methods=["POST"])
def execute_phase_step():
    user = get_current_user()
    if not user or user.get("role") not in ("ADMIN", "OPERATOR"):
        return jsonify({"error": "Permisos insuficientes"}), 403
    
    data = request.json or {}
    phase_id = int(data.get("phase_id", 0))
    params = data.get("params", {})
    
    # Actualizar config en caliente con los datos ingresados en el popup
    config_instance.update_runtime(params)
    
    # Ejecutar la lógica de la fase
    success, msg = orchestrator_instance._execute_phase_logic(phase_id, params)
    if not success:
        return jsonify({"success": False, "error": msg, "phase_id": phase_id})
    
    # Validar compuerta de seguridad
    mock_job = {"config": params}
    gate_ok, gate_msg = orchestrator_instance._check_security_gate(phase_id, params, mock_job)
    
    next_phase = phase_id + 1 if phase_id < 8 else None
    
    pos_num = params.get("pos_num", 1)
    target_ip = params.get("target_ip", "10.108.0.15")
    orchestrator_instance.log(f"POS-{pos_num} ({target_ip})", f"Paso {phase_id} completado vía Asistente Interactivo: {gate_msg}", "SUCCESS")
    
    return jsonify({
        "success": True,
        "phase_id": phase_id,
        "gate_passed": gate_ok,
        "gate_detail": gate_msg,
        "next_phase_id": next_phase,
        "simulation_mode": config_instance.SIMULATION_MODE
    })

# ================= PROCESS PHASES & ORCHESTRATION VIA MICROSERVICE =================
@app.route("/api/phases", methods=["GET"])
def get_phases():
    return jsonify({"phases": orchestrator_instance.get_phases_metadata()})

@app.route("/api/microservice/health", methods=["GET"])
def microservice_health():
    health = worker_client_instance.get_health()
    return jsonify(health)

@app.route("/api/status", methods=["GET"])
def get_status():
    # Obtener estado de la base de datos SQLite / microservicio
    ms_jobs = worker_client_instance.list_jobs()
    ms_logs = worker_client_instance.get_logs()
    
    # Si el microservicio está respondiendo con jobs de SQLite, los usamos prioritariamente
    if ms_jobs or ms_logs:
        active_jobs_map = {j["pos_key"]: j for j in ms_jobs}
        return jsonify({
            "active_jobs": active_jobs_map,
            "bulk_queue": ms_jobs,
            "current_bulk_index": 0,
            "is_bulk_running": any(j["status"] == "IN_PROGRESS" for j in ms_jobs),
            "recent_logs": ms_logs[-35:],
            "microservice_connected": True
        })

    # Fallback al orquestador en memoria si el microservicio está iniciando
    local_status = orchestrator_instance.get_status()
    local_status["microservice_connected"] = False
    return jsonify(local_status)

@app.route("/api/deploy/single", methods=["POST"])
def deploy_single():
    user = get_current_user()
    if not user or user.get("role") not in ("ADMIN", "OPERATOR"):
        return jsonify({"error": "Permisos insuficientes para iniciar despliegue"}), 403
    
    data = request.json or {}
    # Despachar al microservicio interno aislado
    res = worker_client_instance.enqueue_job(data)
    if res.get("success"):
        return jsonify({"success": True, "pos_key": f"POS-{data.get('pos_num', 1)} ({data.get('target_ip', '10.108.0.15')})"})
    
    # Fallback local
    pos_key = orchestrator_instance.start_single_pos(data, user["username"])
    return jsonify({"success": True, "pos_key": pos_key})

@app.route("/api/deploy/bulk", methods=["POST"])
def deploy_bulk():
    user = get_current_user()
    if not user or user.get("role") not in ("ADMIN", "OPERATOR"):
        return jsonify({"error": "Permisos insuficientes para iniciar despliegue por lotes"}), 403
    
    data = request.json or {}
    pos_list = data.get("pos_list", [])
    if not pos_list:
        return jsonify({"error": "Debe proporcionar al menos 1 POS para el lote"}), 400
    
    # Despachar al microservicio interno aislado
    res = worker_client_instance.enqueue_bulk(pos_list)
    if res.get("success"):
        return jsonify({"success": True, "count": len(pos_list), "delegated_to_microservice": True})
    
    # Fallback local
    orchestrator_instance.start_bulk_deployment(pos_list, user["username"])
    return jsonify({"success": True, "count": len(pos_list), "delegated_to_microservice": False})

@app.route("/api/deploy/approve-gate", methods=["POST"])
def approve_gate():
    user = get_current_user()
    if not user or user.get("role") not in ("ADMIN", "OPERATOR"):
        return jsonify({"error": "No autorizado"}), 403
    
    data = request.json or {}
    pos_key = data.get("pos_key")
    approved = data.get("approved", True)
    ok = orchestrator_instance.approve_gate(pos_key, approved, user["username"])
    return jsonify({"success": ok})

@app.route("/api/reconciliation", methods=["POST"])
def test_reconciliation():
    data = request.json or {}
    local_ip = data.get("local_server_ip", config_instance.LOCAL_SERVER_IP)
    pos_ip = data.get("target_ip", "10.108.0.15")
    result = db_service_instance.run_reconciliation_matrix(local_ip, pos_ip, "root", "geocom")
    return jsonify({"success": True, "result": result})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config_instance.PORT, debug=config_instance.DEBUG)
