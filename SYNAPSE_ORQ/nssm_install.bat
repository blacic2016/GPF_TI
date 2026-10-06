@echo off
REM ====================================================================
REM GUÍA Y SCRIPT DE INSTALACIÓN DEL SERVICIO ENTERPRISE DE WINDOWS (NSSM)
REM Plataforma NOVAIOPS - SONDA S.A.
REM ====================================================================

echo [1/3] Verificando permisos de Administrador...
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo Error: Este script debe ejecutarse como ADMINISTRADOR en PowerShell/CMD.
    pause
    exit /b 1
)

echo [2/3] Creando Servicio para el Demonio MAPI de Outlook...
REM Reemplazar las rutas segun la instalacion de Python en el servidor
set PYTHON_PATH=C:\Python310\python.exe
set APP_DIR=c:\SYNAPSE_ORQ

nssm install NOVAIOPS_Daemon "%PYTHON_PATH%" "%APP_DIR%\daemon\listener_daemon.py"
nssm set NOVAIOPS_Daemon AppDirectory "%APP_DIR%"
nssm set NOVAIOPS_Daemon DisplayName "SONDA NOVAIOPS Outlook Realtime Daemon"
nssm set NOVAIOPS_Daemon Description "Demonio de escucha en tiempo real de correos MAPI e integracion con IA n8n/Gemini para SONDA."
nssm set NOVAIOPS_Daemon Start SERVICE_AUTO_START

echo [3/3] Creando Servicio para la Interfaz Web SPA...
nssm install NOVAIOPS_WebApp "%PYTHON_PATH%" "%APP_DIR%\web_app\app.py"
nssm set NOVAIOPS_WebApp AppDirectory "%APP_DIR%"
nssm set NOVAIOPS_WebApp DisplayName "SONDA NOVAIOPS Web Management Console"
nssm set NOVAIOPS_WebApp Start SERVICE_AUTO_START

echo.
echo ====================================================================
echo SERVICIOS REGISTRADOS EXITOSAMENTE.
echo Para iniciar los servicios ejecute:
echo   nssm start NOVAIOPS_Daemon
echo   nssm start NOVAIOPS_WebApp
echo ====================================================================
pause
