import uasyncio # type: ignore
from machine import ADC, Pin # type: ignore
import utime # type: ignore

TAG = "[SENSOR]"

# Calibration parameters derived from hardware staging profiles
SENSOR_PIN = 1
EMPTY_BITS = 1200
FULL_BITS = 3100

# Global runtime state variable accessible by the WebSocket and main architecture
current_gas_percentage = 0

# Initialize and lock the ADC hardware peripheral globally
_adc = ADC(Pin(SENSOR_PIN))
_adc.atten(ADC.ATTN_11DB)  # Full range configuration up to ~3.3V

def _map_value(value, in_min, in_max, out_min, out_max):
    """Replicates Arduino's map() function using floating-point math."""
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def _constrain_value(value, min_val, max_val):
    """Replicates Arduino's constrain() function to guarantee boundaries."""
    return max(min_val, min(value, max_val))

def read_filtered_adc(samples=10):
    """
    Takes multiple native samples and returns the average.
    Shifts default 16-bit reads to 12-bit native S3 resolution (0-4095).
    Mitigates high-frequency ripple noise caused by RF radio bursts.
    """
    total = 0
    for _ in range(samples):
        total += _adc.read_u16() >> 4
        utime.sleep_ms(5)  # Safe hardware settling delay between conversion windows
    return int(total / samples)

def get_gas_percentage():
    """
    Executes a mathematical linear scaling transformation over raw hardware bits.
    Guarantees a clean, non-overflowed output strictly bounded between 0% and 100%.
    """
    try:
        raw_reading = read_filtered_adc()
        
        # Apply floating-point map and force saturation boundaries
        mapped_percentage = _map_value(raw_reading, EMPTY_BITS, FULL_BITS, 0, 100)
        final_percentage = int(_constrain_value(mapped_percentage, 0, 100))
        
        return final_percentage
    except Exception as e:
        print(f"{TAG} ERROR: Calculations failed on ADC scaling transformation:", e)
        return 0

async def sensor_polling_task():
    """
    Long-running asynchronous daemon loop designed for the main scheduler.
    Refreshes the shared global gas capacity state every 20 seconds.
    Yields execution context gracefully to prevent blocking local network sockets.
    """
    global current_gas_percentage
    print(f"{TAG} Initializing Hall sensor telemetry polling engine subsystem.")
    
    while True:
        try:
            # Fetch fresh stable tracking metrics from hardware
            current_gas_percentage = get_gas_percentage()
            print(f"{TAG} Telemetry metrics captured. Current Tank Level: {current_gas_percentage}%")
            
        except Exception as e:
            print(f"{TAG} CRITICAL ERROR: Polling daemon loop encountered an anomaly:", e)
            
        # Asynchronous sleep interval matching system business specifications
        await uasyncio.sleep(20)