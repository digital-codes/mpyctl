import sys
import time
from  machine import Pin,I2C

# pins for stick-c plus
# 26 is next to 5Vout, 0 is next to Batt
# Atom lite/mx pins: 22 (scl),19 (sda)
# Atom S3 pins: 5(scl), 6 (sda)
i2c = I2C(0,scl=Pin(22),sda=Pin(19),freq=400000)
devs = i2c.scan()
print("Devs:",devs)

for i in range(4):
    i2c.writeto(0x38,bytes([i,0]))
    time.sleep(.11)

time.sleep(1)

dir = -1
for i in range(4):
    i2c.writeto(0x38,bytes([i,127 + (dir)*80]))
    time.sleep(1)

i2c.writeto(0x38,bytes([0x10,0]))
time.sleep(1)
i2c.writeto(0x38,bytes([0x10,50]))
time.sleep(1)
i2c.writeto(0x38,bytes([0x10,0]))

dir = 1    
for i in range(4):
    i2c.writeto(0x38,bytes([i,127 + (dir)*80]))
    time.sleep(1)
    
time.sleep(1)
for i in range(4):
    i2c.writeto(0x38,bytes([i,0]))
    time.sleep(.11)

