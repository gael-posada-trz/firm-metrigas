import utime
import uasyncio
import network

# System modules hierarchy (Only using the 4 completed files)
import boot
import config_manager
import network_manager
import ble_manager

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

async def sensor_polling_mock_task():
    """
    Temporary mock task replacing sensor_hall to simulate system loop activity.
    """
    while True:
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            print(f"{TAG} [MOCK SENSOR] System alive. Network verified. (Simulated polling loop).")
        else:
            print(f"{TAG} [MOCK SENSOR] System alive. Network disconnected.")
        await uasyncio.sleep(20)  # Pulse every 20 seconds

async def main_orchestrator():
    """
    Main asynchronous coordinator for the production firmware lifecycle state machine.
    """
    print(f"{TAG} Bootstrapping system modules setup...")
    
    # PHASE 1: Initial Provisioning diagnostics evaluation derived from boot.py
    if boot.force_pairing or not boot.wifi_connected:
        print(f"{TAG} Configuration missing or unreachable. Entering blocking BLE onboarding mode.")
        # Blocks sequential execution until Flutter sends initial "SSID,PASSWORD" packet via BLE
        await ble_manager.run_blocking_provisioning()
    
    # PHASE 2: Hardware Core Subsystems Activation
    wlan = network.WLAN(network.STA_IF)
    local_ip = wlan.ifconfig()[0] if wlan.isconnected() else "0.0.0.0"
    
    print(f"{TAG} Network interface state verified. Registering long-running asynchronous Firmware core tasks.")
    print(f"{TAG} Current Active Local IP: {local_ip}")
    
    # Concurrent core runtime tasks under the same uasyncio cooperative loop architecture
    uasyncio.create_task(wifi_maintenance_task())
    uasyncio.create_task(sensor_polling_mock_task())  # Keeps the scheduler doing something safe
    
    # PHASE 3: Loop Keep-Alive (Replaces the WebSocket server during early testing)
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
