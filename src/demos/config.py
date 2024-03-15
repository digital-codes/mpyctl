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

files = os.listdir("/")

if _CONF_FILE in files:
    with open(_CONF_FILE) as f:
        cfg = json.load(f)

    print("Old config")

else:
    cfg = {}
    cfg["io"] = {} # no default io definition 
    cfg["device"] = -1 # no default device
    cfg["model"] = "" # no default model

    cfg["id"] = machine.unique_id().hex()
    o = os.uname()
    cfg["os"] = {"release":o.release,"machine":o.machine}

    b = bluetooth.BLE()
    b.active(1)
    bmac = b.config("mac")[1].hex()
    bkey = generate_key(bmac)
    cfg["ble"] = {"key":bkey,"addr":bmac}
    w = network.WLAN()
    cfg["wlan"] = {"addr":w.config("mac").hex()}

    print("New config")

print(f"Config: {cfg}")
