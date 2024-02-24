# demo for catch unit with atom motion base
# connect to servo port 1

import sys
import time
from  machine import Pin,I2C
from neopixel import NeoPixel

np = NeoPixel(Pin(27,Pin.OUT), 25) # led driver
for i in range(25):
    np[i] = (0,0,0)
np[2] = (10,10,10) # set pixel#2 to white
np.write()              # write data to all pixels


i2c = I2C(0,scl=Pin(21),sda=Pin(25),freq=400000)
devs = i2c.scan()
print("Devices:",devs)
# motion base should be at 0x38
if not 0x38 in devs:
    print("No motion base present")
    sys.exit()

# servo 1 angle is at address 0
port = 0
limits = [45,88]
# in interactive mode make sure to not exceed limits

for i in range(10):
    np[2] = (0,10,0) # set pixel#2 
    np.write()              # write data to all pixels
    d = bytes([port,limits[0]])
    i2c.writeto(0x38,d)
    time.sleep(1)
    np[2] = (10,0,0) # set pixel#2 
    np.write()              # write data to all pixels
    d = bytes([port,limits[1]])
    i2c.writeto(0x38,d)
    time.sleep(1)

np[2] = (10,10,10) 
np.write()         
