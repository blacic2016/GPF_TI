import json
import os
from werkzeug.security import generate_password_hash, check_password_hash

USERS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "users.json")

ROLES = {
    "ADMIN": {
        "name": "Administrador",
        "description": "Acceso total, gestión de usuarios, edición de .env en caliente, aprobación forzada de compuertas."
    },
    "OPERATOR": {
        "name": "Operador de Despliegue",
        "description": "Puede ejecutar aprovisionamiento individual y por lotes (bulk), editar parámetros de POS y aprobar compuertas."
    },
    "AUDITOR": {
        "name": "Auditor / Observador",
        "description": "Acceso de solo lectura a logs, matriz de validación y estado de los POS."
    }
}

class AuthService:
    def __init__(self):
        self._load_users()

    def _load_users(self):
        if not os.path.exists(USERS_FILE):
            # Crear usuario administrador inicial por defecto
            initial_users = {
                "admin": {
                    "username": "admin",
                    "fullname": "Administrador Principal de Infraestructura",
                    "password_hash": generate_password_hash("AdminGeo2026!"),
                    "role": "ADMIN",
                    "active": True
                },
                "operador": {
                    "username": "operador",
                    "fullname": "Técnico de Despliegue POS",
                    "password_hash": generate_password_hash("Operador2026!"),
                    "role": "OPERATOR",
                    "active": True
                },
                "auditor": {
                    "username": "auditor",
                    "fullname": "Auditor de Procesos de Negocio",
                    "password_hash": generate_password_hash("Auditor2026!"),
                    "role": "AUDITOR",
                    "active": True
                }
            }
            self._save_users(initial_users)
            self.users = initial_users
        else:
            try:
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    self.users = json.load(f)
            except Exception:
                self.users = {}

    def _save_users(self, users_dict=None):
        if users_dict is None:
            users_dict = self.users
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_dict, f, indent=4)

    def authenticate(self, username, password):
        user = self.users.get(username)
        if not user or not user.get("active", False):
            return None
        if check_password_hash(user["password_hash"], password):
            return {
                "username": user["username"],
                "fullname": user["fullname"],
                "role": user["role"]
            }
        return None

    def list_users(self):
        return [
            {
                "username": u["username"],
                "fullname": u["fullname"],
                "role": u["role"],
                "role_name": ROLES.get(u["role"], {}).get("name", u["role"]),
                "active": u.get("active", True)
            }
            for u in self.users.values()
        ]

    def create_user(self, username, fullname, password, role="OPERATOR"):
        username = username.strip().lower()
        if username in self.users:
            raise ValueError(f"El usuario '{username}' ya existe.")
        if role not in ROLES:
            raise ValueError(f"Rol inválido: '{role}'. Debe ser uno de {list(ROLES.keys())}")
        if len(password) < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")
        
        self.users[username] = {
            "username": username,
            "fullname": fullname.strip(),
            "password_hash": generate_password_hash(password),
            "role": role,
            "active": True
        }
        self._save_users()
        return self.users[username]

    def update_user(self, username, fullname=None, password=None, role=None, active=None):
        username = username.strip().lower()
        if username not in self.users:
            raise ValueError(f"El usuario '{username}' no existe.")
        
        user = self.users[username]
        if fullname is not None:
            user["fullname"] = fullname.strip()
        if role is not None:
            if role not in ROLES:
                raise ValueError(f"Rol inválido: {role}")
            user["role"] = role
        if active is not None:
            user["active"] = bool(active)
        if password:
            if len(password) < 6:
                raise ValueError("La contraseña debe tener al menos 6 caracteres.")
            user["password_hash"] = generate_password_hash(password)
            
        self._save_users()
        return user

    def delete_user(self, username):
        username = username.strip().lower()
        if username == "admin":
            raise ValueError("No se puede eliminar el usuario administrador principal.")
        if username in self.users:
            del self.users[username]
            self._save_users()
            return True
        return False

auth_service_instance = AuthService()
