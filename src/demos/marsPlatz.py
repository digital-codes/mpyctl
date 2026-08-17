""" Marsplatz ZKM 2026 Sensor Installation """

# Sensors:
#   M5STack ENV-Pro BME688
#   M5Stack Digital Light Sensor 
#   M5Stack 9-Axis IMU MPU6886
#   M5Stack LoraWan 868/ASR6501 
# Controller:
#   M5Stack  ESP32S, LCD, Button with Grove Expansion 
#   Grove Port, unused, GPIO 1,2

# Expansion Pinout:
# Left -> Right ; top/bottom
# 39, 8, 6
# 38, 7, 5

# ENV: 39(wt)/SCL, 38(ye)/SDA  Addr 0x77
# LORA: 8(wt)/TX, 7(ye)/RX
# LIGHT: 6(wt)/AI, 5(ye)/DI
# IMU: Shared with ENV, SCL/SDA  Addr: 0x68

LORA_PINS = [8, 7]  # TX, RX
I2C_PINS = [39, 38]  # SCL, SDA
LIGHT_PINS = [6, 5]  # AI, DI
# grove pins via config

import sys
import time
import struct 
import machine
import json
import os

import bme688
import mpu6886
import display

from crcX25 import crc16_x25 as x25crc

from M5_LoraWan import M5_LoRaWAN

_CONF_FILE = "/config.json"

_LORA_FILE = "/lib/lora.json"


class MarsPlatz:
    def __init__(self, debug=False):
        self.debug = debug
        
        self.interrupt_flag = False
        
        # read config.json first 
        try:
            with open(_CONF_FILE) as f:
                self.config = json.load(f)
            if self.debug:
                print("Config loaded:", self.config)
        except:
            print("Config file problem")
            sys.exit()

        # config might have a value confif["io"]["btn"], try to get is and configure button if present
        self.btn = None
        if "io" in self.config and "btn" in self.config["io"]:
            btn_pin = self.config["io"]["btn"]
            self.btn = machine.Pin(btn_pin, machine.Pin.IN, machine.Pin.PULL_UP)
            if self.debug:
                print(f"Button configured on pin {btn_pin}")
            # set event handler for button press, if not already set. check if self.btn has an irq method
            if hasattr(self.btn, 'irq'):
                if self.debug:
                    print("Setting up button IRQ handler")
                # remove any existing irq handler first
                self.btn.irq(handler=None)
                # set new irq handler
                self.btn.irq(trigger=machine.Pin.IRQ_FALLING, handler=self.button_pressed)

        self.display = display.DisPlay(self.config)
        
        self.i2c = machine.I2C(1, scl=machine.Pin(I2C_PINS[0]), sda=machine.Pin(I2C_PINS[1]), freq=100000)
        self.light = machine.ADC(machine.Pin(LIGHT_PINS[0]))
        self.light.atten(machine.ADC.ATTN_11DB)  # Full range: 3.3v
        #self.lora_tx = machine.Pin(8, machine.Pin.OUT)
        #self.lora_rx = machine.Pin(7, machine.Pin.IN)
        self.env_addr = 0x77
        self.imu_addr = 0x68

        self.imu = mpu6886.MPU6886(self.i2c, self.imu_addr)
        self.env = bme688.BME68X_I2C(self.i2c, address=self.env_addr,debug=self.debug)

        
        # lora 
        self.lora = M5_LoRaWAN()
        self._init_lora()


    # declare button irq handler as instance method, so it can access self
    def button_pressed(self, pin):
        if self.debug:
            print("Button pressed!", pin)
        self.interrupt_flag = True


    def read_light(self):
        return self.light.read()

    def read_env(self):
        # Placeholder for reading from BME688 sensor
        # Actual implementation would involve I2C communication
        tmp = self.env.temperature
        hum = self.env.humidity
        prs = self.env.pressure
        aqi = self.env.gas
        return {"temperature": tmp, "humidity": hum, "pressure": prs, "aqi": aqi}

    def read_imu(self):
        # Placeholder for reading from MPU6886 sensor
        # Actual implementation would involve I2C communication
        acc = self.imu.acceleration
        gyro = self.imu.gyro
        return {"accel": acc, "gyro": gyro}

    def send_lora(self, data):
        # Placeholder for sending data via LoRa
        # Actual implementation would involve UART communication
        if self.debug:
            print(f"Sending data via LoRa: {data}")
        # we send the data struct here.
        # def send_msg(self, confirm, nbtrials, data):
        # self.lora.send_msg(1, 15, b"01020304abcd")
        self.lora.send_msg(1, 15, data)
        r = self.lora.wait_msg()
        if self.debug:
            print("LORA Received:", r)


    def _init_lora(self):
        if self.debug:
            print("Initializing LoRa module...")

        uart = machine.UART(1, tx=LORA_PINS[1], rx=LORA_PINS[0], baudrate=115200, bits=8, parity=None, stop=1, timeout=1000)
        self.lora.init(uart)
        time.sleep(0.1)
        if self.debug:
            print("Module Connect.....")
        while not self.lora.check_device_connect():
            pass
        self.lora.write_cmd("AT\r\n")
        time.sleep(0.1)
        #LoRaWAN.flush()

        # Disable Log Information # normally 0
        self.lora.write_cmd("AT+ILOGLVL=5\r\n")
        # Enable  Log Information
        self.lora.write_cmd("AT+CSAVE\r\n")
        self.lora.write_cmd("AT+IREBOOT=0\r\n")
        print("LoraWan Rebooting")
        time.sleep(1)

        if self.debug:
            print("LoraWan config")
        try:
            with open(_LORA_FILE) as f:
                loraCfg = json.load(f)
            if self.debug:
                print(loraCfg)
        except:
            print("LoraWan config problem")
            sys.exit()
        loraMode = loraCfg["mode"].lower()
        if self.debug:
            print("LoraWan mode:",loraMode)
        #    def config_abp(self, device_eui,device_addr, app_skey, net_skey, ul_dl_mode):
        if loraCfg["mode"].lower() == "abp":
            self.lora.config_abp(loraCfg["nwparms"]["devaddr"],
                            loraCfg["nwparms"]["appskey"],
                            loraCfg["nwparms"]["nwskey"],
                            "2"  # Upload Download Mode
            )
        elif loraCfg["mode"].lower() == "otaa":
            # Set Join Mode OTAA.
            #  def config_otta(self, device_eui, app_eui, app_key, ul_dl_mode):
            self.lora.config_otta(loraCfg["nwparms"]["deveui"],   # Device EUI
                            loraCfg["nwparms"]["appeui"],       # APP EUI
                            loraCfg["nwparms"]["appkey"],       # APP KEY
                            "2"  # Upload Download Mode
            )
        else:
            print("LoraWan mode problem")
            sys.exit()

        if self.debug:
            print("LoraWan config finished")
        

        response = self.lora.wait_msg(.5)
        print("response after join:", response)
        # Set ClassC mode
        # LoRaWAN.set_class("2")
        self.lora.set_class("2")
        self.lora.write_cmd("AT+CWORKMODE=2\r\n")

        # LoRaWAN868
        # TX Freq
        # 868.1 - SF7BW125 to SF12BW125
        # 868.3 - SF7BW125 to SF12BW125 and SF7BW250
        # 868.5 - SF7BW125 to SF12BW125
        # 867.1 - SF7BW125 to SF12BW125
        # 867.3 - SF7BW125 to SF12BW125
        # 867.5 - SF7BW125 to SF12BW125
        # 867.7 - SF7BW125 to SF12BW125
        # 867.9 - SF7BW125 to SF12BW125
        # 868.8 - FSK
        self.lora.set_freq_mask("0001")

        # 869.525 - SF9BW125 (RX2)              | 869525000
        self.lora.set_rx_window("869525000")
        if loraCfg["mode"].lower() == "otaa":
            self.lora.start_join()


if __name__ == "__main__":
    DEBUG = True
    mars_platz = MarsPlatz(debug=DEBUG)
    loopCnt = 0
    sensor_ID = 11  # Example sensor ID, can be changed as needed 
    mars_platz.display.fill((100,0,0))
    
    imgBuf = bytearray()

    def read_shorts_binary(filename, rows=100, cols=100):
        global imgBuf
        try:
            os.stat(filename)
        except:
            print("Image file not found")
            imgBuf = None
            return
        with open(filename, 'rb') as f:
            num_elements = rows * cols
            
            # Read all bytes at once
            raw_bytes = f.read(num_elements * 2)  # 2 bytes per int16
            
            # Unpack all values (little-endian signed short '<h')
            values = struct.unpack('<' + 'H' * num_elements, raw_bytes)
            
            # Reshape into 2D list of uint16 values
            arr = [list(values[i*cols:(i+1)*cols]) for i in range(rows)]
            for y in range(100):
                for x in range(100):
                    pixval = arr[y][x]
                    imgBuf.append((pixval >> 8) & 0xff)
                    imgBuf.append(pixval & 0xff)


    def showImage(imgBuf, offs_x = 0, offs_y = 0, shape=(100,100)):
        if imgBuf is not None:
            print("Showing image using bit blitting")
            # def blit_buffer(self, buffer, x, y, width, height):
            mars_platz.display.blit_buffer(imgBuf, offs_x, offs_y, shape[1], shape[0])

    # try to read image from file
    read_shorts_binary("marsplatz3.bin",100,100)
    if imgBuf:
        print("Image shape: ",len(imgBuf))
    else:
        print("Image not found")
    
    while True:
        mars_platz.display.fill((0,0,100))
        light_value = mars_platz.read_light()
        env_data = mars_platz.read_env()
        imu_data = mars_platz.read_imu()
        
        print(f"Light: {light_value}, Env: {env_data}, IMU: {imu_data}")

        # Prepare data for transmission
        orientation = [int(imu_data["accel"][0] + 16) & 0xff, int(imu_data["accel"][1] + 16) & 0xff, int(imu_data["accel"][2] + 16) & 0xff]
        data_packet = {
            "light": int(light_value) // 16,  # Scale down to fit in 8 bits
            "temp": int(env_data["temperature"]),
            "pres": int(env_data["pressure"]),
            "co2": int(env_data["aqi"] // 100),
            "hum": int(env_data["humidity"]),
            "imu_x": orientation[0],
            "imu_y": orientation[1],
            "imu_z": orientation[2],
            "cnt": loopCnt
        }
        if DEBUG:
            print("Data packet:", data_packet)
        # convert data_packet to a byte array for transmission
        
        # old reference: struct.pack("!BBBBHHHHH",id,fmt,0,0,cnt,temp,hum,co2,pres)
        # ! is network byte order (big-endian), > is explicit big endian 
        dataFormat = 2 
        data_packet_bytes = struct.pack('!BBBBHHHHHHHHH',
            sensor_ID,  # Sensor ID                                            
            dataFormat,  # Data format version
            0,  # Reserved
            0,  # Reserved
            # unsigned short 
            data_packet["cnt"],
            data_packet["light"],
            int(data_packet["temp"] + 273),  # add Kelvin conversion
            int(data_packet["hum"]),
            data_packet["co2"],
            int(data_packet["pres"]),    # Convert to deci-Pascals
            # new items
            data_packet["imu_x"],
            data_packet["imu_y"],
            data_packet["imu_z"],
        )
        crc_ = x25crc(data_packet_bytes)
        crc = struct.pack("!H",crc_)
        if DEBUG:
            print("Data packet bytes:", data_packet_bytes.hex())
            print("CRC:", hex(crc_))
        sensData = bytes(list(data_packet_bytes)) + bytes(list(crc))
        # current format is 22 bytes of data + 2 bytes of CRC = 24 bytes total
        if DEBUG:
            print("Final sensData:", sensData.hex(), len(sensData))

        # Send data via LoRa
        mars_platz.send_lora(sensData)

        loopCnt += 1

        mars_platz.display.fill((0,100,0))
        time.sleep(1)        
        mars_platz.display.fill((0,0,100))
        # show image 
        showImage(imgBuf,14,14,(100,100))

        # Wait before next reading
        for i in range(20 * 60):
            if mars_platz.interrupt_flag:
                print("Interrupt detected, breaking sleep.")
                mars_platz.interrupt_flag = False
                break
            time.sleep(1)
        # time.sleep(10*60)  # Removed redundant sleep as the loop above already handles the delay
        

""" CRC check like so
    payload_format = "!BBBBHHHHHH"
    payload_sc = struct.unpack(payload_format, payload)
    print(payload_sc)
    crc_rx = payload_sc[-1]
    print("Received CRC: ",crc_rx)
    # probably arduino library uses x25 crc algorithm
    crc = x25crc(payload[:14])
    print("Computed crc:",crc)

    if crc == crc_rx:
        print("CRC matching")
        return True
    else:
        print("CRC error")
        return False
"""
        
        
"""
use with element platform.

take device id and api key from private_marsplatz.py at /home/kugel/temp/m5/lorawanAsr5601

geräteinfo
 curl -i -H "Accept: application/json" -H "Content-Type: application/json" -X GET 'https://iot.skd-ka.de/api/v1/devices/<device-id>?auth=<api-key>' 

letztes paket (probably down)
curl -i -H "Accept: application/json" -H "Content-Type: application/json" -X GET 'https://iot.skd-ka.de/api/v1/devices/<device-id>/packets?limit=1&sort=transceived_at&sort_direction=desc&auth=<api-key>' 

letzte 2
curl -i -H "Accept: application/json" -H "Content-Type: application/json" -X GET 'https://iot.skd-ka.de/api/v1/devices/<device-id>/packets?limit=2&sort=transceived_at&sort_direction=desc&auth=<api-key>' 

letzte 10
curl -i -H "Accept: application/json" -H "Content-Type: application/json" -X GET 'https://iot.skd-ka.de/api/v1/devices/<device-id>/packets?limit=10&sort=transceived_at&sort_direction=desc&auth=<api-key>' 

--------
actions
- streams
name
gerät auswählen


- regeln
stream: name des geräts
event: paket hinzugefügt
bedingung: true

action:
http anfrage senden
post
https://critical-sensors.de/mrsplz-test.php


statt ganzes ereignis als json:
{"Payload":"{{payload}}","PacketType":"{{packet_type}}","Date":"{{transceived_at}}","DeviceId":"{{device_id}}"}


"""
        