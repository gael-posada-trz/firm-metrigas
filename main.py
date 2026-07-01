import utime # type: ignore
import uasyncio # type: ignore
import network# type: ignore
from machine import Pin # type: ignore

# Architecture modules
import boot
import network_manager
import ble_manager
import websocket_server
import api_client
import sensor_hall

TAG = "[MAIN]"

async def wifi_maintenance_task():
    """
    Background task to monitor Wi-Fi health and perform silent reconnections.
    Runs in parallel with the BLE rescue server if a long-term drop occurs.
    """
    while True:
        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            print(f"{TAG} ALERT: Connectivity loss detected during runtime execution.")
            
            try:
                wlan.active(False)
                await uasyncio.sleep_ms(100)
                wlan.active(True)
            except:
                pass # Safe pass if it's already in an atomic lock

            # 1. Trigger non-blocking silent background reconnection attempt
            await network_manager.attempt_silent_reconnection()
            
            # 2. Activate BLE rescue server concurrently so user can update credentials if needed
            if not ble_manager.is_server_running():
                print(f"{TAG} Launching background BLE rescue stack as a fail-safe mechanism.")
                uasyncio.create_task(ble_manager.start_rescue_server())
        else:
            # If Wi-Fi is back online, gracefully shut down BLE stack to preserve critical heap RAM
            if ble_manager.is_server_running():
                print(f"{TAG} Wi-Fi recovered successfully. Disabling BLE rescue stack to free memory.")
                ble_manager.stop_rescue_server()
                
        await uasyncio.sleep(10)  # Check network interface health every 10 seconds

async def main_orchestrator():
    """
    Main asynchronous coordinator for the production firmware lifecycle state machine.
    Distinguishes between first-time factory setup and runtime connectivity drops.
    """
    print(f"{TAG} Bootstrapping system modules setup...")
    
    # Check if the cache contains actual credentials from a valid config.json
    has_stored_credentials = bool(boot.ssid)
    
    # PHASE 1: Initial Provisioning diagnostics evaluation
    # ONLY enter blocking mode if force_pairing is True OR it is a clean factory device (no SSID cached)
    if boot.force_pairing or not has_stored_credentials:
        print(f"{TAG} Critical First-Time Onboarding: No cached network profile detected.")
        print(f"{TAG} Entering blocking BLE onboarding mode for factory setup.")
        # Blocks sequential execution until Flutter sends initial "SSID,PASSWORD"
        await ble_manager.run_blocking_provisioning()
    
    else:
        # SCENARIO REGISTERED: The device has a valid config.json, but Wi-Fi failed during boot.py
        if not boot.wifi_connected:
            print(f"{TAG} Baseline profile detected but network link is down.")
            print(f"{TAG} Bypassing blocking setup. System core will initialize concurrently.")
    
    # PHASE 2: Hardware Core Subsystems Activation
    wlan = network.WLAN(network.STA_IF)
    local_ip = wlan.ifconfig()[0] if wlan.isconnected() else "0.0.0.0"
    
    print(f"{TAG} Network interface state verified. Registering long-running asynchronous Firmware core tasks.")
    print(f"{TAG} Current Active Local IP: {local_ip}")
    
    # while True:
    #    print(sensor_hall.get_gas_percentage())

    # Concurrent core runtime tasks under the same uasyncio cooperative loop architecture
    uasyncio.create_task(websocket_server.start_websocket_server())
    uasyncio.create_task(api_client.api_reporting_task())
    uasyncio.create_task(wifi_maintenance_task())
    
    # PHASE 3: Loop Keep-Alive (Will hold the main thread up)
    print(f"{TAG} Infrastructure ready. Entering main test loop...")
    while True:
        await uasyncio.sleep(1)
        
# --- MICROCONTROLLER SUBSYSTEM ENTRY POINT ---
if __name__ == "__main__":
    try:
        # Bind and start the cooperative event scheduling loop
        uasyncio.run(main_orchestrator())
    except Exception as kernel_panic:
        print(f"{TAG} CRITICAL CRASH: Unhandled kernel panic inside the main scheduler:", kernel_panic)
