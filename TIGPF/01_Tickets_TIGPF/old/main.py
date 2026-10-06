import os
import subprocess
import sys
from datetime import datetime

# --- CONFIGURACIÓN ---
# ▼▼▼ ¡IMPORTANTE! CAMBIA ESTA LÍNEA POR LA RUTA REAL DE TU CARPETA DE SCRIPTS ▼▼▼
CARPETA_DE_SCRIPTS = "C:\zabbix\python\GPF\PlanesdeCredito" 
# Ejemplo para Windows: "C:/Users/TuUsuario/Documents/ScriptsVeeam"
# Ejemplo para Linux/Mac: "/home/TuUsuario/scripts_veeam"
# ▲▲▲ ¡IMPORTANTE! ▲▲▲

def ejecutar_scripts_secuencialmente(ruta_carpeta):
    """
    Busca y ejecuta todos los scripts .py en una carpeta de forma secuencial y ordenada.
    
    Args:
        ruta_carpeta (str): La ruta a la carpeta que contiene los scripts.
    """
    print("=" * 80)
    print(f"--- Iniciando Ejecutador de Scripts Secuenciales ---")
    print(f"Fecha y Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Carpeta de Scripts: {ruta_carpeta}")
    print("=" * 80)

    # 1. Verificar si la carpeta existe
    if not os.path.isdir(ruta_carpeta):
        print(f"\n[ERROR] La carpeta especificada no existe: {ruta_carpeta}")
        print("Por favor, verifica la ruta en la variable 'CARPETA_DE_SCRIPTS' dentro del script.")
        return

    # 2. Encontrar y ordenar los scripts
    try:
        # Obtiene todos los archivos, los filtra por .py y los ordena alfabéticamente
        scripts_a_ejecutar = sorted([f for f in os.listdir(ruta_carpeta) if f.endswith('.py')])
        
        if not scripts_a_ejecutar:
            print("\n[ADVERTENCIA] No se encontraron archivos .py en la carpeta.")
            return
            
    except Exception as e:
        print(f"\n[ERROR] No se pudo leer el contenido de la carpeta: {e}")
        return

    # 3. Ejecutar cada script de forma secuencial
    total_scripts = len(scripts_a_ejecutar)
    print(f"\nSe encontraron {total_scripts} scripts para ejecutar en el siguiente orden:")
    for i, script in enumerate(scripts_a_ejecutar, 1):
        print(f"  {i}. {script}")
    
    scripts_fallidos = 0
    
    for i, script_nombre in enumerate(scripts_a_ejecutar, 1):
        ruta_completa_script = os.path.join(ruta_carpeta, script_nombre)
        
        print("\n" + "-" * 80)
        print(f"[{i}/{total_scripts}] Ejecutando: {script_nombre}...")
        
        try:
            # Usar el mismo ejecutable de Python que está corriendo este script
            python_executable = sys.executable
            
            # subprocess.run es un llamado bloqueante: espera a que el proceso termine.
            resultado = subprocess.run(
                [python_executable, ruta_completa_script],
                capture_output=True,  # Captura la salida estándar y los errores
                text=True,            # Decodifica la salida como texto
                encoding='utf-8',     # Especifica la codificación
                errors='replace',
                check=False           # No lanza excepción si el script falla, lo manejamos manualmente
            )

            # Imprimir la salida estándar del script ejecutado
            if resultado.stdout:
                print("--- Salida del Script ---")
                print(resultado.stdout.strip())
                print("-------------------------")

            # Verificar si el script finalizó correctamente (código de salida 0)
            if resultado.returncode == 0:
                print(f"[ÉXITO] '{script_nombre}' finalizó correctamente.")
            else:
                scripts_fallidos += 1
                print(f"\n[ERROR] '{script_nombre}' finalizó con código de error {resultado.returncode}.")
                # Imprimir la salida de error si existe
                if resultado.stderr:
                    print("--- Salida de Error del Script ---")
                    print(resultado.stderr.strip())
                    print("----------------------------------")
                
        except FileNotFoundError:
            print(f"\n[ERROR CRÍTICO] No se encontró el script: {ruta_completa_script}")
            scripts_fallidos += 1
        except Exception as e:
            print(f"\n[ERROR CRÍTICO] Ocurrió un error al intentar ejecutar '{script_nombre}': {e}")
            scripts_fallidos += 1

    # 4. Resumen final
    print("\n" + "=" * 80)
    print("--- Ejecución Completada ---")
    if scripts_fallidos == 0:
        print("Estado: ¡Todos los scripts se ejecutaron con éxito!")
    else:
        print(f"Estado: Finalizado con {scripts_fallidos} de {total_scripts} scripts fallidos.")
    print("=" * 80)


if __name__ == "__main__":
    ejecutar_scripts_secuencialmente(CARPETA_DE_SCRIPTS)
    # input("Presiona Enter para salir...") # Descomenta esta línea si quieres que la ventana no se cierre al final
