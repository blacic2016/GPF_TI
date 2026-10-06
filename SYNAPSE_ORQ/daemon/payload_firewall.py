"""
SYNAPSE-ORQ Payload Firewall & Sanitizer
Módulo de Control de Tamaño y Sanitización de Correos para SYNAPSE-ORQ.
Protege el demonio MAPI y n8n/Gemini contra DoS por memoria y adjuntos maliciosos.
"""

import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger("SYNAPSE_CORE")

# Configuración de límites operativos de SYNAPSE-ORQ
MAX_BODY_CHARS = 20000          # Máximo de caracteres permitidos para análisis de texto / IA
MAX_ATTACHMENT_SIZE_MB = 15     # Límite estricto de tamaño por archivo adjunto
BLOCKED_EXTENSIONS = {".exe", ".bat", ".vbs", ".cmd", ".scr", ".pif", ".js"}
TEMP_ATTACHMENT_DIR = Path("C:/SYNAPSE_ORQ/temp_attachments")
TEMP_ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)

def sanitize_and_filter_email(item):
    """
    Filtra y limita el tamaño del correo y sus adjuntos antes de encolarlo en SYNAPSE-ORQ.
    """
    try:
        subject = item.Subject[:255] if getattr(item, "Subject", None) else "Sin Asunto"
        sender = getattr(item, "SenderEmailAddress", None) or "Remitente Desconocido"
        body = getattr(item, "Body", None) or ""
        
        # 1. Control de tamaño del cuerpo del correo (Mitigación de DoS por memoria)
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS] + "\n\n[SYNAPSE-ORQ WARNING: Cuerpo truncado por superar el límite operativo de tamaño]."
            logger.warning(f"SYNAPSE-ORQ Firewall: Cuerpo truncado a {MAX_BODY_CHARS} caracteres para '{subject}'")
        
        # 2. Gestión segura de archivos adjuntos
        processed_attachments = []
        if hasattr(item, "Attachments") and item.Attachments.Count > 0:
            for i in range(1, item.Attachments.Count + 1):
                att = item.Attachments.Item(i)
                file_name = getattr(att, "FileName", f"attachment_{i}.bin")
                file_ext = Path(file_name).suffix.lower()
                
                # Validación de seguridad contra extensiones peligrosas
                if file_ext in BLOCKED_EXTENSIONS:
                    logger.warning(f"SYNAPSE-ORQ Security: Adjunto bloqueado por política de seguridad -> {file_name}")
                    continue
                
                # Validación de tamaño (Outlook size en bytes)
                file_size_bytes = getattr(att, "Size", 0)
                file_size_mb = file_size_bytes / (1024 * 1024)
                if file_size_mb > MAX_ATTACHMENT_SIZE_MB:
                    logger.warning(f"SYNAPSE-ORQ Size Limit: Adjunto {file_name} ({file_size_mb:.2f}MB) excede el límite de {MAX_ATTACHMENT_SIZE_MB}MB.")
                    continue
                
                # Guardado seguro en directorio temporal para análisis posterior por los scripts
                safe_path = TEMP_ATTACHMENT_DIR / file_name
                try:
                    att.SaveAsFile(str(safe_path))
                    processed_attachments.append(str(safe_path))
                    logger.info(f"SYNAPSE-ORQ Firewall: Adjunto guardado de forma segura -> {safe_path}")
                except Exception as att_err:
                    logger.error(f"SYNAPSE-ORQ Error guardando adjunto {file_name}: {str(att_err)}")
                
        return {
            "entry_id": getattr(item, "EntryID", ""),
            "subject": subject,
            "sender": sender,
            "body_text": body,
            "received_time": str(getattr(item, "ReceivedTime", "")),
            "attachments": processed_attachments,
            "folder": "Bandeja de entrada"
        }
    except Exception as e:
        logger.error(f"SYNAPSE-ORQ Error sanitizando correo: {str(e)}")
        return None
