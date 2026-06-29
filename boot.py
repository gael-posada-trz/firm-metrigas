import machine  # type: ignore
import network # type: ignore
import json
import os
import utime # type: ignore

TAG = "[BOOT]"

# Robustness configuration for industrial/commercial environments
CONFIG_FILE = "config.json"
WIFI_TIMEOUT_MS = 8000  # Strict limit in milliseconds for fast connection check

# Global shared flags and state variables to be inherited by main.py
wifi_connected = False
force_pairing = False

# Application data context synchronized from Flash to RAM at startup
current_credentials = {"ssid": "", "password": ""}
device_name = "Metrigas"  # Default fallback name for BLE advertising
is_premium = False          # Default fallback status for business logic loops

def load_config():
    """
    Reads the configuration profile from local flash memory.
    Extracts network credentials and persists hardware identity and subscription states.
    """
    global force_pairing, current_credentials, device_name, is_premium
    try:
        if CONFIG_FILE in os.listdir():
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                
                # Structural validation of essential network fields
                if "ssid" in data and "password" in data:
                    current_credentials["ssid"] = data["ssid"]
                    current_credentials["password"] = data["password"]
                    
                    # Safe extraction of application fields with production defaults
                    device_name = data.get("device_name", "Metrigas")
                    is_premium = data.get("is_premium", False)
                    
                    print(f"{TAG} System configuration successfully loaded from Flash storage.")
                    return True
                    
        print(f"{TAG} Profile configuration non-existent or data parameters incomplete.")
    except Exception as e:
        # Prevents infinite hardware reboot loops in production due to partial power loss corruptions
        print(f"{TAG} CRITICAL: Exception caught reading config.json (file might be corrupted):", e)
    
    # Flag main.py to immediately fallback into blocking BLE onboarding routine
    force_pairing = True
    return False

def check_and_connect_wifi(ssid, password, timeout):
    """
    Performs a deterministic, time-bounded fast connection attempt to the wireless access point.
    Returns control rapidly back to the kernel scheduler to prevent hardware stalling.
    """
    global wifi_connected
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # Early escape if the network layer is already bound and up
    if wlan.isconnected():
        wifi_connected = True
        return True
        
    print(f"{TAG} Attempting network connection to Target SSID: {ssid}")
    try:
        wlan.connect(ssid, password)
    except OSError as driver_error:
        print(f"{TAG} CRITICAL WARNING: Driver level anomaly intercepted: {driver_error}")
        print(f"{TAG} Forcing safe fallback: Preserving hardware execution flow toward main.py")
        wifi_connected = False
        return False
    
    start_time = utime.ticks_ms()
    while not wlan.isconnected():
        # Prevent clock overflow errors by evaluating signed time boundaries
        if utime.ticks_diff(utime.ticks_ms(), start_time) > timeout:
            print(f"{TAG} Network timeout reached.  Connection status failed.")
            wifi_connected = False
            return False
        utime.sleep_ms(50)
        
    print(f"{TAG} Network connection established. IP: {wlan.ifconfig()[0]}")
    wifi_connected = True
    return True

# --- BOOT SYSTEM STARTUP TRIGGER ---
print(f"{TAG} Bootstrapping minimal hardware subsystems...")

if load_config():
    # Attempt rapid sync with existing credentials before handing off control to main orchestration
    check_and_connect_wifi(current_credentials["ssid"], current_credentials["password"], WIFI_TIMEOUT_MS)
else:
    print(f"{TAG} Skipping network attempts. Moving directly  to main.py BLE for Pairing.")