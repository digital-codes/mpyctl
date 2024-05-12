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
    "led":2,
    "i2c":[], # clock first
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
    motor.append(machine.Pin(p,machine.Pin.OUT))

print("Motor setting:",motor)

#### globals for motor
_numMotors = micropython.const(len(motor) // 2)
_motorSteps = micropython.const(5)
_motorCtl = bytearray([-128]*_numMotors) # -(steps)..0..(steps)
_motorCtlShadow = bytearray(_numMotors) # local copy within isr/scheduled task
_motorSlot = bytearray([1]) # start with 1

##########
#p = machine.PWM(3,freq=1000,duty=500)
#p.deinit()
#p = machine.Pin(3,machine.Pin.OUT,value=1)
#p = machine.Pin(3,machine.Pin.OUT,value=0)
#p = machine.PWM(3,freq=1000,duty=500)
###########



# isr: copy motorCtl to schadow, then schedule output task
def motorDriver(slot: int):
    global _motorCtlShadow, _motorSlot, motor, _numMotors
    """ Set all motor IO pins from motorCtlShadow according to current slot"""
    fmt = "b"*_numMotors
    ctl = struct.unpack(fmt,_motorCtlShadow)
    #print(ctl)
    for idx in range (_numMotors):
        m = ctl[idx]
        #print(m)
        if m == 0:
            # break
            motor[idx*2].value(0)
            motor[idx*2+1].value(0)
        elif m == -128:
            # free
            motor[idx*2].value(1)
            motor[idx*2+1].value(1)
        elif abs(m) < slot:
            # free
            motor[idx*2].value(1)
            motor[idx*2+1].value(1)
        elif m < 0:
            # reverse
            motor[idx*2].value(0)
            motor[idx*2+1].value(1)
        else:
            # forward
            motor[idx*2].value(1)
            motor[idx*2+1].value(0)

def motorIsr():
    """ motor timer interrupt handler
        copy control for driver
        increment slot
        schedule driver
    """
    global _motorCtl, _motorCtlShadow, _motorSlot, _motorSteps
    irqState = machine.disable_irq()
    micropython.schedule(motorDriver,_motorSlot[0])
    _motorCtlShadow[:] = _motorCtl # copy
    if _motorSlot[0] >= _motorSteps:
        _motorSlot[0] = 1 # else we start with min 2 active cycles
    else:
        _motorSlot[0] += 1
    machine.enable_irq(irqState)

#### initialize the motor timer
_motorTimerId = micropython.const(2) # hw timer id
# on esp32c 50 and 100Hz seem to be good, 500Hz is unstable
_motorTimerPeriod = micropython.const(20) # ms period

motorTimer = machine.Timer(_motorTimerId)
motorTimer.init(period=_motorTimerPeriod, mode=machine.Timer.PERIODIC, callback=lambda t:motorIsr())
