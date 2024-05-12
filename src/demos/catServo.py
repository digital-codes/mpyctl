from  machine import Pin,I2C,PWM
import time
import sys

# for direct servo without motion:
# duty range 25 .. 125, freq 50
# make sure to have 5V. 3V isn't enough for servo

p = Pin(26,Pin.OUT)
pw = PWM(p,freq=50,duty=75)

a = 25
d = 1
o = 2
while True:
    pw.duty(a)
    if d == 1:
        if a < 125:
            a += o
        else:
            d = 0
            a -= o
    else:
        if a > 25:
            a -= o
        else:
            d = 1
            a += o
    time.sleep(.02) 
            
             
sys.exit()

i2c = I2C(0,scl=Pin(21),sda=Pin(25),freq=400000)
devs = i2c.scan()
print("I2C:",devs)

a = 0
d = 1
o = 4
while True:
    print(a)
    i2c.writeto(0x38,bytes([0,a]))
    if d == 1:
        if a < 180:
            a += o
        else:
            d = 0
            a -= o
    else:
        if a > 0:
            a -= o
        else:
            d = 1
            a += o
    time.sleep(.02) 
            
             
