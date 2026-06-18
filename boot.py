import machine
import network
import json
import os
import utime

# Robustness configuration for industrial/commercial environments
CONFIG_FILE = "config.json"
WIFI_TIMEOUT_MS = 8000  # Strict limit in milliseconds

# Global shared flags to be read and interpreted by main.py
wifi_connected = False
force_pairing = False
current_credentials = {"ssid": "", "password": ""}

def load_config():
    global force_pairing, current_credentials
    try:
        if CONFIG_FILE in os.listdir():
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                if "ssid" in data and "password" in data:
                    current_credentials["ssid"] = data["ssid"]
                    current_credentials["password"] = data["password"]
                    return True
        print("[BOOT] Configuration file non-existent or incomplete.")
    except Exception as e:
        # In production, if the file is corrupt (e.g., power outage mid-write),
        # we catch the error to prevent the ESP32 from entering an infinite reboot loop.
        print("[BOOT] Error reading config.json (possible corruption):", e)
    
    force_pairing = True
    return False

def check_and_connect_wifi(ssid, password, timeout):
    global wifi_connected
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if wlan.isconnected():
        wifi_connected = True
        return True
        
    print("[BOOT] Attempting Wi-Fi connection to:", ssid)
    wlan.connect(ssid, password)
    
    start_time = utime.ticks_ms()
    while not wlan.isconnected():
        # Native time management in microcontrollers (prevents clock overflows)
        if utime.ticks_diff(utime.ticks_ms(), start_time) > timeout:
            print("[BOOT] Network timeout reached. Connection status failed.")
            wifi_connected = False
            return False
        utime.sleep_ms(50)
        
    print("[BOOT] Wi-Fi successfully connected! IP:", wlan.ifconfig()[0])
    wifi_connected = True
    return True

# --- BOOT STARTUP FLOW ---
print("[BOOT] Initializing minimal subsystems...")
if load_config():
    check_and_connect_wifi(current_credentials["ssid"], current_credentials["password"], WIFI_TIMEOUT_MS)
else:
    print("[BOOT] Skipping network attempts. Moving directly to main.py for Pairing.")