import sys

sys.path.append("")

from micropython import const

import uasyncio as asyncio
import aioble
import bluetooth

import cryptolib
import random
import struct

import machine
import json
import os

import neopixel

import time 
import math

import micropython
micropython.alloc_emergency_exception_buf(100)



# config stuff
_CONF_FILE = "config.json"
files = os.listdir("/")
if _CONF_FILE in files:
    with open(_CONF_FILE) as f:
        cfdata = json.load(f)
else:
    raise BaseException("No Config")        

# verify id
if machine.unique_id().hex() != cfdata["id"]:
    raise BaseException("Invalid ID")        

try:
    # get ble key
    _bleKey = cfdata["ble"]["key"]
    #print("blekey:",_bleKey)
    _ivBase = bytearray([0]*12) # first 3/4 iv
    _cryptMode = 2 # CBC

    # generate device name
    _deviceName = f"{cfdata['model']}_{cfdata['device']:04}" 
    print("Devicename:",_deviceName)
except:
    raise BaseException("Invalid Config")        

##### initialize built-in stuff first ######
### LED

try: 
    neoPin = cfdata["io"]["led"]
    p = machine.Pin(neoPin)
    RGB = neopixel.NeoPixel(p,1)
except:
    RGB = None

def rgbFill(color):
    global RGB
    if RGB == None:
        return
    RGB.fill(color)
    RGB.write()


# pairing stuff
validation_timer = None
msgBytes = const(4)
pair_value = bytearray([0] * msgBytes)
def genChallenge():
    global pair_value
    """create new random challenge with 4 digits"""
    pin = random.getrandbits(8 * msgBytes) # micropython max is 32 bit
    pair_value = pin.to_bytes(msgBytes,"big")

def decryptMsgWithIv(resp):
    global _bleKey, _ivBase, _cryptMode
    """decrypt response data. expect 16byte encrpyted msg followed by 4 byte iv part"""
    #print("Resp:",resp.hex())
    ivPart = resp[-4:]
    #print(f"IVpart: {ivPart.hex()}")
    iv = bytearray(_ivBase + ivPart)
    #print(f"IV: {iv.hex()}")
    #print(f"KEY: {_bleKey}")
    #print(f"MODE: {_cryptMode}")
    try:
        crypt = cryptolib.aes(bytes.fromhex(_bleKey),_cryptMode,iv)
        msg = crypt.decrypt(resp[:16]) 
        # pkcs7 stuff: check final byte to get padding length
        padding = 16 - msg[-1]
        msg = msg[:padding]
        #print("decrypted msg:",msg.hex())
        return msg
    except:
        print("Decrypt failed")
        return None

def verifyResponse(resp):
    global _bleKey, _ivBase, _cryptMode
    global pair_value
    """verify response data. expect 16byte encrpyted msg followed by  byte iv part"""
    msg = decryptMsgWithIv(resp)
    #print(f"DEC: {msg}, {msg.hex()}")
    #print(f"PIN: {pair_value}, {pair_value.hex()}")
    return msg.hex() == pair_value.hex()

def encryptMsgWithIv(msg):
    global _bleKey, _ivBase, _cryptMode
    #print(f"Msg: {msg.hex()}")

    ivPart_ = bytearray([random.randint(0,256) for i in range(4)])
    #print(f"IVpart: {ivPart_.hex()}")
    #print(f"IVbase: {_ivBase.hex()}")

    iv = _ivBase + ivPart_
    #print(f"IV: {iv.hex()}")

    size = len(msg)
    #print("Len msg:",size)
    #msg = msg.to_bytes(size,"big") + bytes([16 - size]*(16 - size))
    msg += bytes([16 - size]*(16 - size))

    fwd = cryptolib.aes(bytes.fromhex(_bleKey),_cryptMode,iv)

    encoded = fwd.encrypt(msg)
    encodedWIthIv = encoded + ivPart_
    #print(f"Encoded: {encodedWIthIv.hex()}")
    return encodedWIthIv


def testChallenge():
    genChallenge()
    pin = pair_value
    print(f"PIN: {pin.hex()}")

    response = encryptMsgWithIv(pin)

    print(verifyResponse(response))

# testChallenge()

# connected stated
connected = False
authorized = False
currentConnection = None

# machine.unique_id is not stable on Atom S3U ...
# device_address = machine.unique_id()
# activate BLE
ble = bluetooth.BLE()
if not ble.active():
    ble.active(True)


IO_CAPABILITY_DISPLAY_ONLY = const(0)
IO_CAPABILITY_DISPLAY_YESNO = const(1)
IO_CAPABILITY_KEYBOARD_ONLY = const(2)
IO_CAPABILITY_NO_INPUT_OUTPUT = const(3)
IO_CAPABILITY_KEYBOARD_DISPLAY = const(4)

# test security features
# ble.config(bond=True,io=_IO_CAPABILITY_DISPLAY_ONLY,le_secure=True)
# bond=True,io=0,le_secure=True  prompts for pin when run from host application
# however, this seem to be not processed by aioble
# ble.config(bond=True,io=_IO_CAPABILITY_NO_INPUT_OUTPUT,le_secure=True)
useValidation = True

mac = ble.config("mac")
device_address = mac[1]

device_address_str = ":".join("{:02X}".format(byte) for byte in device_address)

print("BLE Device Address:", device_address_str)

##############################
# security stuff. unused so far
#ble.config(bond=True,io=0,le_secure=True)
# io=0 should be like number compare

DEVICE_NAME = _deviceName
ble.config(gap_name=DEVICE_NAME)

DEVICE_APPEARANCE = const(386) # generic remote control
#print("appearance",DEVICE_APPEARANCE)



    
# org.bluetooth.service.environmental_sensing
ENV_SENSE_UUID = bluetooth.UUID(0x181A)
# org.bluetooth.characteristic.temperature
ENV_SENSE_TEMP_UUID = bluetooth.UUID(0x2A6E)

# automation 
ENV_CTL_UUID = bluetooth.UUID(0x1815)
# org.bluetooth.characteristic.digital
ENV_CTL_OUT_UUID = bluetooth.UUID(0x2A56)

# device config characteristics within device information service
# creating uuid from long string tricky ...
def mkUuidFromString(s):
    a = s.replace('-', '')
    b = bytes.fromhex(a)
    c = bytes(b[i] for i in range(len(b) - 1, -1, -1))
    return bluetooth.UUID(c)

DEVICE_CONFIG_RD = mkUuidFromString("19e2282a-0777-4519-9d08-9bc983c3a7d0")
DEVICE_PAIR = mkUuidFromString("bda7b898-782a-4a50-8d10-79d897ea82c2")

# org.bluetooth.characteristic.gap.appearance.xml
#_ADV_APPEARANCE_GENERIC_THERMOMETER = const(768)

# How frequently to send advertising beacons.
ADV_INTERVAL_MS = 250_000


# Register GATT server.
temp_service = aioble.Service(ENV_SENSE_UUID)
temp_characteristic = aioble.Characteristic(
    temp_service, ENV_SENSE_TEMP_UUID, read=True, notify=True
)

# Register GATT server.
ctl_service = aioble.Service(ENV_CTL_UUID)
ctl_characteristic = aioble.Characteristic(
    ctl_service, ENV_CTL_OUT_UUID, read=True, write=True, notify=False, capture=True
)

# device infomration
ENV_INFO_UUID = bluetooth.UUID(0x180A)
info_service = aioble.Service(ENV_INFO_UUID)
mfc_characteristic = aioble.Characteristic(
    info_service, bluetooth.UUID(0x2A29), read=True, notify=False
)
mfc_name = "Digital Codes"
mfc_characteristic.write(mfc_name.encode())

mdl_characteristic = aioble.Characteristic(
    info_service, bluetooth.UUID(0x2A24), read=True, notify=False
)
mdl_name = DEVICE_NAME
mdl_characteristic.write(mdl_name.encode())

# add config characterisitcs 
cfg_characteristic = aioble.Characteristic(
    info_service, DEVICE_CONFIG_RD, read=True, write=False, notify=False
)

# index 2 is personality. default to 0
personality = 4
cfg_value = bytearray([0x55,0xaa,personality,0])
cfg_characteristic.write(cfg_value)
# change personality value when loading new modules...


# AK-CHECK
# windows has issues writing pairing value. might be related to 
# info service assumed to be read only
# use config and pairing with ctl service instead
# capture must be true in order to get data!!!
pair_characteristic = aioble.Characteristic(
    ctl_service, DEVICE_PAIR, read=True, write=True, notify=False, capture=True
)
pair_characteristic.write(pair_value)

# register all services
aioble.register_services(temp_service,ctl_service,info_service)


# Helper to encode the temperature characteristic encoding (sint16, hundredths of a degree).
def _encode_data(data):
    ### wheelchair has 2 data values: 0:status (byte), 1: turn (byte), 2:speed (uint16),  
    sensData = struct.pack("<bbh", int(data["status"]),int(data["turn"]),int(data["speed"]))
    encryptedData = encryptMsgWithIv(sensData)
    return encryptedData

def _decode_ctl(msg):
    # b: unsigned char
    ### wheelchair has 5 ctl byte values: 0:starting (bool), 1:speed (0..10), 2:turn (0..10), 3:direction (0/1), 4:voltage (0/1)    
    data = decryptMsgWithIv(msg)
    ctlData = struct.unpack("<bbbbb", data)
    return ctlData


##############################
# setup blcd stuff

# Hall sensors:
# A - white  (next to VCC)
# B - blue
# C - yellow

# Motor coils:
# A - yellow
# B - green
# C - blue (next to V+)

# detect proper settings: smooth rotation, unstoppable
# bad settings: stoppable or noisy rotation or noise without rotation

# rotation setting is low active
# break is low active
# maybe use pulldown on break to prevent unwanted rotation on startup until controller is active

# setup pwm
# speed pulse: g8
speedPin = 8
# pwm: g6   # 6 is used by neopixel
ctlPin = 6
# maybe use pulldown on ctlPin
brk = 7 # pull break low after startup
# extra: g10  # 

brkSignal = machine.Pin(brk, machine.Pin.OUT)
brkSignal.on() # break

speedSignal = machine.Pin(speedPin, machine.Pin.IN, machine.Pin.PULL_UP)

# tick counter shared with irq callback
speedTick = time.ticks_ms()
speedDelta = 0
# the irq callback just stores the time difference between pulses
# for more action see "Using micropython.schedule"

def speedCallback(p):
    """ interrupt to measure delay between pulses """
    global speedTick, speedDelta
    t = time.ticks_ms()
    speedDelta = time.ticks_diff(t, speedTick) # set delta
    speedTick = t # update tick

# we can start the irq right here
speedSignal.irq(trigger=machine.Pin.IRQ_FALLING, handler=speedCallback)


########
# duty values are voltage dependent
ctlMinDuty = 0
ctlMaxDuty = 0
ctlMaxRegDuty = 0 # while regulating we allow more

# return values are fixed
ctlMinReturn = 25 # we need to measure and update this value
ctlMaxReturn = 80 # we need to measure and update this value


def setDutyLimits(high = False):
    global ctlMinDuty, ctlMaxDuty, ctlMaxRegDuty
    if high:
        print("High voltage")
        ctlMinDuty = 40
        ctlMaxDuty = 150
        ctlMaxRegDuty = 250 # leave some extra margin
    else:
        print("Low voltage")
        ctlMinDuty = 100
        ctlMaxDuty = 250
        ctlMaxRegDuty = 400 # leave some extra margin

# intit duty limits
setDutyLimits(False)
        
ctlSignal = None
# intended speed and duty setting
targetDuty = 0
targetSpeed = 0
# current speed setting
currentSpeed = 0

statusCodes = {"good":0,"battery":1,"warning":2,"error":3}

# pulse delay in range 40 .. 15 ms ~ 25 .. 75 Hz
# create duty cycle mapping
def speedToDuty(speed):
    """map speed to duty cycle"""
    global ctlMinDuty, ctlMaxDuty
    return ctlMinDuty + (ctlMaxDuty - ctlMinDuty) * speed // 10

# create speed mapping
def speedToReturn(speed):
    """map speed to delay"""
    global ctlMinReturn, ctlMaxReturn
    return ctlMinReturn + (ctlMaxReturn - ctlMinReturn) * speed // 10

#create speed mapping
def delayToCtl(delay):
    """map delay to speed"""
    if delay > 200:
        return 0
    elif delay < 1:
        return 10
    else:
        return 1000 / delay

# speed regulator
def speedRegulator(current,expected):
    """control speed based on target speed"""
    global targetDuty
    if targetDuty == 0:
        return
    if abs(current - expected) < 1:
        return
    elif current < expected:
        error = expected - current
        targetDuty += math.ceil(error)
    else:    
        error = current - expected
        targetDuty -= math.ceil(error)
    if targetDuty < ctlMinDuty:
        targetDuty = ctlMinDuty
    elif targetDuty > ctlMaxRegDuty:
        targetDuty = ctlMaxRegDuty
    print("Error:",error)
    setCtlDuty(math.floor(targetDuty))
        


# control output
def initCtlPin():
    """set ctl value to static value"""
    global ctlSignal, ctlPin
    global targetDuty, targetSpeed
    if type(ctlSignal) == machine.PWM:
        ctlSignal.deinit()
    ctlSignal = machine.Pin(ctlPin, machine.Pin.OUT)
    ctlSignal.off()
    targetDuty = 0
    targetSpeed = 0


def initCtlPwm():
    """set ctl value to pwm value"""
    # start with some slow value
    global ctlSignal, ctlPin, ctlMinDuty
    if type(ctlSignal) == machine.PWM:
        print("ALready PWM")
        ctlSignal.duty(speedToDuty(0))
        return
    # set pwm 
    ctlSignal = machine.PWM(machine.Pin(ctlPin), freq=1000, duty=speedToDuty(0))

def setCtlDuty(duty):
    """set ctl value to duty value"""
    global ctlSignal
    print("Duty:",duty)
    ctlSignal.duty(duty)

# init to static 0
initCtlPin()
time.sleep(.1)
# release break
brkSignal.off()


# This would be periodically polling a hardware sensor.
async def sensor_task():
    global connected
    global currentConnection
    global speedTick, speedDelta, statusCodes
    global targetDuty
    print("Start sense")
    while True:
        if connected and authorized:
            t = time.ticks_ms()
            t0 = speedTick
            delta = time.ticks_diff(t, t0) # set delta
            #print("Delta",delta)
            status = 0
            if delta > 200:
                #print("Delta",delta)
                speedReturn = 0   
                if targetDuty > 0:
                    # print("Timeout")
                    status = statusCodes["warning"]
            else:
                speedReturn = delayToCtl(speedDelta) # use global speedDelta
                expectedReturn = speedToReturn(targetSpeed)
                # slower => actual - expected negative. values +/- sort of ok. 
                # larger (5,10 ..) values are bad
                speedRegulator(speedReturn,expectedReturn)
                
            #print("Temp",speed)
            try:
                ## App: expect 3 values, status(byte), turn(byte), speed(uint16)
                data = {"status":status,"turn":random.randint(0,10),"speed":speedReturn}
                temp_characteristic.write(_encode_data(data))
                temp_characteristic.notify(currentConnection)
            except:
                print("sense error")
                await asyncio.sleep_ms(100)
                continue
           
        await asyncio.sleep_ms(100)

async def ctl_task():
    global connected, targetDuty, targetSpeed
    print("Start ctl")
    while True:
        if connected and authorized:
            try:
                conn, _value = await ctl_characteristic.written()
                ctl = _decode_ctl(_value)
                print("Received ctl:",ctl)
                ## App: 0: starting, 1: speed, 2: turn, 3: direction, 4: voltage
                # if starting, initialize PWM, set target speed to ctl[1] (normally 0)
                # else set target speed to value if value > 0
                # else set target speed to 0 and deinit PWM
                if ctl[0] == 1:  # Check if the value is 1 (on)
                    # Code to turn the light on
                    initCtlPin() # set to static value
                    # on start also check voltage. before init pwm!
                    setDutyLimits(ctl[4] == 1)
                    await asyncio.sleep_ms(100)
                    initCtlPwm() # set to default value
                    targetDuty = speedToDuty(ctl[1])
                    targetSpeed = ctl[1]
                    print("START")
                    rgbFill((0,30,0))
                    
                elif ctl[0] == 2:  # Check if the value is 2 (stop)       
                    initCtlPin()
                    targetDuty = 0
                    targetSpeed = 0
                    print("STOP")
                    rgbFill((30,0,0))
                    
                else:  # Check if the value is 0 (off)
                    # Code to turn the light off
                    targetSpeed = ctl[1]
                    duty = speedToDuty(ctl[1])
                    targetDuty = duty
                    setCtlDuty(duty)
                    # check if stop
                    print("RUN")
                    rgbFill((0,0,30))
            except:
                print("ctl error")
                await asyncio.sleep_ms(100)

        else:
            await asyncio.sleep_ms(100)

async def pair_task():
    global connected
    global authorized
    global validation_timer
    print("Start pair")
    while True:
        if connected:
            try:
                conn, _value = await pair_characteristic.written()
                print("Pair received:",conn,_value)
                if verifyResponse(_value):
                    print("Pair OK")
                    validation_timer.deinit()
                    authorized = True
                else:
                    print("Pair failed")
            except Exception as e:
                #print("Error occurred:", e)
                #print("Error type:", type(e))
                #print("Error arguments:", e.args)
                print("pair error")
                authorized = False
                genChallenge() # updates pair_value
                pair_characteristic.write(pair_value)
                await asyncio.sleep_ms(100)

        else:
            await asyncio.sleep_ms(100)


def on_validation_timer(timer):
    #print("Validation timer expired, disconnecting.",timer)
    asyncio.create_task(disconnect_device())

async def disconnect_device():
    global connected
    global authorized
    global currentConnection
    if connected:
        #print("Disconnecting:",currentConnection)
        await currentConnection.disconnect(0)
        #print("Disconnect complete")
        # stop motor
        initCtlPin()
        



# Serially wait for connections. Don't advertise while a central is
# connected.
async def peripheral_task():
    global connected
    global authorized
    global currentConnection
    global validation_timer
    global pair_value
    global useValidation
    # esp32c3 timer handling is different ...
    if "ESP32C3" in cfdata["os"]["machine"]:
        validation_timer = machine.Timer(0)
    else:
        validation_timer = machine.Timer(-1)
    print("Start adv")
    while True:
        try:
            async with await aioble.advertise(
                ADV_INTERVAL_MS,
                name=DEVICE_NAME.encode(),
                services=[ENV_SENSE_UUID,ENV_CTL_UUID,ENV_INFO_UUID],
                appearance=DEVICE_APPEARANCE,
                #manufacturer=(0xabcd, b"Digital Codes"),
            ) as connection:
                print("Connection from", connection.device,connection.device.addr_hex())
                connected = True
                currentConnection = connection
                # new challenge
                genChallenge() # initialize challenge
                pair_characteristic.write(pair_value)
                # Start a timer for client ID validation
                if useValidation:
                    validation_timer.init(mode=machine.Timer.ONE_SHOT, period=10000, callback=on_validation_timer)
                # clear timer if authenticated like:
                # validation_timer.deinit()  

                await connection.disconnected(timeout_ms=None)
                print("Disconnected 1")
                connected = False
                authorized = False
                currentConnection = None
                initCtlPin()
                asyncio.sleep_ms(10)
                rgbFill((10,10,10))
        except:
            print("argh ...")
            await asyncio.sleep_ms(100)


# Run both tasks.
async def main():
    t1 = asyncio.create_task(sensor_task())
    t2 = asyncio.create_task(ctl_task())
    t3 = asyncio.create_task(peripheral_task())
    t4 = asyncio.create_task(pair_task())
    # await asyncio.gather(t1, t2, t3)

    try:
        await asyncio.gather(t1, t2, t3,t4)

    except asyncio.TimeoutError:
        print("Timeout in main:")

    except aioble.DeviceDisconnectedError:
        print("Disconnect in main:")

    except aioble.CancelledError:
        print("Cancelled")

    except any as err:
        print("Error in main:",err)

    rgbFill((10,10,10))


rgbFill((10,10,10))
asyncio.run(main())

# finally ...
initCtlPin()
speedSignal.irq(handler=None)
brkSignal.on() # break
