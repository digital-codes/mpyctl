import sys

sys.path.append("")

from micropython import const

import uasyncio as asyncio
import aioble
import bluetooth

import random
import struct

import machine

# works for matrix and lite
def rgbFill(color):
    print("rgb fill")
    return


# connected stated
connected = False
currentConnection = None

# machine.unique_id is not stable on Atom S3U ...
# device_address = machine.unique_id()
# activate BLE
ble = bluetooth.BLE()
if not ble.active():
    ble.active(True)

mac = ble.config("mac")
device_address = mac[1]

device_address_str = ":".join("{:02X}".format(byte) for byte in device_address)

print("BLE Device Address:", device_address_str)


DEVICE_NAME = "MpyCtlAtom"
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
mdl_name = "MpyCtl"
mdl_characteristic.write(mdl_name.encode())

sno_characteristic = aioble.Characteristic(
    info_service, bluetooth.UUID(0x2A25), read=True, notify=False
)
sno_name = "1234"
sno_characteristic.write(sno_name.encode())



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
        if connected:
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
        if connected:
            try:
                conn, _value = await ctl_characteristic.written()
            except:
                print("ctl error")
                await asyncio.sleep_ms(100)
                continue

            value = _decode_ctl(_value)[0]
            print("Received:",conn, value)
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
        else:
            await asyncio.sleep_ms(1000)




# Serially wait for connections. Don't advertise while a central is
# connected.
async def peripheral_task():
    global connected
    global currentConnection
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
    ##            try:
    ##                connection.pair("12341234")
    ##                print("Pair OK")
    ##            except Exception as e:
    ##                print(f"Pair failed: {e}")

                await connection.disconnected(timeout_ms=None)
                print("Disconnected 1")
                connected = False
                currentConnection = None
                rgbFill((30,30,30))
        except:
            print("argh ...")
            await asyncio.sleep_ms(100)


# Run both tasks.
async def main():
    t1 = asyncio.create_task(sensor_task())
    t2 = asyncio.create_task(ctl_task())
    t3 = asyncio.create_task(peripheral_task())
    # await asyncio.gather(t1, t2, t3)

    try:
        await asyncio.gather(t1, t2, t3)

    except asyncio.TimeoutError:
        print("Timeout in main:")

    except aioble.DeviceDisconnectedError:
        print("Disconnect in main:")

    except aioble.CancelledError:
        print("Cancelled")

    except any as err:
        print("Error in main:",err)

    rgbFill((30,30,30))


rgbFill((30,30,30))
asyncio.run(main())

