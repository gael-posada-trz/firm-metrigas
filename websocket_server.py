import json
import utime
import uasyncio
import machine
from machine import Pin

# Módulos de tu arquitectura
import boot
import config_manager
import sensor_hall

TAG = "[WS_SERVER]"

# Intentar importar mDNS nativo de MicroPython (disponible en builds de ESP32)
try:
    import wp2
    mdns = wp2.mDNS()
except:
    # Fallback si tu firmware usa la librería nativa de red para mDNS
    import network
    mdns = network.WLAN(network.STA_IF)

def inicializar_o_actualizar_mdns(nombre_dominio):
    """
    Registra o cambia el nombre de dominio mDNS en la red local.
    Si es la primera vez, usará 'gas-device', si no, el nombre del usuario.
    """
    try:
        # Reemplazar espacios y caracteres raros para evitar romper el protocolo mDNS
        clean_name = nombre_dominio.lower().replace(" ", "-")
        
        # En la mayoría de los firmwares de MicroPython modernos con ESP32-S3:
        if hasattr(mdns, "config"):
            mdns.config(hostname=clean_name)
        else:
            # Si se usa un objeto mDNS dedicado de un módulo externo
            mdns.start(clean_name, "local")
            
        print(f"{TAG} mDNS Activo. Dispositivo accesible localmente en: http://{clean_name}.local")
    except Exception as e:
        print(f"{TAG} Advertencia al configurar mDNS (Sistemas sin soporte nativo completo):", e)

def decodificar_lcg(datos_cifrados, params_iniciales):
    """
    Descifra un bloque de bytes utilizando el Generador Congruencial Lineal (1 solo ciclo).
    Replica exactamente la lógica matemática de tu archivo sockets.cpp.
    """
    # Desempaquetar parámetros del generador congruencial
    x = params_iniciales["x"]
    A = params_iniciales["A"]
    B = params_iniciales["B"]
    base = params_iniciales["BASE"]
    
    resultado_bytes = bytearray(len(datos_cifrados))
    
    for j in range(len(datos_cifrados)):
        # Fórmula LCG: Siguiente estado pseudoaleatorio
        x = (x * A + B) % base
        
        # Aplicamos el Bitwise XOR entre el byte cifrado y el número generado
        resultado_bytes[j] = datos_cifrados[j] ^ (x % 256)
        
    try:
        # Convertimos el arreglo de bytes descifrados a texto plano (JSON String)
        return resultado_bytes.decode('utf-8')
    except Exception as e:
        print(f"{TAG} ERROR: Error de codificación al descifrar paquete LCG:", e)
        return None

async def procesar_comando_cliente(ws, texto_plano):
    """
    Manejador de la lógica de negocio de los mensajes JSON entrantes de Flutter.
    """
    try:
        payload = json.loads(texto_plano)
        action = payload.get("action")
        
        # CASO 1: Handshake Inicial donde la App registra el nombre personalizado del medidor
        if action == "set_name":
            nuevo_nombre = payload.get("device_name")
            if nuevo_nombre:
                print(f"{TAG} Solicitud de renombrado recibida. Nuevo nombre: '{nuevo_nombre}'")
                
                # Guardar de forma atómica en el almacenamiento local Flash (config.json)
                config_manager.save_config_atomic(device_name=nuevo_nombre)
                
                # Mutar dinámicamente el mDNS en caliente
                inicializar_o_actualizar_mdns(nuevo_nombre)
                
                # Responder confirmación técnica
                await ws.send(json.dumps({"status": "success", "message": "Name updated, mDNS active"}))
                
        # CASO 2: Solicitud bajo demanda del porcentaje de gas actual
        elif action == "get_telemetry":
            respuesta = {
                "status": "metrics",
                "gas_percentage": sensor_hall.current_gas_percentage,
                "timestamp": utime.ticks_ms()
            }
            await ws.send(json.dumps(respuesta))
            
    except Exception as e:
        print(f"{TAG} Error al procesar JSON descifrado:", e)

async def manejar_cliente_websocket(reader, writer):
    """
    Manejador asíncrono de bajo nivel para las conexiones entrantes del WebSocket.
    Soporta la recepción de payloads cifrados binarios.
    """
    print(f"{TAG} Nueva conexión WebSocket establecida desde la app Flutter.")
    
    # Parámetros de prueba fijos acoplados a tu archivo sockets.cpp (Deben coincidir con Flutter)
    # En producción estos parámetros pueden derivar de un intercambio de claves basado en la clave pública
    parametros_lcg = {
        "x": 123456,  # Semilla inicializada (Seed + Contraseña)
        "A": 20011,   # Siguiente primo del ejemplo sockets.cpp
        "B": 12345,
        "BASE": 65536
    }
    
    try:
        while True:
            # Leer el tamaño del frame o el buffer crudo del socket local
            linea = await reader.read(1024)
            if not linea:
                break  # Desconexión limpia del cliente
                
            # Identificar si es un frame de WebSocket válido (Extracción de Payload Útil)
            # Nota: Si usas Microdot_WebSocket, este procesamiento de bytes se simplifica a:
            # datos_cifrados = await ws.recv()
            
            # Asumiendo que recibes los bytes crudos cifrados por el canal binario:
            texto_descifrado = decodificar_lcg(linea, parametros_lcg)
            
            if texto_descifrado:
                print(f"{TAG} Mensaje LCG Descifrado Exitosamente: {texto_descifrado}")
                # Ejecutar lógica de comandos
                # Inyectamos un objeto mock 'ws' para simular la respuesta
                class WS_Wrapper:
                    async def send(self, msg):
                        writer.write(msg.encode('utf-8'))
                        await writer.drain()
                
                await procesar_comando_cliente(WS_Wrapper(), texto_descifrado)
                
    except Exception as error_socket:
        print(f"{TAG} Conexión de cliente finalizada o interrumpida:", error_socket)
    finally:
        writer.close()
        await writer.wait_closed()
        print(f"{TAG} Sockets liberados atómicamente.")

async def start_websocket_server():
    """
    Lanza el demonio del servidor local WebSocket en el puerto 8765.
    Configura el nombre mDNS inicial antes de abrir las compuertas de red.
    """
    # 1. Determinar el nombre de dominio. Si está vacío en config.json, usar el genérico de fábrica
    nombre_inicial = boot.device_name if boot.device_name else "gas-device"
    print(f"{TAG} Configurando infraestructura mDNS inicial...")
    inicializar_o_actualizar_mdns(nombre_inicial)
    
    # 2. Inicializar el socket del servidor asíncrono cooperativo
    print(f"{TAG} Abriendo servidor WebSocket local en el puerto 8765...")
    try:
        servidor = await uasyncio.start_server(manejar_cliente_websocket, "0.0.0.0", 8765)
        print(f"{TAG} Servidor en línea de forma exitosa.")
        
        # Mantener la tarea viva indefinidamente en el planificador
        while True:
            await uasyncio.sleep(3600)
    except Exception as e:
        print(f"{TAG} CRITICAL ERROR: No se pudo montar el servidor local:", e)