import network
import uasyncio 
import utime
import boot

TAG = "[NETWORK]"

async def attempt_silent_reconnection():
    """
    Triggers a non-blocking background reconnection attempt using cached credentials.
    Yields control to the asyncio scheduler to prevent halting other system modules.
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # Early escape if the link layer managed to auto-recover on its own
    if wlan.isconnected():
        return True
        
    target_ssid = boot.current_credentials["ssid"]
    target_password = boot.current_credentials["password"]
    
    if not target_ssid:
        print(f"{TAG} Aborting silent reconnection: Cache memory contains empty credentials.")
        return False
        
    print(f"{TAG} Launching background link reconnection attempt to Target SSID: {target_ssid}")
    wlan.connect(target_ssid, target_password)
    
    # Allow the Wi-Fi radio stack a brief asynchronous window to resolve the link state
    # We do not block with a tight while loop; we wait cooperatively
    await uasyncio.sleep(5)
    
    if wlan.isconnected():
        print(f"{TAG} Silent background connection recovered successfully. Local IP: {wlan.ifconfig()[0]}")
        boot.wifi_connected = True
        return True
    else:
        print(f"{TAG} Background connection handshake pending. Radio stack will retry on next cycle.")
        return False

async def test_new_credentials(ssid, password):
    """
    Validates a new set of credentials received via BLE rescue server.
    Does not write to flash; only verifies if the router grants an IP address.
    """
    print(f"{TAG} Isolating interface to test incoming credentials for SSID: {ssid}")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # Gracefully disconnect current station layer to perform a clean diagnostic test
    if wlan.isconnected():
        wlan.disconnect()
        await uasyncio.sleep_ms(500)
        
    wlan.connect(ssid, password)
    
    # Bounded polling loop that yields control to the asynchronous engine
    start_time = utime.ticks_ms()
    test_timeout_ms = boot.WIFI_TIMEOUT_MS
    
    while not wlan.isconnected():
        # Evaluate time delta using signed subtraction to mitigate clock overflow bugs
        if utime.ticks_diff(utime.ticks_ms(), start_time) > test_timeout_ms:
            print(f"{TAG} Verification failed: Network connection timed out with provided BLE parameters.")
            
            # Safe Fallback: Attempt to revert connection back to previous known working parameters in RAM
            if boot.current_credentials["ssid"]:
                print(f"{TAG} Rolling back radio parameters to baseline credentials.")
                wlan.connect(boot.current_credentials["ssid"], boot.current_credentials["password"])
            return False
            
        await uasyncio.sleep_ms(100)
        
    print(f"{TAG} Verification succeeded! Incoming parameters resolved to Local IP: {wlan.ifconfig()[0]}")
    boot.wifi_connected = True
    return True