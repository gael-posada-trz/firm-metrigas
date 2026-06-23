import ubluetooth
import uasyncio
import utime
import boot
import config_manager
import network_manager

TAG = "[BLE]"

# Global Bluetooth execution context
_ble = None
_server_running = False
_provisioning_done = False

# Internals for GATT Handles
_handle_char_wifi = None

def is_server_running():
    """Returns the current operational status of the BLE advertising server."""
    return _server_running

def _build_advertising_payload(device_name):
    """
    Assembles a standardized Length-Type-Value (LTV) BLE advertising packet.
    Includes discoverable flags and the local complete hardware name.
    """
    encoded_name = device_name.encode('utf-8')
    # Structure: [Len, Type, Value] -> Flags: General Discoverable, BR/EDR Not Supported
    flags_ltv = bytearray([2, 1, 6])
    # Structure: [Len, Type, Value] -> Complete Local Name
    name_ltv = bytearray([len(encoded_name) + 1, 9]) + encoded_name
    return flags_ltv + name_ltv

def _ble_irq_handler(event, data):
    """
    Hardware Interrupt Service Routine (ISR) callback for BLE events.
    Must execute with absolute speed and minimal allocation.
    """
    global _provisioning_done, _handle_char_wifi
    
    # Event 3: _IRQ_GATTS_WRITE (A central device wrote data to a characteristic)
    if event == 3:
        conn_handle, value_handle = data
        if value_handle == _handle_char_wifi:
            try:
                # Read incoming binary chunk directly from the characteristic buffer
                raw_payload = _ble.gatts_read(_handle_char_wifi).decode('utf-8')
                print(f"{TAG} Raw configuration transmission intercepted over BLE transport layer.")
                
                if "," in raw_payload:
                    # Tokenize string structured as "SSID,PASSWORD"
                    parts = raw_payload.split(",", 1)
                    incoming_ssid = parts[0].strip()
                    incoming_password = parts[1].strip()
                    
                    print(f"{TAG} Processing onboarding parameters for Network Destination: {incoming_ssid}")
                    
                    # Offload validation logic to a synchronous execution context
                    # (Note: IRQs cannot directly await async tasks, main or manager handles execution)
                    _ble_context["ssid"] = incoming_ssid
                    _ble_context["password"] = incoming_password
                    _provisioning_done = True
                    
            except Exception as e:
                print(f"{TAG} ERROR: Exception raised while parsing incoming BLE GATT payload:", e)

# Memory context container to share data back from hardware IRQ to async loops
_ble_context = {"ssid": "", "password": ""}

def _init_ble_stack():
    """Initializes hardware radio peripherals and registers GATT Profiles."""
    global _ble, _handle_char_wifi
    
    _ble = ubluetooth.BLE()
    _ble.active(True)
    _ble.irq(_ble_irq_handler)
    
    # Define primary service UUID and write-only configuration characteristic
    UUID_SERVICE = ubluetooth.UUID("0000FFF0-0000-1000-8000-00805F9B34FB")
    UUID_CHARACTERISTIC = ubluetooth.UUID("0000FFF1-0000-1000-8000-00805F9B34FB")
    
    # Configuration tuple following MicroPython GATTS specification
    CHAR_CONFIG = (UUID_CHARACTERISTIC, ubluetooth.FLAG_WRITE,)
    SERVICE_CONFIG = (UUID_SERVICE, (CHAR_CONFIG,),)
    
    # Register the service in native RAM and save pointer address
    (((_handle_char_wifi,),),) = _ble.gatts_register_services((SERVICE_CONFIG,))

def stop_rescue_server():
    """Gracefully kills advertising loops and tears down the BLE stack to maximize free heap RAM."""
    global _ble, _server_running
    if _ble and _server_running:
        print(f"{TAG} Disabling radio transmission. Releasing hardware resources.")
        _ble.gap_advertise(None)
        _ble.active(False)
        _server_running = False

async def start_rescue_server():
    """Spins up the asynchronous BLE server in the background as a passive fail-safe interface."""
    global _server_running, _provisioning_done
    if _server_running:
        return
        
    print(f"{TAG} Starting background rescue interface. Awaiting connection pulses.")
    _init_ble_stack()
    _server_running = True
    _provisioning_done = False
    
    # Start emitting advertising packets using current runtime name
    payload = _build_advertising_payload(boot.device_name)
    _ble.gap_advertise(100000, payload)  # Interval 100ms
    
    # Monitoring daemon loop
    while _server_running:
        if _provisioning_done:
            print(f"{TAG} New credentials updated via rescue server. Validating access point link status.")
            # We turn off advertising BEFORE validating.
            # This prevents the phone from trying to send something else while we're verifying. 
            _ble.gap_advertise(None)

            # We immediately lower the flag.
            # We've captured the event; we've released the state for future use.
            _provisioning_done = False
            # Verify network connection using the new credentials
            success = await network_manager.test_new_credentials(_ble_context["ssid"], _ble_context["password"])
            if success:
                # Atomically write configuration including existing name/premium states
                config_manager.save_config_atomic(ssid=_ble_context["ssid"], password=_ble_context["password"])
                print(f"{TAG} Onboarding parameters committed to flash. Tearing down rescue subsystem.")
                stop_rescue_server()
                break
            else:
                print(f"{TAG} WARNING: Rescue validation link failed. Resuming advertising pulses.")
                _ble.gap_advertise(100000, payload)
                
        await uasyncio.sleep_ms(250)

async def run_blocking_provisioning():
    """
    Halts sequential system boot up inside main.py until a first-time binding packet 
    is received and verified from Flutter. Necessary for initial factory setup.
    """
    global _provisioning_done, _server_running
    print(f"{TAG} Entering critical first-time device binding routine.")
    
    # We initialize the physical BLE stack once outside the retry loop
    _init_ble_stack()

    while True:
        _server_running = True
        _provisioning_done = False
        
        # Advertise using the generic factory default fallback name ("ESP32_PROV")
        payload = _build_advertising_payload(boot.device_name)
        _ble.gap_advertise(100000, payload)
        
        # Fast polling blocking mechanism
        while not _provisioning_done:
            await asyncio.sleep_ms(200)
            
        print(f"{TAG} Initial transmission capture successful. Testing infrastructure connectivity.")
        _ble.gap_advertise(None)  # Quiet down radio while testing router link
        
        # Force full synchronous check via boot mechanism
        success = boot.check_and_connect_wifi(_ble_context["ssid"], _ble_context["password"], boot.WIFI_TIMEOUT_MS)
        
        if success:
            # Create initial 4-field config payload atomically using placeholders for business logic
            config_manager.save_config_atomic(
                ssid=_ble_context["ssid"], 
                password=_ble_context["password"],
                device_name="ESP32_PROV",
                is_premium=False
            )
            print(f"{TAG} Verification succeeded. Factory onboarding accomplished.")
            stop_rescue_server()
            break #Breaks the infinite loop and continues execution safely
        else:
            print(f"{TAG} ERROR: Factory credentials failed. Resetting state and retrying sequence.")
            stop_rescue_server()
            # Recursive asynchronous restart
            await asyncio.sleep_ms(500)  # Minimal settling delay before turning the radio back on