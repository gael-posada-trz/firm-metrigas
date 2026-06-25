
import json
import os
import time
import requests

CONFIG_FILE = "config.json"
# Para pruebas rápidas: 10 segundos. En producción usa: 24 * 60 * 60
INTERVALO_SEGUNDOS = 10 

def guardar_config(time_target):
    """Guarda el tiempo objetivo en el archivo JSON."""
    data = {"timeTarget": time_target}
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)
    print(f"[+] Guardado en JSON próximo objetivo: {int(time_target)} (Epoch)")

def leer_config():
    """Lee el archivo JSON. Si no existe o está corrupto, devuelve None."""
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return data.get("timeTarget")
    except (json.JSONDecodeError, OSError):
        return None

def enviar_log(url, meter_id):
    """Envía la petición POST usando la librería requests estándar."""
    payload = {
        "currentPercentage": 80, 
        "meterId": meter_id
    }
    try:
        print("[*] Enviando POST a la base de datos...")
        response = requests.post(url, json=payload, timeout=5)
        print(f"    Código de respuesta: {response.status_code}")
        if response.status_code in [200, 201]:
            print(f"    Respuesta: {response.json()}")
        else:
            print(f"    Error en servidor: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"[-] Error de red/conexión: {e}")

def iniciar_daemon_reporte(url_destino, meter_id):
    """Ejecuta la lógica del daemon usando el tiempo del sistema."""
    print("=== Iniciando Daemon de Pruebas (Python Común) ===")
    
    # En Python normal, time.time() da la hora real del sistema operativa (ya sincronizada)
    tiempo_actual = time.time()
    time_target = leer_config()
    
    if time_target is None:
        # --- CASO 1: Primera iteración en la historia ---
        print("[*] No existe variable en JSON. Primera ejecución...")
        enviar_log(url_destino, meter_id)
        time_target = tiempo_actual + INTERVALO_SEGUNDOS
        guardar_config(time_target)
    else:
        # --- CASO 2: Regresando de un apagón / reinicio ---
        print(f"[*] Recuperado objetivo del JSON: {int(time_target)}")
        print(f"[*] Tiempo actual real: {int(tiempo_actual)}")
        
        if tiempo_actual >= time_target:
            # El tiempo actual es MAYOR o igual: Se perdió un reporte mientras estaba apagado
            print("[!] COMPENSACIÓN: Se detectó que debió hacerse un POST mientras estaba apagado.")
            enviar_log(url_destino, meter_id)
            
            # Recalculamos el siguiente objetivo sumando el intervalo
            time_target = time_target + INTERVALO_SEGUNDOS
            # Si pasó demasiado tiempo apagado, este bucle actualiza el JSON al futuro correcto
            while time_target <= tiempo_actual:
                time_target += INTERVALO_SEGUNDOS
            guardar_config(time_target)
        else:
            # El tiempo actual es MENOR: Todavía no toca, se mantiene el objetivo viejo
            print("[*] Reinicio temprano. Continuando espera del objetivo guardado...")

    # --- BUCLE CONTINUO EN SEGUNDO PLANO ---
    print(f"[*] Entrando en bucle de monitoreo (revisión cada segundo)...")
    while True:
        tiempo_actual = time.time()
        
        if tiempo_actual >= time_target:
            print(f"\n[*] ¡Plazo cumplido! Tiempo actual: {int(tiempo_actual)}")
            enviar_log(url_destino, meter_id)
            
            # Programar el siguiente ciclo y actualizar JSON
            time_target += INTERVALO_SEGUNDOS
            guardar_config(time_target)
            
        time.sleep(1)

def main():
    # Parámetros de prueba local
    MI_URL = "http://localhost:3000/logs" 
    MI_METER_ID = "3bc8e162-4217-4934-bc2c-5645367b1201"
    
    # Invocar la función del daemon
    iniciar_daemon_reporte(url_destino=MI_URL, meter_id=MI_METER_ID)

if __name__ == "__main__":
    main()