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

# works for matrix and lite
def rgbFill(color):
    return


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
    print("blekey:",_bleKey)
    _ivBase = bytearray([0]*12) # first 3/4 iv
    _cryptMode = 2 # CBC

    # generate device name
    _deviceName = f"{cfdata['model']}_{cfdata['device']:04}" 
    print("Devicename:",_deviceName)
except:
    raise BaseException("Invalid Config")        


# pairing stuff
validation_timer = None
_msgBytes = const(4)
pair_value = bytearray([0]*_msgBytes)
def genChallenge():
    global pair_value
    """create new random challenge with 4 digits"""
    pin = random.getrandbits(8*_msgBytes) # micropython max is 32 bit
    pair_value = pin.to_bytes(_msgBytes,"big")

def verifyResponse(resp):
    global _bleKey, _ivBase, _cryptMode
    global pair_value
    """verify response data. expect 16byte encrpyted msg followed by 8 byte iv part"""
    print("Resp:",resp.hex())
    ivPart = resp[-4:]
    print(f"IVpart: {ivPart.hex()}")
    iv = bytearray(_ivBase + ivPart)
    print(f"IV: {iv.hex()}")
    print(f"KEY: {_bleKey}")
    print(f"MODE: {_cryptMode}")
    crypt = cryptolib.aes(bytes.fromhex(_bleKey),_cryptMode,iv)
    msg = crypt.decrypt(resp[:16])[:_msgBytes]
    print(f"DEC: {msg}, {msg.hex()}")
    print(f"PIN: {pair_value}, {pair_value.hex()}")
    return msg.hex() == pair_value.hex()

def testChallenge():
    genChallenge()
    pin = pair_value
    print(f"PIN: {pin}")

    ivPart_ = bytearray([random.randint(0,256) for i in range(4)])
    print(f"IVpart: {ivPart_.hex()}")
    print(f"IVbase: {_ivBase.hex()}")

    iv = _ivBase + ivPart_
    print(f"IV: {iv.hex()}")

    fwd = cryptolib.aes(bytes.fromhex(_bleKey),_cryptMode,iv)

    # need to generate 16 byte message for encryption (padding)
    # standard pkcs7 padding ?
    msg = pin + bytes([16 - _msgBytes]*(16 - _msgBytes))
    print(f"MSG: {msg.hex()}")

    encoded = fwd.encrypt(msg)
    print(f"ENC: {encoded.hex()}")

    response = encoded + ivPart_
    print(f"RESP: {response.hex()}")

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


_IO_CAPABILITY_DISPLAY_ONLY = const(0)
_IO_CAPABILITY_DISPLAY_YESNO = const(1)
_IO_CAPABILITY_KEYBOARD_ONLY = const(2)
_IO_CAPABILITY_NO_INPUT_OUTPUT = const(3)
_IO_CAPABILITY_KEYBOARD_DISPLAY = const(4)

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
print("name",DEVICE_NAME)

DEVICE_APPEARANCE = const(386) # generic remote control
print("appearance",DEVICE_APPEARANCE)


# tux3
pc_address_str = "dc:46:28:1f:b0:61"
# Split the string into components and convert each to an integer, then to bytes
pc_address = bytes(int(part, 16) for part in pc_address_str.split(':'))
print(pc_address)


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
print("SENSE",ENV_SENSE_UUID)
# org.bluetooth.characteristic.temperature
ENV_SENSE_TEMP_UUID = bluetooth.UUID(0x2A6E)
print("TEMP",ENV_SENSE_TEMP_UUID)

# automation 
ENV_CTL_UUID = bluetooth.UUID(0x1815)
print("SENSE",ENV_CTL_UUID)
# org.bluetooth.characteristic.digital
ENV_CTL_OUT_UUID = bluetooth.UUID(0x2A56)
print("TEMP",ENV_CTL_OUT_UUID)

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
print("TEMP srv",temp_service)
temp_characteristic = aioble.Characteristic(
    temp_service, ENV_SENSE_TEMP_UUID, read=True, notify=True
)
print("TEMP char",temp_characteristic)
#aioble.register_services(temp_service)

# Register GATT server.
ctl_service = aioble.Service(ENV_CTL_UUID)
print("CTL srv",ctl_service)
ctl_characteristic = aioble.Characteristic(
    ctl_service, ENV_CTL_OUT_UUID, read=True, write=True, notify=False, capture=True
)
print("OUT char",ctl_characteristic)

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
cfg_value = bytearray([0,1,2,3,4,5,6,7,8,9])
cfg_characteristic.write(cfg_value)

# capture must be true in order to get data!!!
pair_characteristic = aioble.Characteristic(
    info_service, DEVICE_PAIR, read=True, write=True, notify=False, capture=True
)
pair_characteristic.write(pair_value)

aioble.register_services(temp_service,ctl_service,info_service)


# Helper to encode the temperature characteristic encoding (sint16, hundredths of a degree).
def _encode_temperature(temp_deg_c):
    return struct.pack("<h", int(temp_deg_c * 100))

def _decode_ctl(data):
    # b: unsigned char
    return struct.unpack("b", data)


# This would be periodically polling a hardware sensor.
async def sensor_task():
    global connected
    global currentConnection
    print("Start sense")
    t = 24.5
    while True:
        if connected and authorized:
            print("Temp",t)
            try:
                temp_characteristic.write(_encode_temperature(t))
                temp_characteristic.notify(currentConnection)
            except:
                print("sense error")
                await asyncio.sleep_ms(100)
                continue
           
            t += random.uniform(-0.5, 0.5)
        await asyncio.sleep_ms(1000)

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
                    print("ON")
                    rgbFill((0,100,0))
                elif value == 0:  # Check if the value is 0 (off)
                    # Code to turn the light off
                    print("OFF")
                    rgbFill((0,0,30))
                else:
                    print("else")
                    rgbFill((100,0,0))
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



# Serially wait for connections. Don't advertise while a central is
# connected.
async def peripheral_task():
    global connected
    global authorized
    global currentConnection
    global validation_timer
    global pair_value
    global useValidation
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

