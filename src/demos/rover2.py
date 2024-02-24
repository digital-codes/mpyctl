import sys
import time
from  machine import Pin,I2C
from collections import OrderedDict

# pins for stick-c plus
# 26 is next to 5Vout, 0 is next to Batt
# Atom lite/mx pins: 22 (scl),19 (sda)
# Atom S3 pins: 5(scl), 6 (sda)
i2c = I2C(0,scl=Pin(26),sda=Pin(0),freq=400000)
devs = i2c.scan()
print("Devs:",devs)

# stop all wheels
for i in range(4):
    i2c.writeto(0x38,bytes([i,0]))
    time.sleep(.11)

time.sleep(1)

# 2 pattern bits per motor
# fwd: 10, rev: 01, 00,11:stop 
patterns = OrderedDict([
    ("fwd", 0b10101010),
    ("rev", 0b01010101),
    ("left", 0b01101001),
    ("right", 0b10010110),
    ("lfwd", 0b00101000),
    ("rfwd", 0b10000010),
    ("lrev", 0b01000001),
    ("rrev", 0b00010100),
    ("lturn", 0b10011001),
    ("rturn", 0b01100110),
    ("stop", 0b00000000)
])

def motCtl(ctl):
    for i in range(4):
        mctl = (ctl >> 2*i) & 3
        print(mctl)
        if mctl == 2:
            val = 60
        elif mctl == 1:
            val = 255 - 60
        else:
            val = 0
        i2c.writeto(0x38,bytes([i,val]))
        time.sleep(.05)

def grip(open):
    if open:
        i2c.writeto(0x38,bytes([0x10,50]))
    else:
        i2c.writeto(0x38,bytes([0x10,0]))

for dir in patterns.keys():
    ctl = patterns[dir]
    print(dir)
    motCtl(ctl)
    grip((ctl & 1) == 1)
    time.sleep(2)



# stop    
time.sleep(1)
for i in range(4):
    i2c.writeto(0x38,bytes([i,0]))
    time.sleep(.11)

