import time
from machine import Pin
from machine import I2C

from mx import tof

scl = Pin(32,Pin.OUT)
sda = Pin(26)
i2c = I2C(0,scl=scl,sda=sda,freq=400000)
i2c.scan()

dist = tof.VL53L0X(i2c)

while True:
    dist.start()
    d = dist.read()
    print(d)
    dist.stop()
    time.sleep(.2)



