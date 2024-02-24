# demo for catch unit with atom motion base
# connect to servo port 1

import sys
import time
from  machine import Pin,I2C


i2c = I2C(0,scl=Pin(39),sda=Pin(38),freq=400000)
devs = i2c.scan()
print("Devices:",devs)
# motion base should be at 0x38
if not 0x38 in devs:
    print("No motion base present")
    sys.exit()

# servo 1 angle is at address 0
port = 0
limits = [60,120]
# in interactive mode make sure to not exceed limits

for i in range(5):
    d = bytes([port,limits[0]])
    i2c.writeto(0x38,d)
    time.sleep(1)
    d = bytes([port,limits[1]])
    i2c.writeto(0x38,d)
    time.sleep(3)

    d = bytes([port,90])
    i2c.writeto(0x38,d)
