import sys
import time
from  machine import Pin,I2C
import neopixel

import mpu6886



# pins for mx atom
# Atom mx grove pins: 26 (scl),32 (sda)
# Atom mx internal i2c: 21 (scl), 25 (sda)
# internal imu address: 104 = 0x68
i2c = I2C(0,scl=Pin(21),sda=Pin(25),freq=400000)
devs = i2c.scan()
print("Devs:",devs)

imu = mpu6886.MPU6886(i2c)

p = Pin(27)
RGB = neopixel.NeoPixel(p,25)

def rgbFill(color):
    global RGB
    if RGB == None:
        return
    RGB.fill(color)
    RGB.write()


def find_abs_max_and_sign_index(a, b, c):
    # List of values to compare
    values = [a, b, c]
    
    # Calculate the absolute values and find the index of the max
    abs_values = [abs(val) for val in values]
    max_index = abs_values.index(max(abs_values))
    max_val = abs(values[max_index])

    # Determine the sign of the maximum absolute value
    if max_val > 0:
        sign = 1
    elif max_val < 0:
        sign = -1
    else:
        sign = 0

    return max_val, sign, max_index

while True:
    acc = imu.acceleration
    #print(acc)
    #print(imu.gyro)
    m,s,i = find_abs_max_and_sign_index(*acc)
    #print(m,s,i)
    if m > 2:
        if i == 0:
            rgbFill((255,0,0))
        elif i == 1:    
            rgbFill((0,255,0))  
        else:    
            rgbFill((0,0,255))
    else:
        rgbFill((255,255,255))   
                
    # print(imu.temperature)
    time.sleep(.04)

