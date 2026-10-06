import os
from dotenv import load_dotenv

# Cargar variables del archivo .env al inicio
load_dotenv(override=True)

class Config:
    def __init__(self):
        self.reload_from_env()

    def reload_from_env(self):
        self.PORT = int(os.getenv("PORT", 5000))
        self.DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1")
        self.SECRET_KEY = os.getenv("SECRET_KEY", "geopos_super_secret_key_prod_2026_x89a1!")
        
        # Repositorio central
        self.REPO_CENTRAL_IP = os.getenv("REPO_CENTRAL_IP", "172.21.9.12")
        self.REPO_CENTRAL_PORT = int(os.getenv("REPO_CENTRAL_PORT", 22))
        self.REPO_CENTRAL_USER = os.getenv("REPO_CENTRAL_USER", "geocom")
        self.REPO_CENTRAL_PASS = os.getenv("REPO_CENTRAL_PASS", "geocom")
        self.REPO_CENTRAL_BASE_PATH = os.getenv("REPO_CENTRAL_BASE_PATH", "/home/geocom/repo_geo")
        
        # Local y Unidad de negocio
        self.DEFAULT_BUSINESS_UNIT = os.getenv("DEFAULT_BUSINESS_UNIT", "FYBECA")
        self.LOCAL_SERVER_IP = os.getenv("LOCAL_SERVER_IP", "10.108.0.101")
        self.LOCAL_SERVER_MYSQL_PORT = int(os.getenv("LOCAL_SERVER_MYSQL_PORT", 3306))
        self.LOCAL_SERVER_MYSQL_USER = os.getenv("LOCAL_SERVER_MYSQL_USER", "root")
        self.LOCAL_SERVER_MYSQL_PASS = os.getenv("LOCAL_SERVER_MYSQL_PASS", "geocom")
        self.LOCAL_ID = os.getenv("LOCAL_ID", "901")
        
        # POS Target defaults
        self.POS_SSH_USER = os.getenv("POS_SSH_USER", "geocom")
        self.POS_SSH_PASS = os.getenv("POS_SSH_PASS", "geocom")
        self.POS_SOPORTE_USER = os.getenv("POS_SOPORTE_USER", "soportegeo")
        self.POS_SOPORTE_PASS = os.getenv("POS_SOPORTE_PASS", "F1b3caSopg.2022#")
        self.POS_MYSQL_USER = os.getenv("POS_MYSQL_USER", "root")
        self.POS_MYSQL_PASS = os.getenv("POS_MYSQL_PASS", "geocom")
        
        # Pinpad defaults
        self.PINPAD_IP = os.getenv("PINPAD_IP", "10.121.112.81")
        self.PINPAD_TERMINAL_ID = os.getenv("PINPAD_TERMINAL_ID", "S0001728")
        self.PINPAD_MERCHANT_CODE = os.getenv("PINPAD_MERCHANT_CODE", "000000832686")
        
        # Oracle ERP
        self.ORACLE_HOST = os.getenv("ORACLE_HOST", "172.21.10.50")
        self.ORACLE_PORT = int(os.getenv("ORACLE_PORT", 1521))
        self.ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "PRODERP")
        self.ORACLE_USER = os.getenv("ORACLE_USER", "GEOCOM_READ")
        self.ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "PasswordOracle2026!")
        self.ORACLE_ENABLED = os.getenv("ORACLE_ENABLED", "False").lower() in ("true", "1")
        
        # Modo simulación
        self.SIMULATION_MODE = os.getenv("SIMULATION_MODE", "True").lower() in ("true", "1")

    def to_dict(self):
        """Retorna diccionario sin exponer contraseñas en texto plano para la UI"""
        return {
            "PORT": self.PORT,
            "REPO_CENTRAL_IP": self.REPO_CENTRAL_IP,
            "REPO_CENTRAL_PORT": self.REPO_CENTRAL_PORT,
            "REPO_CENTRAL_USER": self.REPO_CENTRAL_USER,
            "REPO_CENTRAL_BASE_PATH": self.REPO_CENTRAL_BASE_PATH,
            "DEFAULT_BUSINESS_UNIT": self.DEFAULT_BUSINESS_UNIT,
            "LOCAL_SERVER_IP": self.LOCAL_SERVER_IP,
            "LOCAL_SERVER_MYSQL_PORT": self.LOCAL_SERVER_MYSQL_PORT,
            "LOCAL_SERVER_MYSQL_USER": self.LOCAL_SERVER_MYSQL_USER,
            "LOCAL_ID": self.LOCAL_ID,
            "POS_SSH_USER": self.POS_SSH_USER,
            "POS_SOPORTE_USER": self.POS_SOPORTE_USER,
            "POS_MYSQL_USER": self.POS_MYSQL_USER,
            "PINPAD_IP": self.PINPAD_IP,
            "PINPAD_TERMINAL_ID": self.PINPAD_TERMINAL_ID,
            "PINPAD_MERCHANT_CODE": self.PINPAD_MERCHANT_CODE,
            "ORACLE_HOST": self.ORACLE_HOST,
            "ORACLE_PORT": self.ORACLE_PORT,
            "ORACLE_SERVICE": self.ORACLE_SERVICE,
            "ORACLE_USER": self.ORACLE_USER,
            "ORACLE_ENABLED": self.ORACLE_ENABLED,
            "SIMULATION_MODE": self.SIMULATION_MODE
        }

    def update_runtime(self, new_values: dict):
        """Permite modificar cualquier parámetro en vivo durante o antes de la ejecución"""
        for k, v in new_values.items():
            if hasattr(self, k) and not k.startswith("_"):
                # Conversión de tipos adecuada
                attr_type = type(getattr(self, k))
                if attr_type == bool:
                    setattr(self, k, str(v).lower() in ("true", "1", "yes"))
                elif attr_type == int:
                    setattr(self, k, int(v))
                else:
                    setattr(self, k, str(v))

config_instance = Config()
