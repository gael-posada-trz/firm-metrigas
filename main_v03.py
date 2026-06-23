import utime
import uasyncio
import network

# System modules hierarchy
import boot
import config_manager
import wifi_manager
import ble_provisioning
import sensor_hall
import premium_reporter
import local_server

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
            await wifi_manager.attempt_silent_reconnection()
            
            # 2. Activate BLE rescue server concurrently so user can update credentials if needed
            if not ble_provisioning.is_server_running():
                print(f"{TAG} Launching background BLE rescue stack as a fail-safe mechanism.")
                uasyncio.create_task(ble_provisioning.start_rescue_server())
        else:
            # If Wi-Fi is back online, gracefully shut down BLE stack to preserve critical heap RAM
            if ble_provisioning.is_server_running():
                print(f"{TAG} Wi-Fi recovered successfully. Disabling BLE rescue stack to free memory.")
                ble_provisioning.stop_rescue_server()
                
        await uasyncio.sleep(10)  # Check network interface health every 10 seconds

async def premium_reporting_task():
    """
    Background task managing the hybrid 24-hour cloud sync reporting loop.
    Captures internet loss exceptions directly from the POST handler to alert the user.
    """
    print(f"{TAG} Initializing Premium clock service.")
    while True:
        # Check time delta using native ticks via the isolated premium_reporter module
        if premium_reporter.is_premium_active and premium_reporter.has_cycle_expired():
            print(f"{TAG} 24-hour cycle reached. Proceeding with REST payload compilation.")
            
            # Extract clean, filtered percentage from the hardware sensor abstraction module
            current_gas_level = sensor_hall.read_sensor_percentage()
            
            # Execute direct HTTP POST request to Railway. Internal try-except catches timeouts or fiber cuts
            success = await premium_reporter.send_daily_report(current_gas_level)
            
            if not success:
                # If it failed due to lack of internet (modem fiber cut), notify Flutter
                print(f"{TAG} REST delivery failed due to network isolation. Dispatching WebSocket warning.")
                # Directly notify the single connected user through the local WebSocket channel
                await local_server.broadcast_message({
                    "event": "internet_loss", 
                    "msg": "Modem connected locally, but no Internet access found. Please check your home internet connection or contact your provider."
                })
                
        await uasyncio.sleep(30)  # Check daily timer ticks differential every 30 seconds

async def main_orchestrator():
    """
    Main asynchronous coordinator for the production firmware lifecycle state machine.
    """
    print(f"{TAG} Bootstrapping system modules setup...")
    
    # PHASE 1: Initial Provisioning diagnostics evaluation derived from boot.py
    if boot.force_pairing or not boot.wifi_connected:
        print(f"{TAG} Configuration missing or unreachable. Entering blocking BLE onboarding mode.")
        # Blocks sequential execution until Flutter sends initial "SSID,PASSWORD" packet via BLE
        await ble_provisioning.run_blocking_provisioning()
    
    # PHASE 2: Hardware Core Subsystems Activation
    wlan = network.WLAN(network.STA_IF)
    local_ip = wlan.ifconfig()[0] if wlan.isconnected() else "0.0.0.0"
    
    print(f"{TAG} Network interface state verified. Registering long-running asynchronous Firmware core tasks.")
    
    # Concurrent core runtime tasks under the same uasyncio cooperative loop architecture
    uasyncio.create_task(wifi_maintenance_task())
    uasyncio.create_task(premium_reporting_task())
    uasyncio.create_task(sensor_hall.sensor_polling_task()) # Polls ADC and streams to app every 20s if open
    
    # PHASE 3: Startup Local WebSocket Infrastructure (Keeps the uasyncio scheduler alive)
    print(f"{TAG} Starting local WebSocket engine listening on port 8765...")
    await local_server.start_websocket_server(local_ip, port=8765)

# --- MICROCONTROLLER SUBSYSTEM ENTRY POINT ---
if __name__ == "__main__":
    try:
        # Bind and start the cooperative event scheduling loop
        uasyncio.run(main_orchestrator())
    except Exception as kernel_panic:
        print(f"{TAG} CRITICAL CRASH: Unhandled kernel panic inside the main scheduler:", kernel_panic)