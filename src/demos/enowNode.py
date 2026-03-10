import network
import json 
import time
import machine
import espnow
import asyncio
import os 

from micropython import const
import random
import struct

CHAN = 5

# config stuff
_CONF_FILE = "config.json"
files = os.listdir("/")
if _CONF_FILE in files:
    with open(_CONF_FILE) as f:
        cfdata = json.load(f)
        this_device = cfdata["id"]
        print("Device ID:", this_device)
else:
    raise BaseException("No Config")        

import display
disp = display.DisPlay(cfdata)
disp.fill((0,200,0))

try:
    network.WLAN().disconnect() # disconnect from any existing wifi connection
except OSError:
    pass

# A WLAN interface must be active to send()/recv()
sta = network.WLAN(network.WLAN.IF_STA)
sta.active(True)
while not sta.active():
    time.sleep(1)
sta.config(channel=CHAN)    # Change to the channel used by the proxy above.
sta.config(pm=sta.PM_NONE) # disable power save to prevent wifi disconnects during sleep

e = espnow.ESPNow()  # Returns ESPNow enhanced with async support
e.active(True)

SERVER = bytes.fromhex("dc5475c89604")
e.add_peer(SERVER)
disp.fill((0,0,100))
    

def push(e):
    if not e.send(SERVER, b'ping'):
        print("Push: peer not responding:", SERVER)
        disp.fill((200,0,0))
        time.sleep(0.3)
        disp.fill((0,0,0))
    else:
        print("Push: ping", SERVER)
        disp.fill((0,200,0))
        time.sleep(0.3)
        disp.fill((0,0,0))


def main(e, period):
    while True:
        push(e)
        host, msg = e.recv(200)
        if msg:             # msg == None if timeout in recv()
            print(host, msg)
            if msg == b'end':
                break

            disp.fill((0,0,200))
            time.sleep(0.3)
            disp.fill((0,0,0))

        time.sleep(period)


main(e, 5 )

