import time
from machine import Pin
from machine import I2C

from mx import rgbsense

scl = Pin(32,Pin.OUT)
sda = Pin(26)
i2c = I2C(0,scl=scl,sda=sda,freq=400000)
i2c.scan()

sensor = rgbsense.TCS34725(i2c)
print(sensor.read())

