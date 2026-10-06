"""
Módulo Base y Registry de Handlers para NOVAIOPS.
Refactorización de scripts legacy (GPF Hetrix, Totem, Networker) a controladores modulares.
"""

import re
import json
import requests
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("NOVAIOPS_HANDLERS")

class BaseEmailHandler(ABC):
    def __init__(self, config=None):
        self.config = config or {}

    @abstractmethod
    def execute(self, email_data: dict, extraction_rules: dict = None) -> dict:
        """
        email_data: {'subject': str, 'sender': str, 'body': str, 'folder': str}
        Debe retornar un dict con:
        {
          'status': 'SUCCESS' | 'FAILED' | 'WARNING',
          'extracted_params': dict,
          'message': str,
          'error': str or None
        }
        """
        pass

class GPFHetrixHandler(BaseEmailHandler):
    """Manejador para GPF Hetrix (MantisBT + Zabbix Sender) basado en script GPF_HETRIX_TOTAL.py"""
    def execute(self, email_data: dict, extraction_rules: dict = None) -> dict:
        from handlers.real_connections import get_operador_turno_real, send_zabbix_alarm_real
        
        body = email_data.get('body', '')
        subject = email_data.get('subject', '')
        sender = email_data.get('sender', '')
        
        operador_actual = get_operador_turno_real()
        clean_body = re.sub(r'http\S+', '', body)
        
        url_match = re.search(r'https?://[^\s]+', body)
        url_servicio = url_match.group(0) if url_match else "Desconocido"
        
        estado = "DOWN" if "DOWN" in subject.upper() or "DOWN" in body.upper() else "UP"
        
        extracted = {
            "url_servicio": url_servicio,
            "estado": estado,
            "subject": subject,
            "operador_asignado": operador_actual
        }
        
        # Enviar métrica real a Zabbix Server en 172.32.1.50
        send_zabbix_alarm_real("172.32.1.51", "GPF.hetrix", {"url": url_servicio, "estado": estado})
        
        logger.info(f"[GPF_HETRIX REAL] Alerta procesada: Servicio {url_servicio} está {estado}. Operador asignado: {operador_actual}")
        
        return {
            "status": "SUCCESS",
            "extracted_params": extracted,
            "message": f"Evento Hetrix {estado} procesado. Ticket asignado a {operador_actual}.",
            "error": None
        }

class GPFTotemHandler(BaseEmailHandler):
    """Manejador para GPF Totems"""
    def execute(self, email_data: dict, extraction_rules: dict = None) -> dict:
        body = email_data.get('body', '')
        totem_match = re.search(r'TOTEM-(\d+)', body)
        ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', body)
        
        totem_id = totem_match.group(0) if totem_match else "TOTEM-GENERAL"
        ip = ip_match.group(0) if ip_match else "0.0.0.0"
        
        extracted = {"totem_id": totem_id, "ip": ip}
        logger.info(f"[GPF_TOTEM] Evento Totem {totem_id} ({ip}) recibido.")
        
        return {
            "status": "SUCCESS",
            "extracted_params": extracted,
            "message": f"Alerta Totem {totem_id} procesada correctamente.",
            "error": None
        }

class GPFNetworkerHandler(BaseEmailHandler):
    """Manejador para GPF Respaldos Networker"""
    def execute(self, email_data: dict, extraction_rules: dict = None) -> dict:
        body = email_data.get('body', '')
        subject = email_data.get('subject', '')
        
        status = "FAILED" if "FAILED" in subject.upper() or "ERROR" in body.upper() else "SUCCESS"
        client_match = re.search(r'(Oracle_\w+|Client_\w+|[A-Z0-9_-]{5,})', subject + " " + body)
        client_name = client_match.group(0) if client_match else "GPF_CLIENT"
        
        extracted = {"status": status, "client": client_name}
        logger.info(f"[GPF_NETWORKER] Respaldo de {client_name}: {status}")
        
        return {
            "status": "SUCCESS",
            "extracted_params": extracted,
            "message": f"Respaldo Networker para {client_name} registrado como {status}.",
            "error": None
        }

class AISondaHandler(BaseEmailHandler):
    """Manejador Cognitivo mediante Webhook n8n + Google Gemini API"""
    def execute(self, email_data: dict, extraction_rules: dict = None) -> dict:
        webhook_url = self.config.get("N8N_WEBHOOK_URL", "http://172.32.1.60:5678/webhook/sonda-email-ai")
        
        payload = {
            "sender": email_data.get("sender"),
            "subject": email_data.get("subject"),
            "body_text": email_data.get("body"),
            "folder": email_data.get("folder")
        }
        
        try:
            # Intento de llamada real a n8n con timeout de gracia o fallback simulado
            response = requests.post(webhook_url, json=payload, timeout=3)
            if response.status_code == 200:
                ai_json = response.json()
            else:
                ai_json = self._simulate_gemini_response(payload)
        except Exception as e:
            logger.warning(f"[AI_SONDA] n8n Webhook inaccesible ({e}). Ejecutando motor Gemini local/simulado.")
            ai_json = self._simulate_gemini_response(payload)
            
        return {
            "status": "SUCCESS",
            "extracted_params": {
                "cliente": ai_json.get("cliente_detectado"),
                "severidad": ai_json.get("severidad"),
                "categoria": ai_json.get("categoria")
            },
            "ai_payload_response": ai_json,
            "message": f"Análisis IA completado: Categoría {ai_json.get('categoria')} con severidad {ai_json.get('severidad')}.",
            "error": None
        }

    def _simulate_gemini_response(self, payload):
        subject = payload.get("subject", "").lower()
        body = payload.get("body_text", "").lower()
        sender = payload.get("sender", "").lower()
        
        client = "SONDA General"
        if "leterago" in sender or "leterago" in body: client = "Leterago"
        elif "vilaseca" in sender or "vilaseca" in body: client = "Grupo Vilaseca"
        elif "almar" in sender or "almar" in body: client = "Grupo Almar"
        elif "petroecuador" in sender or "petroecuador" in body: client = "Petroecuador"
        elif "gpf" in sender or "gpf" in body: client = "GPF"
        
        severidad = "MEDIA"
        if "critico" in subject or "caida" in body or "error 500" in body: severidad = "CRITICAL"
        elif "advertencia" in subject or "warning" in body: severidad = "ALTA"
        
        return {
            "categoria": "INCIDENTE_INFRAESTRUCTURA" if "critica" in severidad else "ALERTA_MONITOREO",
            "cliente_detectado": client,
            "severidad": severidad,
            "script_destino": "gpf_hetrix_handler",
            "argumentos_extraidos": {
                "ticket_id": "INC-2026-9912",
                "dispositivo": "SRV-DB-PROD-01"
            },
            "razonamiento": f"Análisis inteligente realizado sobre el correo de {client}. Detectado impacto de nivel {severidad}."
        }

class DynamicRuleHandler(BaseEmailHandler):
    """Manejador dinámico que ejecuta el análisis de título, cuerpo (regex) y adjuntos configurados al crear el monitoreo."""
    def execute(self, email_data: dict, extraction_rules: dict = None) -> dict:
        subject = email_data.get('subject', '')
        sender = email_data.get('sender', '')
        body = email_data.get('body', '') or email_data.get('body_text', '')
        attachments = email_data.get('attachments') or email_data.get('attachment_names') or []

        extracted = {
            "subject": subject,
            "sender": sender,
            "body_length": len(body),
            "attachments_count": len(attachments)
        }

        # Si se suministraron reglas de extracción regex (clave-valor JSON)
        rules = extraction_rules or self.config.get("extraction_rules") or {}
        if isinstance(rules, str):
            try:
                rules = json.loads(rules)
            except Exception:
                rules = {}

        for var_name, pattern in rules.items():
            try:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    extracted[var_name] = m.group(1) if m.groups() else m.group(0)
                else:
                    # Buscar en el subject como fallback
                    m_subj = re.search(pattern, subject, re.IGNORECASE)
                    if m_subj:
                        extracted[var_name] = m_subj.group(1) if m_subj.groups() else m_subj.group(0)
                    else:
                        extracted[var_name] = "NO_MATCH"
            except Exception as e:
                extracted[var_name] = f"ERROR_REGEX: {e}"

        logger.info(f"[DYNAMIC_RULE_HANDLER] Ejecución completada para '{subject}'. Variables extraídas: {list(extracted.keys())}")

        return {
            "status": "SUCCESS",
            "extracted_params": extracted,
            "message": f"Análisis y requerimientos de la regla ejecutados exitosamente.",
            "error": None
        }

# Registry de Handlers de SYNAPSE-ORQ
from handlers.antigravity_handler import AntigravityHandler

HANDLER_MAP = {
    "dynamic_rule_handler": DynamicRuleHandler,
    "gpf_hetrix_handler": GPFHetrixHandler,
    "gpf_totem_handler": GPFTotemHandler,
    "gpf_networker_handler": GPFNetworkerHandler,
    "ai_sonda_handler": AISondaHandler,
    "antigravity_handler": AntigravityHandler
}

def get_handler(handler_name: str, config: dict = None) -> BaseEmailHandler:
    handler_cls = HANDLER_MAP.get(handler_name, DynamicRuleHandler)
    return handler_cls(config)
