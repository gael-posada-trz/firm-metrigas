import asyncio
import json
import websockets

# URL del ESP32 usando el mDNS de fábrica o su IP actual
# Si ya lo renombraste antes, cambia "esp32-prov" por el nombre actual
ESP32_URL = "ws://192.168.1.105:8765"

# Parámetros estáticos del LCG (deben coincidir exactamente con el ESP32)
LCG_PARAMS = {
    "x": 123456,
    "A": 20011,
    "B": 12345,
    "BASE": 65536
}

def encode_lcg(plaintext, initial_params):
    """Cifra el texto plano usando el Generador Congruencial Lineal (LCG)."""
    x = initial_params["x"]
    A = initial_params["A"]
    B = initial_params["B"]
    base = initial_params["BASE"]
    
    raw_bytes = plaintext.encode('utf-8')
    encrypted_bytes = bytearray(len(raw_bytes))
    
    for j in range(len(raw_bytes)):
        x = (x * A + B) % base
        encrypted_bytes[j] = raw_bytes[j] ^ (x % 256)
        
    return bytes(encrypted_bytes)

async def enviar_cambio_nombre():
    # 1. Estructura el JSON con tu nuevo formato de arreglos compactos
    mensaje_json = json.dumps({"action": "get_percentage"})
    print(f"[CLIENTE] Texto plano a enviar: {mensaje_json}")
    
    # 2. Cifrar el JSON con el LCG antes de mandarlo por el aire
    payload_cifrado = encode_lcg(mensaje_json, LCG_PARAMS)
    
    print(f"[CLIENTE] Conectando a {ESP32_URL}...")
    try:
        # 3. Abrir el socket, enviar el buffer binario y esperar la respuesta
        async with websockets.connect(ESP32_URL) as websocket:
            print("[CLIENTE] Conexión establecida. Enviando paquete cifrado...")
            await websocket.send(payload_cifrado)
            
            # 4. Recibir respuesta del ESP32 (viene en texto plano/JSON directo)
            respuesta_cruda = await websocket.recv()
            print(f"[ESP32 RESPUESTA]: {respuesta_cruda}")
            
    except Exception as e:
        print(f"[CLIENTE] Error en la comunicación: {e}")

# Ejecutar el script asíncrono
asyncio.run(enviar_cambio_nombre())