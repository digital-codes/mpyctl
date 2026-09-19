import time

class M5_LoRaWAN:
    def __init__(self):
        self._serial = None

    def init(self, serial):
        self._serial = serial
        # self._serial.init(115200, bits=8, parity=None, stop=1, rx=RX, tx=TX)
        #self._serial.flush()

    def flush(self):
        return
        self._serial.flush()

    def check_device_connect(self):
        restr = self.write_cmd("AT+CGMI?\r\n")
        if restr.find("OK") == -1:
            return False
        else:
            return True

    def check_join_status(self):
        restr = self.write_cmd("AT+CSTATUS?\r\n")
        if restr.find("+CSTATUS:") != -1:
            if restr.find("03") != -1 or restr.find("07") != -1 or restr.find("08") != -1:
                return True
            else:
                return False
        else:
            return False

    def wait_msg(self, wt = 5):
        restr = ""
        start = time.time()
        while True:
            if (time.time() - start) < wt:
                data = self._serial.readline()
                if data:
                    str_data = data.decode()
                    restr += str_data
            else:
                break
        print("Resp:",restr)
        return restr

    def write_cmd(self, command):
        print("CMD:",command)
        self._serial.write(command.encode())
        time.sleep(0.1)
        return self.wait_msg(1)

    def send_msg(self, confirm, nbtrials, data):
        if type(data) == str:
            encoded_data = self.encode_msg(data)
        elif type(data) == bytes:
            encoded_data = data.hex()
        else:
            print("Data type not supported")
            return
        cmd = "AT+DTRX=" + str(confirm) + ',' + str(nbtrials) + ',' + str(len(encoded_data)//2) + ',' + encoded_data + "\r\n"
        self.write_cmd(cmd)

    def receive_msg(self):
        restr = self.wait_msg(2000)
        if restr.find("OK+RECV:") != -1 and restr.find("02,00,00") == -1:
            data = restr[restr.find("OK+RECV:") + 17:-2]
            return self.decode_msg(data)
        else:
            return ""

    def config_otta(self, device_eui, app_eui, app_key, ul_dl_mode):
        self.write_cmd("AT+CJOINMODE=0\r\n")
        self.write_cmd("AT+CDEVEUI=" + device_eui + "\r\n")
        self.write_cmd("AT+CAPPEUI=" + app_eui + "\r\n")
        self.write_cmd("AT+CAPPKEY=" + app_key + "\r\n")
        self.write_cmd("AT+CULDLMODE=" + ul_dl_mode + "\r\n")

    def config_abp(self, device_addr, app_skey, net_skey, ul_dl_mode):
        self.write_cmd("AT+CJOINMODE=1\r\n")
        self.write_cmd("AT+CDEVADDR=" + device_addr + "\r\n")
        self.write_cmd("AT+CAPPSKEY=" + app_skey + "\r\n")
        self.write_cmd("AT+CNWKSKEY=" + net_skey + "\r\n")
        self.write_cmd("AT+CULDLMODE=" + ul_dl_mode + "\r\n")

    def set_class(self, mode):
        self.write_cmd("AT+CCLASS=" + mode + "\r\n")

    def set_rx_window(self, freq):
        self.write_cmd("AT+CRXP=0,0," + freq + "\r\n")

    def set_freq_mask(self, mask):
        self.write_cmd("AT+CFREQBANDMASK=" + mask + "\r\n")

    def start_join(self):
        #self.write_cmd("AT+CJOIN=1,0,10,8\r\n")
        # last parm is max retries
        self.write_cmd("AT+CJOIN=1,0,10,100\r\n")

    def encode_msg(self, str):
        buf = bytearray(str, 'utf-8')
        tempbuf = bytearray((len(buf) * 2))
        i = 0
        for p in buf:
            tempbuf[i] = p
            i += 1
        return tempbuf.hex()

    def decode_msg(self, hex_encoded):
        if len(hex_encoded) % 2 == 0:
            buf = bytearray.fromhex(hex_encoded)
            tempbuf = bytearray(len(buf))
            i = 0
            for loop in range(2, len(hex_encoded) + 1, 2):
                tmpstr = hex_encoded[loop - 2:loop]
                tempbuf[i] = int(tmpstr, 16)
                i += 1
            return tempbuf.decode()
        else:
            return hex_encoded
