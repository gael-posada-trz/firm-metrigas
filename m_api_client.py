import urequests
import ujson
import utime
import ntptime
from machine import RTC

CONFIG_FILE = "config.json"
INTERVALO_24_HORAS_SEGUNDOS = 24 * 60 * 60 

def sincronizar_hora():
    try:
        ntptime.settime()
        print("[+] Hora sincronizada por NTP.")
    except Exception as e:
        print(f"[-] Error NTP: {e}")

def guardar_config(time_target):
    with open(CONFIG_FILE, "w") as f:
        ujson.dump({"timeTarget": time_target}, f)

def leer_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return ujson.load(f).get("timeTarget")
    except OSError:
        return None

def enviar_log(url, meter_id):
    # Nota: Aquí puedes integrar tu función call_hall() interna o pasar el porcentaje por parámetro
    payload = {"currentPercentage": 80, "meterId": meter_id}
    headers = {'Content-Type': 'application/json'}
    try:
        response = urequests.post(url, data=ujson.dumps(payload), headers=headers)
        response.close()
        print("[+] Reporte enviado con éxito.")
    except Exception as e:
        print(f"[-] Error al enviar reporte: {e}")

# ESTA ES LA FUNCIÓN QUE LLAMARÁS DESDE OTRA PARTE
def iniciar_daemon_reporte(url_destino, meter_id):
    """
    Inicia el bucle infinito del daemon de reportes.
    REQUIERE: 
        - url_destino (str): La URL completa de la API (ej. 'http://192.168.1.75:3000/logs')
        - meter_id (str): El UUID del medidor
    """
    print("=== Iniciando Daemon desde módulo externo ===")
    
    # Asumimos que el Wi-Fi ya está conectado externamente como mencionaste
    sincronizar_hora()
    
    time_target = leer_config()
    tiempo_actual = utime.time()
    
    if time_target is None:
        enviar_log(url_destino, meter_id)
        time_target = tiempo_actual + INTERVALO_24_HORAS_SEGUNDOS
        guardar_config(time_target)
    else:
        if tiempo_actual >= time_target:
            print("[!] Compensando reporte perdido por apagón...")
            enviar_log(url_destino, meter_id)
            time_target = time_target + INTERVALO_24_HORAS_SEGUNDOS
            while time_target <= tiempo_actual:
                time_target += INTERVALO_24_HORAS_SEGUNDOS
            guardar_config(time_target)

    # Bucle infinito en segundo plano
    while True:
        tiempo_actual = utime.time()
        if tiempo_actual >= time_target:
            enviar_log(url_destino, meter_id)
            time_target += INTERVALO_24_HORAS_SEGUNDOS
            guardar_config(time_target)
            
        utime.sleep(5)