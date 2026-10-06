import time
import socket
import paramiko
from config import config_instance

class SSHService:
    def __init__(self):
        pass

    def check_reachability(self, host: str, port: int = 22, timeout: float = 2.0) -> bool:
        if config_instance.SIMULATION_MODE:
            return True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, int(port)))
            sock.close()
            return result == 0
        except Exception:
            return False

    def execute_command(self, host: str, user: str, password: str, command: str, port: int = 22, timeout: int = 30) -> dict:
        """
        Ejecuta un comando SSH remoto en el equipo de destino.
        Soporta modo SIMULATION_MODE para pruebas sin infraestructura física.
        """
        if config_instance.SIMULATION_MODE:
            time.sleep(0.4) # Simula latencia de red
            return self._simulate_command_execution(host, command)

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(hostname=host, port=int(port), username=user, password=password, timeout=timeout)
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode('utf-8', errors='ignore')
            err = stderr.read().decode('utf-8', errors='ignore')
            exit_code = stdout.channel.recv_exit_status()
            client.close()
            return {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "stdout": out,
                "stderr": err,
                "host": host,
                "command": command
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "host": host,
                "command": command
            }

    def _simulate_command_execution(self, host: str, command: str) -> dict:
        """Genera respuestas simuladas realistas basadas en el documento de preparación de POS"""
        cmd_lower = command.lower()
        stdout = ""
        
        if "mkdir" in cmd_lower:
            stdout = "Directorios creados exitosamente."
        elif "scp" in cmd_lower:
            stdout = "DumpBaseCaja.sql 100% 45MB 12.5MB/s\nPaqueteBaseCaja.tgz 100% 120MB 15.2MB/s\ngeopos2gpf-fybeca 100% 85MB 14.1MB/s"
        elif "tar -xvzf" in cmd_lower:
            stdout = "Extrayendo paquetes...\nx ./geopos/\nx ./geoconfigurator/\nx ./current/\nDescompresión completa."
        elif "dconf" in cmd_lower:
            stdout = "Configuración de favoritos Gnome aplicada: firefox, GEOPOS, nautilus, terminal."
        elif "kill -9" in cmd_lower:
            stdout = "Proceso geopos (PID 4912) terminado."
        elif "reboot" in cmd_lower:
            stdout = "Broadcast message from soportegeo@pos: The system will reboot now!"
        elif "crontab" in cmd_lower:
            stdout = "crontab: installing new crontab"
        elif "run-commandlineclient.sh" in cmd_lower:
            stdout = "[GeoConfigurator CLI] Analizando VersionGEOPosCaja.xml...\nActualizando propiedades... OK.\nResultado: alwaysupdate completado sin errores."
        else:
            stdout = f"Ejecutado con éxito en {host}: {command[:60]}"

        return {
            "success": True,
            "exit_code": 0,
            "stdout": stdout,
            "stderr": "",
            "host": host,
            "command": command
        }

ssh_service_instance = SSHService()
