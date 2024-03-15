import sys

sys.path.append("")

from micropython import const as constant

import bluetooth
import network 
import json 
import os

import machine
import neopixel


# activate ble first
b = bluetooth.BLE()
b.active(1)

_CONF_FILE = "config.json"

files = os.listdir("/")

if _CONF_FILE in files:
    with open(_CONF_FILE) as f:
        cfg = json.load(f)
    print("Old config:", cfg)

else:
    _ioMap = {
        "model":"devkit-c",
        "device":-1,
        "btn":0,
        "led":-1,
        "i2c":[14,27], # clock first. to be checked
        "motor":[23,22,21,5,16,4,18,19] # 2 pins per motor. pin 3 not OK, use 5 instead
        #"motor":[4,16,18,19,21,5,22,23], # 2 pins per motor. pin 3 not OK, use 5 instead
    }
    cfg = {}
    cfg["io"] = _ioMap 
    cfg["device"] = -1 # no default device
    cfg["model"] = "" # no default model

    cfg["id"] = machine.unique_id().hex()
    o = os.uname()
    cfg["os"] = {"release":o.release,"machine":o.machine}

    bmac = b.config("mac")[1].hex()
    bkey = f"{(int(bmac, 16) % 1_000_000):06}"
    cfg["ble"] = {"key":bkey,"addr":bmac}
    w = network.WLAN()
    cfg["wlan"] = {"addr":w.config("mac").hex()}

    print("New config")

# update config
if cfg["id"] != machine.unique_id().hex():
    print("ID mismatch")
    cfg["id"] = machine.unique_id().hex()
    o = os.uname()
    cfg["os"] = {"release":o.release,"machine":o.machine}

    bmac = b.config("mac")[1].hex()
    bkey = f"{(int(bmac, 16) % 1_000_000):06}"
    cfg["ble"] = {"key":bkey,"addr":bmac}
    w = network.WLAN()
    cfg["wlan"] = {"addr":w.config("mac").hex()}
    print("Updating config")
    with open(_CONF_FILE,"w") as f:
        json.dump(cfg,f)
else:
    print("Config OK")

print(f"Config: {cfg}")


 
##### initialize built-in stuff first ######
### LED
if cfg["io"]["led"] >= 0:
    neoPin = cfg["io"]["led"]
    p = machine.Pin(neoPin)
    RGB = neopixel.NeoPixel(p,1)
else:
    RGB = None

def rgbFill(color):
    global RGB
    if RGB != None:
        RGB.fill(color)
        RGB.write()

##### init motor outputs
motor = []
for p in cfg["io"]["motor"]:
    motor.append({
        "io":p,
        "pin":machine.PWM(p,freq=1000,duty=0),
        "mode":"pwm"
        }
    )

print("Motor setting:",motor)

##### globals for motor
_motorSteps = constant(10)
_numMotors = constant(len(motor) // 2)
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
        machine.Pin(motor[mot]["io"],machine.Pin.OUT,value=1)
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
        setHigh(midx*2)
        setHigh(midx*2+1)
    elif abs(value > 10):
        print("Invalid value")
        return
    elif value < 0:
        # reverse
        if abs(value) > _motorSteps:
            value = -_motorSteps
        if brk: 
            setPwm(midx*2)
            motor[midx*2]["pin"].duty(0)
        else:
            setHigh(midx*2)
        setPwm(midx*2+1)
        motor[midx*2+1]["pin"].duty(int(abs(value) / _motorSteps * 1023))
    else:
        # forward
        if abs(value) > _motorSteps:
            value = _motorSteps
        setPwm(midx*2)
        motor[midx*2]["pin"].duty(int(abs(value) / _motorSteps * 1023))
        if brk:
            setPwm(midx*2+1)
            motor[midx*2+1]["pin"].duty(0)
        else:
            setHigh(midx*2+1)


##########
#p = machine.PWM(3,freq=1000,duty=500)
#p.deinit()
#p = machine.Pin(3,machine.Pin.OUT,value=1)
#p = machine.Pin(3,machine.Pin.OUT,value=0)
#p = machine.PWM(3,freq=1000,duty=500)
###########

