# GPF_TI

Plataforma y herramientas de automatización de TI para Corporación GPF.

## Módulos y Componentes

### 1. SYNAPSE_ORQ
- **Orquestador y Daemon de Servicios:** Servicio de monitoreo e ingesta automatizada MAPI / correo.
- **Firewall de Payload & Validación:** Control y enrutamiento de peticiones de automatización.
- **Web App & Dashboard:** Panel de monitoreo de microservicios y estado operativo.
- **Base de Datos:** Persistencia local y registro de estado (`novaiops.db`).

### 2. TIGPF / 01_Tickets_TIGPF
- **Monitoreo de Tickets y Planes de Crédito:** Ingesta de reportes de correo periódicos.
- **Analizador de Tickets:** Motor de análisis y métricas sobre tiempos de respuesta, grupos y analistas.
- **Dashboard Web:** Servidor Flask y visualización gráfica con estadísticas en tiempo real (`server.py`).
- **Persistencia:** Base de datos SQLite (`TI_GPF.db`) y generación de reportes en Excel.

### 3. ORACLE
- Integraciones y utilidades de base de datos Oracle.

---

### Requisitos y Configuración
- Python 3.10+
- Dependencias especificadas en cada submódulo (`requirements.txt`).
