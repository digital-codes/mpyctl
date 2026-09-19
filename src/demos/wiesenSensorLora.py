from machine import I2C, ADC, UART
from co2l import CO2LUnit
from colorRgb import TCS3472
from M5_LoraWan import M5_LoRaWAN
from crcX25 import crc16_x25 as x25crc
from machine import lightsleep, deepsleep, reset


import json
import time
import struct

LORA_PINS = [6,5]  # TX, RX
BAT_PIN = 8  # ADC pin for battery voltage measurement
COLOR_PINS = [4, 3]  # SCL, SDA for color sensor
CO2_PINS = [1, 2]  # SCL, SDA for CO2 sensor

_CONF_FILE = "/config.json"

_LORA_FILE = "/lib/lora.json"


class WieseLora:
    def __init__(self):
        self.debug = True
        self.lora = None
        self.co2 = None
        self.rgb = None
        self.battery_adc = ADC(BAT_PIN)
        self.config = self.load_config()
        
        # check battery first. if we  are below 3.8, enter lightsleep for 10 minutes to save power, then retry. If we are below 3.5, enter deep sleep for 1 hour to save power, then retry.
        bat_ok = False
        while not bat_ok:
            bat_voltage = self.get_battery_voltage()
            if self.debug:
                print("Battery voltage: {:.2f} V".format(bat_voltage))
            if bat_voltage < 3.5:
                print("Battery voltage below 3.5V, entering deep sleep for 1 hour to save power.")
                deepsleep(60 * 60 * 1000)  # Convert seconds to milliseconds for deep sleep
                # this gives a reset after 1 hour, and the code will start from the beginning, checking battery voltage again.
            elif bat_voltage < 3.8:
                print("Battery voltage below 3.8V, entering lightsleep for 10 minutes to save power.")
                lightsleep(10 * 60 * 1000)  # Convert seconds to milliseconds for lightsleep
            else:
                bat_ok = True
        
        
        self._initCO2Sensor()
        self._initColorSensor()
        # lora 
        self.lora = M5_LoRaWAN()
        try:
            self._init_lora()
        except Exception as e:
            print("Error initializing LoRa:", e)
            time.sleep(5)
            reset()

    def load_config(self):
        try:
            with open(_CONF_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print("Error loading config:", e)
            return {}

    def get_battery_voltage(self):
        # read battery voltage in volts. battery has a voltage divider of 2:1, so multiply by 2. ADC returns value in range 0-4095 for 0-3.3V, so multiply by 3.3/4095 to get volts
        return self.battery_adc.read_uv() * 2 / 1000000

    def _initColorSensor(self):
        i2 = I2C(1, scl=COLOR_PINS[0], sda=COLOR_PINS[1], freq=400000)
        i2.scan()
        self.rgb = TCS3472(i2)
        
    def _initCO2Sensor(self):
        i1 = I2C(0, scl=CO2_PINS[0], sda=CO2_PINS[1], freq=400000)
        i1.scan()
        self.co2 = CO2LUnit(i1)
        self.co2.reinit()
        self.co2.get_serial_number()

    def _init_lora(self):
        if self.debug:
            print("Initializing LoRa module...")

        uart = UART(1, tx=LORA_PINS[1], rx=LORA_PINS[0], baudrate=115200, bits=8, parity=None, stop=1, timeout=1000)
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


    def get_co2(self):
        self.co2.set_single_shot_measurement_all()
        # set single shot has built-in wait
        if self.co2.is_data_ready():
            try:
                gas = self.co2.co2
                tmp = self.co2.temperature
                hum = self.co2.humidity
                return gas, tmp, hum
            except Exception as e:
                print("Error reading CO2 sensor:", e)

        return None, None, None        

    def getColor(self):
        try:
            self.rgb.set_active(True)
            time.sleep(0.1)
            self.rgb.set_integration_time(2.4)
            time.sleep(0.1)
            cols = self.rgb.get_color_rgb_bytes()
            lux = self.rgb.get_lux()
            ct = self.rgb.get_color_temperature()
            self.rgb.set_active(False)
            return cols, lux, ct
        except Exception as e:
            print("Error reading color sensor:", e)
            return None, None, None
    
    def prepareDataPacket(self, sensor_ID, bat, co2_val, temp, rh, rgb, lux, loopCnt):
        # Prepare data for transmission
        if lux < 0:
            light_value = 0
        elif lux > 32767:
            light_value = 32767
        else:
            light_value = int(lux)
        data_packet = {
            "light": int(light_value) // 256,  # limited to 8 bit, comaptible with others
            "temp": int((float((temp)) + 273.0) * 10.0),  # add Kelvin conversion and scale up
            "pres": int(0), # not available here 
            "bat": int(bat * 10),  # scale up
            "co2": int(co2_val),
            "hum": int(rh),
            "r": rgb[0],
            "g": rgb[1],
            "b": rgb[2],
            "cnt": loopCnt
        }
        if self.debug:
            print("Data packet:", data_packet)
        # convert data_packet to a byte array for transmission
        
        # old reference: struct.pack("!BBBBHHHHH",id,fmt,0,0,cnt,temp,hum,co2,pres)
        # ! is network byte order (big-endian), > is explicit big endian 
        dataFormat = 2 
        data_packet_bytes = struct.pack('!BBBBHHHHHHHHH',
            sensor_ID,  # Sensor ID                                            
            dataFormat,  # Data format version
            data_packet["bat"],  # Reserved use for battery voltage
            0,  # Reserved
            # unsigned short 
            data_packet["cnt"],
            data_packet["light"],
            int(data_packet["temp"]),
            int(data_packet["hum"]),
            data_packet["co2"],
            int(data_packet["pres"]),    # Convert to deci-Pascals
            # new items
            data_packet["r"],
            data_packet["g"],
            data_packet["b"],
        )
        crc_ = x25crc(data_packet_bytes)
        crc = struct.pack("!H",crc_)
        if self.debug:
            print("Data packet bytes:", data_packet_bytes.hex())
            print("CRC:", hex(crc_))
        sensData = bytes(list(data_packet_bytes)) + bytes(list(crc))
        # current format is 22 bytes of data + 2 bytes of CRC = 24 bytes total
        if self.debug:
            print("Final sensData:", sensData.hex(), len(sensData))

        return sensData

    
if __name__ == "__main__":
    wiese = WieseLora()
    loopCnt  = 0
    sensor_ID = 2  # Example sensor ID, can be changed as needed 

    while True:
        try:
            bat = wiese.get_battery_voltage()
            if wiese.debug:
                    print("Battery voltage: {:.2f} V".format(bat))
            co2_val, temp, rh = wiese.get_co2()
            if co2_val is not None:
                if wiese.debug:
                    print("CO2: {} ppm, Temp: {:.2f} C, RH: {:.2f} %".format(co2_val, temp, rh))
            else:
                print("CO2 data not ready")
            rgb, lux, ct = wiese.getColor()
            if rgb is not None:
                if wiese.debug:
                    print("Color sensor data: R={}, G={}, B={}, Lux={:.2f}, Color Temp={:.2f}".format(rgb[0], rgb[1], rgb[2], lux, ct))
            else:
                print("Color sensor data not ready")
                
            # Prepare data packet for LoRa transmission
            if bat is not None and co2_val is not None and rgb is not None and lux is not None:
                payload = wiese.prepareDataPacket(sensor_ID, bat, co2_val, temp, rh, rgb, lux, loopCnt)
                loopCnt += 1
                wiese.send_lora(payload)
        except Exception as e:
            print("Error in main loop:", e)
            
        lightsleep(10 * 60 * 1000)  # Convert seconds to milliseconds for lightsleep
        
        