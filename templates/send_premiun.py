import machine
import network
import json
import os
import utime
import ubluetooth
import boot
# NOTE: urequests and your websockets library must be imported here
# Global application state variables
premium_active = True
timer_24h = utime.ticks_ms()
INTERVAL_24H_MS = 24 * 60 * 60 * 1000 # 24 hours in milliseconds

#helper function to read sensor data (simulate with random for now)


def send_premium_report():
    global premium_active
    print("[API] Starting daily REST report...")
    
    gas_level = 55
    # Replace with real urequests in production
    url = "https://api.your-proyect.railway.app/tanks/report"
    payload = {"gas_level": gas_level, "device_token": "STATIC_DEVICE_TOKEN"}
    #payload = {"gas_level": readSensor(), "device_token": "STATIC_DEVICE_TOKEN"}
    
    try:
        # Petición REST al backend de NestJS
        #response = urequests.post(url, json=payload)
        #status = response.status_code
        #response.close()
        
        status = 200 # Successful simulation
        
        if status in (402, 403):
            print("[API] Subscription inactive/expired. Disabling 24-hour reports.")
            premium_active = False
        else:
            print(f"[API] Daily report sent successfully. Status code: {status}")
    except Exception as e:
        print("[API] Network error in daily report, will retry later:", e)

# --- ORCHESTRATION FLOW ---
if boot.force_pairing or not boot.wifi_connected:
    print("[MAIN] Device requires configuration.")
    run_ble_pairing_server()

print("[MAIN] Running Production Firmware...")

# TODO: Initialize your local WebSockets server here (e.g., microWebSrv or similar)
# ws_server.start()

while True:
    # 1. ON-DEMAND WEB SOCKETS MANAGEMENT
    # Your WebSockets library will run asynchronously or via poll() inside here
    # to send readings every 20 seconds only if the app is open.
    
    # 2. PREMIUM DAILY REPORT VERIFICATION
    if premium_active:
        if utime.ticks_diff(utime.ticks_ms(), timer_24h) >= INTERVAL_24H_MS:
            send_premium_report()
            timer_24h = utime.ticks_ms() # Reset native timer
            
    # 3. CONTROLLED WI-FI RECONNECTION (Network Maintenance)
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected(): 
        print()
