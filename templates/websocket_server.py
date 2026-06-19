async def manejar_websocket(ws):
    print("¡Flutter se ha conectado por WebSocket!")
    try:
        while True:
            mensaje = await ws.recv()
            if mensaje is None:
                break
            print("Recibido de Flutter:", mensaje)
            await ws.send(f"ESP32 recibió: {mensaje}")
    except Exception as e:
        print("Conexión WebSocket cerrada:", e)

def iniciar_servidor_websocket(ip_local):
    print(f"Iniciando Servidor WebSocket en ws://{ip_local}:8765")
    server = MicroPythonWebSocketServer(manejar_websocket, "0.0.0.0", 8765)
    server.start()
    
    loop = asyncio.get_event_loop()
    loop.run_forever()

print(f"Conectando a {credenciales['ssid']}...")
intentos = 0
while not sta.isconnected() and intentos < 15:
    time.sleep(1)
    intentos += 1
    
if sta.isconnected():
    print("¡Conectado exitosamente!")
    ip_local = sta.ifconfig()[0]
    print("IP Local asignada:", ip_local)
    iniciar_servidor_websocket(ip_local)
else:
    print("No se pudo conectar al WiFi. Borrando credenciales...")
    os.remove(CONFIG_FILE)
    machine.reset()