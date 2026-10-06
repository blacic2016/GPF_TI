import subprocess
import time
import sys
import os

# Asegurar codificación utf-8 en consola de Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SERVICES = [
    {
        "name": "Microservicio Interno de Ejecucion (Port 5001)",
        "cmd": [sys.executable, os.path.join(os.path.dirname(__file__), "microservices", "engine_service.py")],
        "process": None
    },
    {
        "name": "Plataforma Web y Gateway API (Port 5000)",
        "cmd": [sys.executable, os.path.join(os.path.dirname(__file__), "app.py")],
        "process": None
    }
]

def start_service(svc):
    print(f"[SUPERVISOR] Iniciando {svc['name']}...")
    proc = subprocess.Popen(svc["cmd"], stdout=sys.stdout, stderr=sys.stderr)
    svc["process"] = proc
    return proc

def monitor_services():
    print("=" * 70)
    print("[SUPERVISOR] SUPERVISOR DE ALTA DISPONIBILIDAD - GEOPOS PROVISIONING")
    print("[SUPERVISOR] Supervisando microservicios y aislando cargas criticas.")
    print("=" * 70)

    # Iniciar primero el microservicio y luego la web
    for svc in SERVICES:
        start_service(svc)
        time.sleep(1.5)

    try:
        while True:
            time.sleep(3)
            for svc in SERVICES:
                proc = svc["process"]
                if proc.poll() is not None:
                    # El proceso cayó
                    print(f"[ALERTA] {svc['name']} finalizo inesperadamente con codigo {proc.returncode}. Reiniciando...")
                    start_service(svc)
    except KeyboardInterrupt:
        print("\n[SUPERVISOR] Deteniendo todos los servicios ordenadamente...")
        for svc in SERVICES:
            if svc["process"] and svc["process"].poll() is None:
                svc["process"].terminate()
        sys.exit(0)

if __name__ == "__main__":
    monitor_services()
