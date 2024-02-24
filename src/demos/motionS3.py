import sys
import time
from  machine import Pin,I2C

# i2c pins form motion drive
# Atom lite/mx pins: 21 (scl),15 (sda)
# Atom S3 pins: 39(scl), 38 (sda)
i2c = I2C(0,scl=Pin(39),sda=Pin(38),freq=400000)
devs = i2c.scan()
print("Devs:",devs)


# motors: MG995 is 360° servo
# angle values 45 - 90 - 135 to ports 0,1,2,3
# 90 is stop

# motor values are ports 0x20,0x21
# speed values -127..127
# usable with yellow motors: 90..170 

# grove ports:
# Port-B: Pin 6 (white), Pin 5 (yellow)
# Port-C: Pin 7 (white), Pin 8 (yellow)

# stop all servos
for i in range(4):
    i2c.writeto(0x38,bytes([i,90]))
    time.sleep(.11)

time.sleep(1)

dir = -1
for i in range(4):
    i2c.writeto(0x38,bytes([i,90 + (dir)*int(45/2)]))
    time.sleep(1)

for i in range(4):
    i2c.writeto(0x38,bytes([i,90 + (dir)*45]))
    time.sleep(1)

for i in range(4):
    i2c.writeto(0x38,bytes([i,90]))
    time.sleep(.11)

dir = 1    
for i in range(4):
    i2c.writeto(0x38,bytes([i,90 + int((dir)*45/2)]))
    time.sleep(1)
    
for i in range(4):
    i2c.writeto(0x38,bytes([i,90 + (dir)*45]))
    time.sleep(1)
    
time.sleep(1)
for i in range(4):
    i2c.writeto(0x38,bytes([i,90]))
    time.sleep(.11)

