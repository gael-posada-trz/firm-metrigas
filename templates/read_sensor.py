import utime
from machine import ADC, Pin

def readSensor():
    # Pin connected to the voltage divider output from SS49E OUT (GPIO 1)
    SENSOR_PIN = 1  

    # Configure ADC: 12-bit resolution (0-4095) and full 3.3V range
    adc = ADC(Pin(SENSOR_PIN))
    print(f"[HALL SENSOR] ADC Configuration: {adc}")
    adc.atten(ADC.ATTN_11DB)

    '''def read_filtered_adc(samples=10):
        """Takes multiple samples and returns the average to eliminate USB noise."""
        total = 0
        for _ in range(samples):
            # Convert 16-bit default read to 12-bit native resolution
            total += adc.read_u16() >> 4
            utime.sleep_ms(5)  # Short delay between samples
        return int(total / samples)'''

    def map_value(value, in_min, in_max, out_min, out_max):
        """Replicates Arduino's map() function using floating-point math."""
        return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def constrain_value(value, min_val, max_val):
        """Replicates Arduino's constrain() function."""
        return max(min_val, min(value, max_val))

    
    # Read ADC value: returns between 0 and 4095 on ESP32-S3
    '''raw_reading = read_filtered_adc(samples=10)'''
    raw_reading = adc.read_u16() >> 4 # Shift 16-bit to 12-bit resolution

    # CALIBRATION VALUES (Update these with your real USB-C setup data)
    EMPTY_BITS = 1200  
    FULL_BITS = 3100   

    # Map raw bits to percentage
    tank_percentage = map_value(raw_reading, EMPTY_BITS, FULL_BITS, 0, 100)
    
    # Round to closest integer and constrain values between 0% and 100%
    tank_percentage = int(round(tank_percentage))
    tank_percentage = constrain_value(tank_percentage, 0, 100)

    # Print results to console
    print(f"[HALL SENSOR]Raw Reading (Bits): {raw_reading}  |  Tank Level: {tank_percentage}%")

    # Wait 1 second before the next update
    utime.sleep(1)
