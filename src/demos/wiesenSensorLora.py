from machine import I2C, ADC
from co2l import CO2LUnit
from colorRgb import TCS3472
import time


# battery adc is on pin 8
bat = ADC(8)
def get_battery_voltage():
    # read battery voltage in volts. battery has a voltage divider of 2:1, so multiply by 2. ADC returns value in range 0-4095 for 0-3.3V, so multiply by 3.3/4095 to get volts
    return bat.read_uv() * 2 / 1000000


i1 = I2C(0,scl=1,sda=2,freq=400000)
i1.scan()
co2 = CO2LUnit(i1)
co2.reinit()
co2.get_serial_number()
#co2.set_start_low_periodic_measurement()

def get_co2():
    co2.set_single_shot_measurement_all()
    # set single shot has built-in wait
    if co2.is_data_ready():
        try:
            gas = co2.co2
            tmp = co2.temperature
            hum = co2.humidity
            return gas, tmp, hum
        except Exception as e:
            print("Error reading CO2 sensor:", e)

    return None, None, None
    
    
i2 = I2C(1,scl=4,sda=3,freq=400000)
i2.scan()
rgb = TCS3472(i2)

def get_rgb():
    rgb.set_active(True)
    time.sleep(0.1)
    rgb.set_integration_time(2.4)
    time.sleep(0.1)
    cols = rgb.get_color_rgb_bytes()
    lux = rgb.get_lux()
    ct = rgb.get_color_temperature()
    rgb.set_active(False)
    return cols, lux, ct

    
if __name__ == "__main__":
    while True:
        print("Battery voltage: {:.2f} V".format(get_battery_voltage()))
        co2_val, temp, rh = get_co2()
        if co2_val is not None:
            print("CO2: {} ppm, Temp: {:.2f} C, RH: {:.2f} %".format(co2_val, temp, rh))
        else:
            print("CO2 data not ready")
        (r, g, b), lux, ct = get_rgb()
        print("RGB: R={}, G={}, B={}".format(r, g, b))
        print("Lux: {:.2f}, Color Temperature: {:.2f}".format(lux, ct))
        time.sleep(5)
        
        