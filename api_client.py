import urequests # type: ignore
import json # type: ignore
import utime # type: ignore
import uasyncio # type: ignore
import ntptime # type: ignore
import network # type: ignore

# Architecture modules
import boot
import config_manager
import sensor_hall

TAG = "[API_CLIENT]"
INTERVALO_24_HORAS_SEGUNDOS = 24 * 60 * 60
TARGET_URL = "https://tu-api-nestjs.onrender.com/logs" # Set your production endpoint here


def sync_ntp_time():
    """
    Safely synchronizes the ESP32 internal RTC via NTP.
    """
    try:
        ntptime.settime()
        print(f"{TAG} System clock successfully synchronized via NTP.")
        return True
    except Exception as e:
        print(f"{TAG} Warning: NTP synchronization failed (Modem without WAN access): {e}")
        return False

def send_log_to_endpoint(percentage):
    """
    Executes a controlled synchronous POST request to NestJS.
    Returns the HTTP status code or 0 if a network anomaly occurs.
    """
    # Nota: Aquí puedes integrar tu función call_hall() interna o pasar el porcentaje por parámetro
    payload = {
        "currentPercentage": percentage, 
        "meterId": boot.meter_id
    }
    headers = {'Content-Type': 'application/json'}
    try:
        print(f"{TAG} Transmitting 24h telemetry report to API... Payload: {payload}")
        response = urequests.post(TARGET_URL, data=json.dumps(payload), headers=headers, timeout=5)
        status = response.status_code
        response.close()
        return status
    except Exception as e:
        print(f"{TAG} Physical connection error when reporting to external API: {e}")
        return 0

async def api_reporting_daemon_task():
    """
    Cooperative asynchronous background daemon task for WAN reporting control.
    Monitors the target time and handles Premium state degradation.
    """
    print(f"{TAG} Initializing 24-hour reporting asynchronous daemon.")
    
    # Wait until the device has a valid IP before starting core logic
    wlan = network.WLAN(network.STA_IF)
    while not wlan.isconnected():
        await uasyncio.sleep(2)
        
    # First time synchronization attempt
    sync_ntp_time()

    while True:
        try:
            # BUSINESS CONDITION IN RAM: If user is FREE, the task suspends execution
            if not boot.is_premium:
                await uasyncio.sleep(30)
                continue
                
            # If no meter UUID is registered yet, we cannot send valid reports
            if not boot.meter_id:
                print(f"{TAG} Waiting for 'meter_id' allocation from Flutter to report.")
                await uasyncio.sleep(10)
                continue

            current_time = utime.time()
            
            # CASE A: First-time run or target configuration lost due to corruption
            if boot.time_target == 0:
                print(f"{TAG} Configuring first 'time_target' in the device lifecycle.")
                percentage = sensor_hall.get_gas_percentage() # Live hot reading
                
                status_code = send_log_to_endpoint(percentage)
                
                if status_code in [402, 403]:
                    print(f"{TAG} Critical Alert: API rejected credentials ({status_code}). Degrading to FREE.")
                    config_manager.save_config_atomic(is_premium=False)
                    continue
                
                # Calculate and atomically save the next 24-hour target goal
                new_target = current_time + INTERVAL_24_HOURS_SECONDS
                config_manager.save_config_atomic(time_target=new_target)

            # CASE B: Target time has expired (Normal flow or power outage compensation)
            elif current_time >= boot.time_target:
                # Try resyncing time before reporting in case the chip's oscillator drifted
                sync_ntp_time()
                
                # Evaluate if we are returning from a prolonged power outage
                if (current_time - boot.time_target) > (INTERVAL_24_HOURS_SECONDS * 2):
                    print(f"{TAG} [!] Prolonged power outage detected. Compensating delayed report...")
                
                percentage = sensor_hall.get_gas_percentage()
                status_code = send_log_to_endpoint(percentage)
                
                if status_code in [402, 403]:
                    print(f"{TAG} Critical Alert: API rejected credentials ({status_code}). Degrading to FREE.")
                    config_manager.save_config_atomic(is_premium=False)
                    continue
                
                # Calculate next 24h jump. If power outage lasted for days, advance up to the present.
                next_target = boot.time_target + INTERVAL_24_HOURS_SECONDS
                while next_target <= utime.time():
                    next_target += INTERVAL_24_HOURS_SECONDS
                    
                config_manager.save_config_atomic(time_target=next_target)
                
        except Exception as task_error:
            print(f"{TAG} Anomaly caught in the API daemon loop:", task_error)
            
        # Check the processor clock every 5 seconds cooperatively (Without blocking WebSockets)
        await uasyncio.sleep(5)