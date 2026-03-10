import network
import json 
import time
import machine
import aioespnow
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
disp.fill((200,0,0))

_PEER_FILE = "peers.json"
if _PEER_FILE in files:
    with open(_PEER_FILE) as f:
        peers = json.load(f)
else:
    print("No peer file, starting with dummy/empty peer list")
    peers = [bytes.fromhex("94b97e92b81c")]


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

e = aioespnow.AIOESPNow()  # Returns AIOESPNow enhanced with async support
e.active(True)

for peer in peers:
    e.add_peer(peer)
    print("Added peer:", peer)
    


# Send a periodic ping to a peer
async def heartbeat(e, peers, period=30):
    while True:
        for peer in peers:
            if not await e.asend(peer, b'ping'):
                print("peer not responding:", peer)
                disp.text("Fail   ",10,10)
            else:
                print("Heartbeat: ping", peer)
                disp.text("OK       ",10,10)
            await asyncio.sleep(0.3) # small delay between pings to different peers
            disp.text("          ",10,10)
        await asyncio.sleep(period)

# Echo any received messages back to the sender
async def echo_server(e):
    async for mac, msg in e:
        print("Echo:", msg)
        
        try:
            await e.asend(mac, msg)
        except OSError as err:
            if len(err.args) > 1 and err.args[1] == 'ESP_ERR_ESPNOW_NOT_FOUND':
                e.add_peer(mac)
                await e.asend(mac, msg)
                disp.text(f"New {mac}",10,30)

async def main(e, peers, timeout, period):
    asyncio.create_task(heartbeat(e, peers, period))
    asyncio.create_task(echo_server(e))
    while True:
        await asyncio.sleep(timeout)

asyncio.run(main(e, peers, 120 , 5 )) #  120, 10))

