import sys

sys.path.append("")

from micropython import const

import uasyncio as asyncio
import aioble
import bluetooth

import random
import struct

import machine
import neopixel

import micropython

_ioMap = {
    "model":"stampc3u",
    "device":2,
    "btn":9,
    "led":2,
    "i2c":[0,1], # clock first. to be checked
    "motor":[3,4,5,6], # 2 pins per motor
}
 
##### initialize built-in stuff first ######
### LED
neoPin = _ioMap["led"]
p = machine.Pin(neoPin)
RGB = neopixel.NeoPixel(p,1)

def rgbFill(color):
    global RGB
    RGB.fill(color)
    RGB.write()

##### init motor outputs
motor = []
for p in _ioMap["motor"]:
    motor.append({
        "io":p,
        "pin":machine.PWM(p,freq=1000,duty=0),
        "mode":"pwm"
        }
    )

print("Motor setting:",motor)

##### globals for motor
_numMotors = micropython.const(len(motor) // 2)
_motorSteps = micropython.const(5)
_motorCtl = bytearray([-128]*_numMotors) # -(steps)..0..(steps)
_motorCtlShadow = bytearray(_numMotors) # local copy within isr/scheduled task
_motorSlot = bytearray([1]) # start with 1

##### we use PWM channels for motor
# a static "1" cannot be (reliably?) set via PWM
# maybe the max. dutycycle (1023) is ok 
# else use deinit followed by out

def setPwm(mot):
    global motor
    if motor[mot]["mode"] != "pwm":
        motor[mot]["pin"] = machine.PWM(motor[mot]["io"],freq=1000,duty=0) 
        motor[mot]["mode"] = "pwm"

def setHigh(mot):
    global motor
    if motor[mot]["mode"] == "pwm":
        motor[mot]["pin"].deinit()
        machine.Pin(motor[mot]["io"],machine["pin"].OUT,value=1)
        motor[mot]["mode"] = "high"


def motorDrive(midx,value,brk=True):
    """ set pins of current motor. value in range -10 .. 10"""
    if midx >= _numMotors:
        print("Invalid motor")
        return

    if value == 0:
        # break
        setPwm(midx*2)
        motor[midx*2]["pin"].duty(0)
        setPwm(midx*2+1)
        motor[midx*2+1]["pin"].duty(0)
    elif value == -128:
        # free
        setPwm(midx*2)
        motor[midx*2]["pin"].duty(1023)
        setPwm(midx*2+1)
        motor[midx*2+1]["pin"].duty(1023)
    elif abs(value > 10):
        print("Invalid value")
        return
    elif value < 0:
        # reverse
        if brk:
            motor[midx*2]["pin"].duty(0)
        else:
            motor[midx*2]["pin"].duty(1023)
        motor[midx*2+1]["pin"].duty(int(abs(value) / 10 * 1023))
    else:
        # forward
        motor[midx*2]["pin"].duty(int(abs(value) / 10 * 1023))
        if brk:
            motor[midx*2+1]["pin"].duty(0)
        else:
            motor[midx*2+1]["pin"].duty(1023)


##########
#p = machine.PWM(3,freq=1000,duty=500)
#p.deinit()
#p = machine.Pin(3,machine["pin"].OUT,value=1)
#p = machine.Pin(3,machine["pin"].OUT,value=0)
#p = machine.PWM(3,freq=1000,duty=500)
###########

