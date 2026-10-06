# GPF_TI

Plataforma y herramientas de automatización de TI para Corporación GPF.

## Módulos y Componentes

### 1. PROCESOPOS
- **Sistema Automatizado POS (GeoPOS):** Aprovisionamiento, configuración remota y despliegue de cajas POS.
- **Microservicios y Conectores:** SSH/SCP con repositorio de artefactos, configuración MySQL local, Pinpad y ERP Oracle.
- **Supervisor y Panel Web:** Servidor web Flask y panel de control en tiempo real (`app.py`, `supervisor.py`).
- **Persistencia de Trabajos:** Historial de tareas y estados de despliegue (`storage/pos_jobs.db`).

### 2. SYNAPSE_ORQ
- **Orquestador y Daemon de Servicios:** Servicio de monitoreo e ingesta automatizada MAPI / correo.
- **Firewall de Payload & Validación:** Control y enrutamiento de peticiones de automatización.
- **Web App & Dashboard:** Panel de monitoreo de microservicios y estado operativo.
- **Base de Datos:** Persistencia local y registro de estado (`novaiops.db`).

### 3. TIGPF / 01_Tickets_TIGPF
- **Monitoreo de Tickets y Planes de Crédito:** Ingesta de reportes de correo periódicos.
- **Analizador de Tickets:** Motor de análisis y métricas sobre tiempos de respuesta, grupos y analistas.
- **Dashboard Web:** Servidor Flask y visualización gráfica con estadísticas en tiempo real (`server.py`).
- **Persistencia:** Base de datos SQLite (`TI_GPF.db`) y generación de reportes en Excel.

### 4. ORACLE
- Integraciones y utilidades de base de datos Oracle.

---

### Requisitos y Configuración
- Python 3.10+
- Dependencias especificadas en cada submódulo (`requirements.txt`).
