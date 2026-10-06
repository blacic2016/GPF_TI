import os
import requests

MICROSERVICE_URL = os.getenv("MICROSERVICE_URL", "http://127.0.0.1:5001")

class WorkerClient:
    def __init__(self, base_url=MICROSERVICE_URL):
        self.base_url = base_url

    def get_health(self) -> dict:
        try:
            r = requests.get(f"{self.base_url}/internal/health", timeout=1.5)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            return {"status": "UNREACHABLE", "error": str(e), "service": "POS-Engine-Microservice"}
        return {"status": "ERROR"}

    def set_simulation_mode(self, mode: bool) -> dict:
        try:
            r = requests.post(f"{self.base_url}/internal/config/simulation", json={"simulation_mode": mode}, timeout=2.0)
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def enqueue_job(self, pos_config: dict) -> dict:
        try:
            r = requests.post(f"{self.base_url}/internal/jobs/enqueue", json=pos_config, timeout=3.0)
            return r.json()
        except Exception as e:
            return {"success": False, "error": f"Fallo al comunicar con microservicio interno: {str(e)}"}

    def enqueue_bulk(self, pos_list: list) -> dict:
        try:
            r = requests.post(f"{self.base_url}/internal/jobs/enqueue", json={"pos_list": pos_list}, timeout=3.0)
            return r.json()
        except Exception as e:
            return {"success": False, "error": f"Fallo al comunicar con microservicio interno: {str(e)}"}

    def list_jobs(self) -> list:
        try:
            r = requests.get(f"{self.base_url}/internal/jobs", timeout=1.5)
            if r.status_code == 200:
                return r.json().get("jobs", [])
        except Exception:
            return []
        return []

    def get_logs(self) -> list:
        try:
            r = requests.get(f"{self.base_url}/internal/logs", timeout=1.5)
            if r.status_code == 200:
                return r.json().get("logs", [])
        except Exception:
            return []
        return []

worker_client_instance = WorkerClient()
