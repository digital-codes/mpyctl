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

import bme688
import mpu6886
import display

from M5_LoraWan import M5_LoRaWAN

_CONF_FILE = "/config.json"

_LORA_FILE = "/lib/lora.json"


class MarsPlatz:
    def __init__(self, debug=False):
        self.debug = debug
        
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


    # declare button irq handler as static method, so it can be used as a callback
    @staticmethod
    def button_pressed(pin):
        print("Button pressed!",pin)


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
            self.lora.config_abp(loraCfg["nwparms"]["deveui"],   # Device EUI
                loraCfg["nwparms"]["devaddr"],
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
    mars_platz = MarsPlatz(debug=True)
    while True:
        light_value = mars_platz.read_light()
        env_data = mars_platz.read_env()
        imu_data = mars_platz.read_imu()
        
        print(f"Light: {light_value}, Env: {env_data}, IMU: {imu_data}")

        time.sleep(3)  # Simulate sensor reading delay

        continue
    
        # Prepare data for transmission
        data_packet = {
            "light": light_value,
            "env": env_data,
            "imu": imu_data
        }

        # Send data via LoRa
        mars_platz.send_lora(data_packet)

        # Display data on LCD (if applicable)
        display.show(data_packet)

        # Wait before next reading
        time.sleep(5)        
        
        
        
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
        