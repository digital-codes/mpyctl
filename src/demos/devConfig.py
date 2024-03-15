""" read/write config"""
import json
import machine
import os
import network
import bluetooth
import hashlib
import random

_SALT = f"{random.randint(100000,999999):06}"
_CONF_FILE = "config.json"

def generate_key(mac_address):
    """Generate a 6-digit key from a MAC address."""
    code = "".join([mac_address,_SALT])
    hash = hashlib.sha256(code.encode()).digest().hex()
    key = str(int(hash, 16))[-6:] # Get the last 6 digits
    return f"{key:06}"  # Pad with zeros if necessary

class Config:
    def __init__(self, data=None):
        self.dirty = True # true if the config has been modified
        if data == None:    
            self.io = {}  # no default io definition
            self.device = -1  # no default device
            self.model = ""  # no default model
            self.id = machine.unique_id().hex()
            o = os.uname()
            self.os = {"release": o.release, "machine": o.machine}
            b = bluetooth.BLE()
            b.active(1)
            bmac = b.config("mac")[1].hex()
            bkey = generate_key(bmac)
            self.ble = {"key": bkey, "addr": bmac}
            w = network.WLAN()
            self.wlan = {"addr": w.config("mac").hex()}
        elif isinstance(data, dict):
            self.io = data.get('io')
            self.device = data.get('device')
            self.model = data.get('model')
            if data.get('id', "") == machine.unique_id().hex():
                self.dirty = False
                self.id = data.get('id')
                self.os = data.get('os')
                self.ble = data.get('ble')
                self.wlan = data.get('wlan')
            else:
                self.id = machine.unique_id().hex()
                self.os = {"release": os.uname().release, "machine": os.uname().machine}
                self.ble = {"key": generate_key(bluetooth.BLE().config("mac")[1].hex()), "addr": bluetooth.BLE().config("mac")[1].hex()}
                self.wlan = {"addr": network.WLAN().config("mac").hex()}
        else:
            raise ValueError("Invalid data type")

    def __str__(self):
        """don't include dirty flag in string"""
        cfg = {}
        for k in self.__dict__.keys():
            if k != "dirty":
                cfg[k] = self.__dict__[k]
        return json.dumps(cfg)

    # Getters and Setters
    def set_io(self, io):
        self.io = io

    def set_model(self, model):
        self.model = model

    def get_dirty(self):
        return self.dirty



def main():
    # Test the Config class
    cfg = Config()  # Create a new config
    print(f"New config: {cfg}")

    files = os.listdir("/")
    if _CONF_FILE in files:
        with open(_CONF_FILE) as f:
            cfdata = json.load(f)
        cfg = Config(cfdata)
        print("From old config:",cfg)
        if cfg.get_dirty():
            print("Config dirty")
        else:
            print("Config clean")


if __name__ == "__main__":
    main()

