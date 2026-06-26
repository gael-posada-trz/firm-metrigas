import json
import utime
import uasyncio
import machine
from machine import Pin

# Architecture modules
import boot
import config_manager
import sensor_hall

TAG = "[WS_SERVER]"

# Try to import native MicroPython mDNS (available on ESP32 builds)
try:
    import wp2
    mdns = wp2.mDNS()
except:
    # Fallback if your firmware uses the native network library for mDNS
    import network
    mdns = network.WLAN(network.STA_IF)

def init_or_update_mdns(domain_name):
    """
    Registers or updates the mDNS domain name on the local network.
    If it's the first time, it will use 'gas-device', otherwise, the user's custom name.
    """
    try:
        # Replace spaces and special characters to avoid breaking the mDNS protocol
        clean_name = domain_name.lower().replace(" ", "-")
        
        # On most modern MicroPython firmwares with ESP32-S3:
        if hasattr(mdns, "config"):
            mdns.config(hostname=clean_name)
        else:
            # If using a dedicated mDNS object from an external module
            mdns.start(clean_name, "local")
            
        print(f"{TAG} mDNS Active. Device locally accessible at: http://{clean_name}.local")
    except Exception as e:
        print(f"{TAG} Warning when configuring mDNS (Systems without full native support):", e)

def decode_lcg(encrypted_data, initial_params):
    """
    Decrypts a block of bytes using a Linear Congruential Generator (single cycle).
    Exactly replicates the mathematical logic from your sockets.cpp file.
    """
    # Unpack congruential generator parameters
    x = initial_params["x"]
    A = initial_params["A"]
    B = initial_params["B"]
    base = initial_params["BASE"]
    
    result_bytes = bytearray(len(encrypted_data))
    
    for j in range(len(encrypted_data)):
        # LCG Formula: Next pseudorandom state
        x = (x * A + B) % base
        
        # Apply Bitwise XOR between the encrypted byte and the generated number
        result_bytes[j] = encrypted_data[j] ^ (x % 256)
        
    try:
        # Convert the decrypted byte array to plaintext (JSON String)
        return result_bytes.decode('utf-8')
    except Exception as e:
        print(f"{TAG} ERROR: Encoding error while decrypting LCG packet:", e)
        return None

async def process_client_command(ws, plaintext):
    """
    Business logic handler for incoming JSON messages from Flutter.
    """
    try:
        payload = json.loads(plaintext)
        action = payload.get("action")
        
        # CASE 1: Initial Handshake where the App registers the custom meter name
        if action == "set_name":
            new_name = payload.get("device_name")
            if new_name:
                print(f"{TAG} Rename request received. New name: '{new_name}'")
                
                # Atomically save to local Flash storage (config.json)
                config_manager.save_config_atomic(device_name=new_name)
                
                # Dynamically hot-mutate the mDNS
                init_or_update_mdns(new_name)
                
                # Send technical confirmation response
                await ws.send(json.dumps({"status": "success", "message": "Name updated, mDNS active"}))
                
        # CASE 2: On-demand request for the current gas percentage
        elif action == "get_telemetry":
            response = {
                "status": "metrics",
                "gas_percentage": sensor_hall.current_gas_percentage,
                "timestamp": utime.ticks_ms()
            }
            await ws.send(json.dumps(response))
            
    except Exception as e:
        print(f"{TAG} Error processing decrypted JSON:", e)

async def handle_websocket_client(reader, writer):
    """
    Low-level asynchronous handler for incoming WebSocket connections.
    Supports receiving binary encrypted payloads.
    """
    print(f"{TAG} New WebSocket connection established from the Flutter app.")
    
    # Fixed test parameters coupled to your sockets.cpp file (Must match Flutter)
    # In production, these parameters can derive from a key exchange based on the public key
    lcg_params = {
        "x": 123456,  # Initialized seed (Seed + Password)
        "A": 20011,   # Next prime from the sockets.cpp example
        "B": 12345,
        "BASE": 65536
    }
    
    try:
        while True:
            # Read the frame size or the raw buffer from the local socket
            line = await reader.read(1024)
            if not line:
                break  # Clean client disconnection
                
            # Identify if it is a valid WebSocket frame (Useful Payload Extraction)
            # Note: If using Microdot_WebSocket, this byte processing simplifies to:
            # encrypted_data = await ws.recv()
            
            # Assuming you receive the raw encrypted bytes over the binary channel:
            decrypted_text = decode_lcg(line, lcg_params)
            
            if decrypted_text:
                print(f"{TAG} LCG Message Successfully Decrypted: {decrypted_text}")
                # Execute command logic
                # Inject a mock 'ws' object to simulate the response
                class WS_Wrapper:
                    async def send(self, msg):
                        writer.write(msg.encode('utf-8'))
                        await writer.drain()
                
                await process_client_command(WS_Wrapper(), decrypted_text)
                
    except Exception as socket_error:
        print(f"{TAG} Client connection finalized or interrupted:", socket_error)
    finally:
        writer.close()
        await writer.wait_closed()
        print(f"{TAG} Sockets atomically released.")

async def start_websocket_server():
    """
    Launches the local WebSocket server daemon on port 8765.
    Configures the initial mDNS name before opening the network gates.
    """
    # 1. Determine the domain name. If empty in config.json, use the generic factory default
    initial_name = boot.device_name if boot.device_name else "gas-device"
    print(f"{TAG} Configuring initial mDNS infrastructure...")
    init_or_update_mdns(initial_name)
    
    # 2. Initialize the cooperative async server socket
    print(f"{TAG} Opening local WebSocket server on port 8765...")
    try:
        server = await uasyncio.start_server(handle_websocket_client, "0.0.0.0", 8765)
        print(f"{TAG} Server successfully online.")
        
        # Keep the task alive indefinitely in the scheduler
        while True