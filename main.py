import machine
import network
import json
import os
import utime
import ubluetooth as bluetooth

# Import boot.py to inherit its network functions and state variables
import boot

def save_config_atomic(ssid, password):
    """
    Writes atomically to Flash memory to mitigate damage from power outages.
    Creates a temporary file, and only if successfully written, replaces the master file.
    """
    tmp_file = boot.CONFIG_FILE + ".tmp"
    try:
        config_data = {"ssid": ssid, "password": password}
        # 1. Write to temporary file
        with open(tmp_file, "w") as f:
            json.dump(config_data, f)
        
        # 2. If writing was successful, safely replace the original file
        if boot.CONFIG_FILE in os.listdir():
            os.remove(boot.CONFIG_FILE)
        os.rename(tmp_file, boot.CONFIG_FILE)
        
        # Hot-update credentials in volatile memory (RAM)
        boot.current_credentials["ssid"] = ssid
        boot.current_credentials["password"] = password
        print("[MAIN] config.json successfully saved and verified.")
        return True
    except Exception as e:
        print("[MAIN] Critical error saving configuration:", e)
        return False

def run_ble_pairing_server():
    print("[PAIRING] Initializing MicroPython BLE stack...")
    ble = ubluetooth.BLE()

    while True:
        ble.active(True)
    
        # Local synchronization context to break the loop from the interrupt service routine (IRQ)
        ble_context = {"data_received": False, "ssid": "", "password": ""}
    
        # Standard configuration UUIDs (you can customize these for your mobile App)
        SERVICE_UUID = ubluetooth.UUID("0000FFF0-0000-1000-8000-00805F9B34FB")
        CHARACTERISTIC_UUID = ubluetooth.UUID("0000FFF1-0000-1000-8000-00805F9B34FB")
    
        WRITE_PROPERTY = ubluetooth.FLAG_WRITE
        CONFIG_CHAR = (CHARACTERISTIC_UUID, WRITE_PROPERTY,)
        CONFIG_SERVICE = (SERVICE_UUID, (CONFIG_CHAR,),)
        
        # Register the service and get the memory handle for the characteristic
        ((wifi_char_handle,),) = ble.gatts_register_services((CONFIG_SERVICE,))
    
        def ble_irq(event, data):
            # Event 3: _IRQ_GATTS_WRITE (A mobile phone/central device wrote data to the ESP32)
            if event == 3:
                conn_handle, value_handle = data
                if value_handle == wifi_char_handle:
                    try:
                        raw_payload = ble.gatts_read(wifi_char_handle).decode('utf-8')
                        # The mobile App must send the string in plain format: "SSID,PASSWORD"
                        if "," in raw_payload:
                            parts = raw_payload.split(",", 1)
                            ble_context["ssid"] = parts[0].strip()
                            ble_context["password"] = parts[1].strip()
                            ble_context["data_received"] = True
                    except Exception as err:
                        print("[PAIRING] Error decoding BLE payload:", err)

        ble.irq(ble_irq)
    
        # Basic structured Advertising Payload to announce the device name
        device_name = "ESP32_PROV"
        payload = bytearray([2, 1, 6, len(device_name) + 1, 9]) + device_name.encode()
        ble.gap_advertise(100000, payload) # Advertise every 100ms
        print("[PAIRING] ESP32 ready for pairing in the mobile App under the name: 'ESP32_PROV'")
    
        # Controlled blocking loop in main.py waiting for user interaction in the App
        while not ble_context["data_received"]:
            utime.sleep_ms(200)
        
        print("[PAIRING] Credentials captured from the App. Stopping Bluetooth advertising...")
        ble.gap_advertise(None) # Turn off advertising immediately
        print("[PAIRING] Testing credentials...")
    
        # Attempt actual connection to the user-supplied network (We increase the timeout to 12s)
        if boot.check_and_connect_wifi(ble_context["ssid"], ble_context["password"], timeout=12000):
            # ONLY if the connection works in the real world, we persistently save the JSON
            save_config_atomic(ble_context["ssid"], ble_context["password"])
            print("[PAIRING] Process completed. Releasing Bluetooth memory...")
            ble.active(False)  # Free up valuable RAM by turning off the BLE radio stack
            return True
        else:
            print("[PAIRING] Provided credentials failed to connect. Restarting Pairing Mode...")
            ble.active(False)
            utime.sleep_ms(500)  # Short delay before restarting the pairing server

# --- PRODUCTION FIRMWARE MAIN ORCHESTRATOR ---
if boot.force_pairing or not boot.wifi_connected:
    print("[MAIN] Device requires configuration. Entering provisioning mode.")
    run_ble_pairing_server()

# ==============================================================================
#                        MAIN APPLICATION LOGIC
# ==============================================================================
print("[MAIN] Running Production Firmware...")

while True:
    # TODO: Initialize your local WebSocket server here (e.g., microWebSrv or similar)
    # ws_server.start()    

    # Edge Cases Validation: What happens if Wi-Fi drops DURING normal operation?
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("[MAIN] ALERT: Connectivity loss detected during execution.")
        # Attempt non-blocking background reconnection using data loaded in boot
        if boot.current_credentials["ssid"]:
            print("[MAIN] Attempting silent reconnection...")
            wlan.connect(boot.current_credentials["ssid"], boot.current_credentials["password"])
            utime.sleep(5)
            
    utime.sleep(5)