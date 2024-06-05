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
import math

import mpu6886



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
    RGB = neopixel.NeoPixel(p,25)
except:
    RGB = None

def rgbFill(color):
    global RGB
    if RGB == None:
        return
    color2 = [int(x/8) for x in color]
    RGB.fill(color2)
    RGB.write()

# ##########################
# IMU stuff
imuI2c = machine.I2C(0,scl=machine.Pin(21),sda=machine.Pin(25),freq=400000)
imu = mpu6886.MPU6886(imuI2c)

def find_abs_max_and_sign_index(a, b, c):
    # List of values to compare
    values = [a, b, c]
    
    # Calculate the absolute values and find the index of the max
    abs_values = [abs(val) for val in values]
    max_index = abs_values.index(max(abs_values))
    max_val = abs(values[max_index])

    # Determine the sign of the maximum absolute value
    if values[max_index] > 0:
        sign = 1
    elif values[max_index] < 0:
        sign = -1
    else:
        sign = 0

    return max_val, sign, max_index


def compute_axis_alignment_with_gravity(ax, ay, az):
    # Normalize the acceleration vector
    norm_a = math.sqrt(ax**2 + ay**2 + az**2)
    if norm_a == 0:
        return 0, 0, 0
    
    # Calculate angles with respect to the negative gravity direction
    theta_x = math.acos(-ax / norm_a)
    theta_y = math.acos(-ay / norm_a)
    theta_z = math.acos(-az / norm_a)

    # Convert radians to degrees for easier interpretation
    return math.degrees(theta_x), math.degrees(theta_y), math.degrees(theta_z)


def quaternion_from_euler(theta_x, theta_y, theta_z):
    # Helper function to compute quaternion for rotation about an axis
    def axis_angle_to_quat(angle, axis):
        w = math.cos(angle / 2.0)
        x = math.sin(angle / 2.0) * axis[0]
        y = math.sin(angle / 2.0) * axis[1]
        z = math.sin(angle / 2.0) * axis[2]
        return (w, x, y, z)

    # Convert degrees to radians
    theta_x = math.radians(theta_x)
    theta_y = math.radians(theta_y)
    theta_z = math.radians(theta_z)

    # Quaternion for each axis rotation
    qx = axis_angle_to_quat(theta_x, [1, 0, 0])
    qy = axis_angle_to_quat(theta_y, [0, 1, 0])
    qz = axis_angle_to_quat(theta_z, [0, 0, 1])

    # Function to multiply quaternions
    def multiply_quaternions(q1, q2):
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2
        w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
        x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
        y = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2
        z = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2
        return (w, x, y, z)

    # Compose rotations: quaternion multiplication is right to left for this order
    q = multiply_quaternions(qz, qy)
    q = multiply_quaternions(q, qx)
    
    return q




# ##########################    

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
        msg = crypt.decrypt(resp[:16])[: msgBytes]
        #print("decrypted msg:",msg.hex())
        return msg
    except:
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


##Device Information Service (0x180A): This service contains basic device information.
##
##    Manufacturer Name String (0x2A29): UUID for manufacturer's name.
##    Model Number String (0x2A24): UUID for the model number of the device.
##    Serial Number String (0x2A25): UUID for the serial number.
##    Hardware Revision String (0x2A27): UUID for the hardware revision.
##    Firmware Revision String (0x2A26): UUID for the firmware revision.
##    Software Revision String (0x2A28): UUID for the software revision.
##    System ID (0x2A23): UUID for system ID.
##    IEEE 11073-20601 Regulatory Certification Data List (0x2A2A): UUID for regulatory certification data.
##    PnP ID (0x2A50): UUID for Plug and Play ID.
##
##Battery Service (0x180F): This service provides information about the battery level.
##    Battery Level (0x2A19): UUID for battery level.
##    

##Environmental Sensing Service (0x181A): This service is often used for environmental sensors, such as temperature, humidity, or air quality sensors.
##
##    Temperature (0x2A6E)
##    Humidity (0x2A6F)
##    Pressure (0x2A6D)
##

##Automation IO Service (0x1815): This service is relevant for simple input/output functionalities, often used in home automation for controlling actuators like switches or relays.
##Digital (UUID: 0x2A56):
##
##    This characteristic is used to represent the state of a digital signal. It's typically used for simple binary devices like switches, where the characteristic can represent an ON or OFF state.
##    It can be used to read the current state, write a new state (like turning a light on or off), or notify/indicate a state change.
##
##Analog (UUID: 0x2A58):
##
##    The Analog characteristic represents the state of an analog signal. It can be used for devices that require or provide a range of values instead of just binary states, like dimmers or variable-speed fans.
##    Similar to the Digital characteristic, it supports read, write, and notify/indicate operations.
##
##Aggregate (UUID: 0x2A5A):
##
##    This characteristic is used to aggregate multiple digital and analog signals into a single characteristic. It's useful when a device has multiple sensors or actuators that need to be read or controlled simultaneously.
##    The Aggregate characteristic is a bitfield or array that encapsulates the states of various digital and analog signals.
##    

##In Bluetooth Low Energy (BLE), the Appearance value is a standardized data type used in advertising packets to give a hint about the type of device. This helps in identifying the kind of device before making a connection. The Appearance value is a 16-bit field defined in the Bluetooth specifications.
##
##Here are some standard Appearance values for common device types:
##
##    Generic Phone (Appearance Value: 64): Represents a generic phone.
##
##    Generic Computer (Appearance Value: 128): Represents a generic computer or computing device.
##
##    Generic Watch (Appearance Value: 192): This is typically used for wearable watch devices.
##
##    Generic Thermometer (Appearance Value: 768): Represents a generic thermometer, often used for temperature sensing devices.
##
##    Heart Rate Sensor (Appearance Value: 832): Used for devices that measure heart rate.
##
##    Blood Pressure (Appearance Value: 896): For blood pressure monitors.
##
##    Human Interface Device (HID) (Appearance Value: 960): Used for input or output devices like keyboards, mice, or game controllers.
##
##    Generic Light Fixture (Appearance Value: 1088): For smart lighting systems.
##
##    Generic Fan (Appearance Value: 1152): Used for devices like smart fans.
##
##    Generic Air Conditioning (Appearance Value: 1216): For air conditioning units.
##    

    
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
# index 2 is personality
cfg_value = bytearray([0x55,0xaa,2,0])
cfg_characteristic.write(cfg_value)

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


def _decode_ctl(msg):
    # b: unsigned char
    data = decryptMsgWithIv(msg)
    ctlData = struct.unpack("b", data)
    return ctlData


# This would be periodically polling a hardware sensor.
async def sensor_task():
    global connected
    global currentConnection
    print("Start sense")
    while True:
        if connected and authorized:
            try:
                acc = imu.acceleration
                m,s,i = find_abs_max_and_sign_index(*acc)
                if m > 2:
                    if i == 0:
                        rgbFill((255,0,0))
                    elif i == 1:    
                        rgbFill((0,255,0))  
                    else:    
                        rgbFill((0,0,255))
                else:
                    rgbFill((255,255,255))   
                            
                theta_x, theta_y, theta_z = compute_axis_alignment_with_gravity(*acc)

                quaternion = quaternion_from_euler(theta_x, theta_y, theta_z)
                # quaternion values are -1 .. 1. max is -10..10. sign and index are bool
                # print("Q:",quaternion,"m:",m,"s:",s,"i:",i)
                # > 5 signed int, 2 signed bytes
                # format < is little endian
                sensData = struct.pack("<hhhhhbb", 
                                       int(quaternion[0] * 1000),
                                       int(quaternion[1] * 1000),
                                       int(quaternion[2] * 1000),
                                       int(quaternion[3] * 1000),
                                       int(m * 1000),
                                       s,i)
                encryptedData = encryptMsgWithIv(sensData)
                temp_characteristic.write(encryptedData)
                temp_characteristic.notify(currentConnection)
            except:
                print("sense error")
                await asyncio.sleep_ms(100)
                continue
           
        await asyncio.sleep_ms(50)


async def ctl_task():
    global connected
    print("Start ctl")
    while True:
        if connected and authorized:
            try:
                conn, _value = await ctl_characteristic.written()
                value = _decode_ctl(_value)[0]
                #print("Received:", value)
                if value == 1:  # Check if the value is 1 (on)
                    # Code to turn the light on
                    # print("ON")
                    # rgbFill((0,100,0))
                    pass
                elif value == 0:  # Check if the value is 0 (off)
                    # Code to turn the light off
                    # print("OFF")
                    # rgbFill((0,0,30))
                    pass
                else:
                    print("strange ctl")
                    # rgbFill((100,0,0))
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
        try:
            conn, _value = await pair_characteristic.written()
            if connected:
                print("Pair received:",conn,_value)
                if verifyResponse(_value):
                    print("Pair OK")
                    validation_timer.deinit()
                    authorized = True
                else:
                    print("Pair failed")
            else:
                print("Pair ignored")
                
        except Exception as e:
            print("Error occurred:", e)
            print("Error type:", type(e))
            print("Error arguments:", e.args)
            print("pair error")
            authorized = False
            genChallenge() # updates pair_value
            pair_characteristic.write(pair_value)

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
                connected = True
                currentConnection = connection
                # new challenge
                genChallenge() # initialize challenge
                pair_characteristic.write(pair_value)
                # 
                print("Connection from", connection.device,connection.device.addr_hex())
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
                asyncio.sleep_ms(10)
                rgbFill((100,100,100))
        except:
            print("argh ...")
            await asyncio.sleep_ms(100)


# Run both tasks.
async def main():
    t1 = asyncio.create_task(sensor_task())
    t2 = asyncio.create_task(ctl_task())
    t3 = asyncio.create_task(peripheral_task())
    t4 = asyncio.create_task(pair_task())

    try:
        await asyncio.gather(t1, t2, t3, t4)

    except asyncio.TimeoutError:
        print("Timeout in main:")

    except aioble.DeviceDisconnectedError:
        print("Disconnect in main:")

    except aioble.CancelledError:
        print("Cancelled")

    except any as err:
        print("Error in main:",err)

    rgbFill((100,100,100))


rgbFill((100,100,100))
asyncio.run(main())

