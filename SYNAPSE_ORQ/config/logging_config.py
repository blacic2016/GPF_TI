import logging
from logging.handlers import RotatingFileHandler
import os

def init_synapse_logger():
    os.makedirs("logs", exist_ok=True)
    log_path = "logs/synapse_daemon.log"
    
    # Rotación estricta: Máximo 10 MB por archivo, hasta 15 respaldos históricos
    handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=15, encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] [SYNAPSE-ORQ] %(filename)s:%(lineno)d - %(message)s')
    handler.setFormatter(formatter)
    
    logger = logging.getLogger("SYNAPSE_CORE")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger
