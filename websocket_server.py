import json
import uasyncio # type: ignore
import network # type: ignore
import hashlib
import ubinascii # type: ignore
import urequests # type: ignore

# Architecture modules
import boot
import config_manager
import sensor_hall

TAG = "[WS_SERVER]"

def init_or_update_mdns(domain_name):
    """
    Registers or updates the mDNS domain name on the local network using native network tools.
    If it's the first time, it will use 'metrigas', otherwise, the user's custom name.
    """
    try:
        # Format the name cleanly (mDNS protocol drops spaces and underscores)
        clean_name = domain_name.lower().replace(" ", "-").replace("_", "-")

        # MicroPython standard way to set global network identity (v1.20+)
        network.hostname(clean_name)
        print(f"{TAG} mDNS Active. Device locally accessible at: http://{clean_name}.local")
    except Exception as e:
        print(f"{TAG} Warning when configuring mDNS hostname:", e)

def check_internet_lookup():
    """
    Fast verification of actual Internet (WAN) connectivity.
    Opens an ephemeral UDP socket to Google's public DNS without blocking the event loop.
    """
    try:
        print(f"{TAG} Checking WAN link status...")
        response = urequests.get("http://clients3.google.com/generate_204", timeout=1.5)
        if response.status_code == 204:
            response.close()
            return True
            
        response.close()
        print(f"{TAG} Internet connection lost.")
        return False
    except Exception as e:
        print(f"{TAG} Internet connection lost. Error: {e}")
        return False # Internet Loss (Módem colgado o sin saldo)

def decode_lcg(encrypted_data, initial_params):
    """
    Decrypts a block of bytes using a Linear Congruential Generator (single cycle).
    """
    # Unpack congruential generator parameters
    x = initial_params[0]
    A = initial_params[1]
    B = initial_params[2]
    base = initial_params[3]

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
        action_data = payload.get("action")
        
        # Extract the main action whether it comes as a string or a list
        action = action_data[0] if isinstance(action_data, list) else action_data
        
        # CASE 1: BAPTISM / INITIAL CONNECTION
        if action == "set_name":
            # Extract the meter name from the array
            new_name = action_data[1]
            set_id = action_data[2]
            print(f"{TAG} Rename request received. New name: '{new_name}'")
            
            # Atomically save to local Flash storage (config.json)
            if config_manager.save_config_atomic(device_name=new_name, meter_id=set_id):
                # Dynamically hot-mutate the mDNS
                init_or_update_mdns(new_name)
                response = {"status": ["ok", "mDNS_mutated"]}
                await ws.send(json.dumps(response))
                
        # CASE 2: PREMIUM UPGRADE
        elif action == "set_premium":
            print(f"{TAG} Premium update command received.")
            
            # Atomically save to local Flash storage (config.json)
            if config_manager.save_config_atomic(is_premium = True):
                response = {"status": ["ok", "premium_flag_true"]}
                await ws.send(json.dumps(response))

        # CASE 3: OBTAIN PERCENTAGE (REQUEST DEMAND)
        elif action == "get_percentage":
            print(f"{TAG} On-demand telemetry request received.")
            
            # Perform a filtered read of the magnetic stripe and save it as a list.
            percentage = [sensor_hall.get_gas_percentage()]
            
            # Only validate the status of the outdoor modem if the user has a RAM premium subscription.
            if boot.is_premium:
                print(f"{TAG} Premium device. Checking WAN link status...")
                # If check_internet_lookup() returns False, then internet_lost is True
                if not check_internet_lookup():
                    percentage.append("internet_lost")
            
            # Formulate a unified response
            response = {"status": percentage}
            await ws.send(json.dumps(response))
            
        # CASE 4: FACTORY RESET
        elif action == "reset":
            print(f"{TAG} Critical Alert: Full Factory Wipe Command.")
            response = {"status": ["ok", "factory_reset_initiated"]}
            await ws.send(json.dumps(response))
            
            # Allow a brief asynchronous pause to ensure the TCP buffer sends the JSON to the mobile phone.
            await uasyncio.sleep_ms(800)
            
            config_manager.force_factory_reset()

    except Exception as e:
        print(f"{TAG} Syntactic parsing error in the received JSON:", e)

async def handle_websocket_client(reader, writer):
    """
    Synchronous TCP byte stream handler for the WebSocket channel.
    """
    print(f"{TAG} TCP communication channel linked from Flutter. Awaiting encrypted JSON messages...")
    
    # Wired, fixed, and static LCG key for symmetric synchronization with Flutter.
    lcg_params = [123456, 20011, 12345, 65536] # x, A, B, BASE
    
    class WS_Wrapper:
        """"
        Minimalist wrapper to emulate clean socket programming.
        """
        async def send(self, msg):
            payload = msg.encode('utf-8')
            payload_len = len(payload)
            
            header = bytearray()
            #0x81 -> FIN bit set + Opcode 0x1 (Plain text)
            header.append(0x81)
            
            # Construct the header size for the server according to RFC 6455.
            if payload_len < 126:
                header.append(payload_len)
            elif payload_len < 65536:
                header.append(126)
                header.append((payload_len >> 8) & 0xFF)
                header.append(payload_len & 0xFF)
            
            writer.write(header + payload)
            await writer.drain()

    try:
        # Read the initial opening handshake
        line = await reader.read(1024)
        if not line:
            return # The client closed the screen or turned off the phone (TCP sends an empty buffer).
        
        # If we detect that it is the initial HTTP handshake for the WebSocket
        if b"Upgrade: websocket" in line:
            # We need to extract the mandatory security key sent by the client.
            raw_header = line.decode('utf-8', 'ignore')
            ws_key = ""
            for header_line in raw_header.split("\r\n"):
                if header_line.startswith("Sec-WebSocket-Key:"):
                    ws_key = header_line.split(":")[1].strip()
                    break

            if ws_key:
                # The WebSocket protocol requires responding with a specific SHA-1 hash.
                MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                accept_sha1 = hashlib.sha1((ws_key + MAGIC_GUID).encode()).digest()
                accept_b64 = ubinascii.b2a_base64(accept_sha1).decode().strip()
                
                # We inform the client that we agree to upgrade the connection to WebSocket.
                response_handshake = (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept_b64}\r\n\r\n"
                )
                writer.write(response_handshake.encode())
                await writer.drain()
                print(f"{TAG} HTTP handshake completed. Official WebSocket channel established.")
            else:
                print(f"{TAG} Error: The Sec-WebSocket-Key header was not found.")
                return

        # Enter the eternal loop to receive your payloads encrypted with the LCG.
        while True:
            line = await reader.read(1024)
            if not line:
                break

            # Validate that the packet is long enough to contain a valid header.
            if len(line) < 2:
                continue
                
            # Extract information from the WebSocket frame
            opcode = line[0] & 0x0F
            is_masked = line[1] & 0x80
            payload_len = line[1] & 0x7F
            
            # PING CONTROL: If it is a control frame (Ping = 0x9, Close = 0x8), we respond quickly.
            if opcode == 0x09: # Ping
                # We automatically respond with a Pong (0x8A) to keep the channel alive.
                writer.write(b'\x8a\x00')
                await writer.drain()
                continue
            elif opcode == 0x08: # Close
                break
                
            # Determine where the mask and data start based on the payload size
            # For short JSONs (< 126 bytes), the standard header with mask is 6 bytes
            if payload_len < 126:
                mask_start = 2
                data_start = 6
            else:
                # If the JSON would measure more than 126 bytes (extended configuration case)
                mask_start = 4
                data_start = 8

            # Extract the actual data and unmask it according to the RFC 6455 standard
            if is_masked:
                masks = line[mask_start:data_start]
                raw_payload = line[data_start:data_start + payload_len]
                
                # XOR operation for WebSocket unmasking
                unmasked_bytes = bytearray(len(raw_payload))
                for i in range(len(raw_payload)):
                    unmasked_bytes[i] = raw_payload[i] ^ masks[i % 4]
                
                actual_data = unmasked_bytes
            else:
                actual_data = line[data_start:data_start + payload_len]

            # Assuming you receive the raw encrypted bytes over the binary channel:
            decrypted_text = decode_lcg(actual_data, lcg_params)
            if decrypted_text:
                print(f"{TAG} LCG Message Successfully Decrypted: {decrypted_text}")
                await process_client_command(WS_Wrapper(), decrypted_text)
                
    except Exception as socket_error:
        print(f"{TAG} Client connection finalized or interrupted:", socket_error)
    finally:
        writer.close()
        await writer.wait_closed()
        print(f"{TAG} Socket resources released atomically in RAM.")

async def start_websocket_server():
    """
    Launches the local WebSocket server daemon on port 8765.
    Configures the initial mDNS name before opening the network gates.
    """
    # Determine the domain name. If empty in config.json, use the generic factory default
    initial_name = boot.device_name
    print(f"{TAG} Configuring initial mDNS infrastructure...")
    init_or_update_mdns(initial_name)
    
    #Initialize the cooperative async server socket
    print(f"{TAG} Opening local WebSocket server on port 8765...")
    try:
        server = await uasyncio.start_server(handle_websocket_client, "0.0.0.0", 8765)
        print(f"{TAG} Server successfully online.")
        
        #Keep the task alive indefinitely in the scheduler
        while True:
            await uasyncio.sleep(3600)
    except Exception as e:
        print(f"{TAG} CRITICAL ERROR: Could not mount the local server:", e)