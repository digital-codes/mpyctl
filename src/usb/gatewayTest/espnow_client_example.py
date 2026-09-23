# SPDX-License-Identifier: AGPL-3.0-only
# espnow_client_example.py
#
# ESP-NOW test client. Runs on a SECOND ESP32 board (not the gateway).
#
# Sends a short test message to the server every 5 seconds:
#   on-air payload = 16-byte shared key header + "sensor message <n>"
#
# Configuration:
#   private.py   : ENOW_SERVER (server MAC hex), ENOW_KEY (hex, its first
#                  16 bytes become the PMK and the message header),
#                  ENOW_CHANNEL (Wi-Fi channel to join)
#   config.json  : ble.key (hex) used as the LMK for encrypted unicast to
#                  the registered server peer. Without it traffic is sent
#                  unencrypted.
#
# The server must have this board registered via enableNode()/peers.json
# with the same LMK.

import time
import json
import binascii
import network
import espnow

# get channel, secret key and server mac from private.py
import private as pr
S3U_SERVER = pr.ENOW_SERVER
S3U_KEY = pr.ENOW_KEY
WIFI_CHANNEL = pr.ENOW_CHANNEL

SHARED_KEY = bytes.fromhex(S3U_KEY[:32])
print("Shared key:", SHARED_KEY.hex())

try:
    with open("config.json", "r") as f:
        config = json.load(f)
        print("Config:", config)
except Exception as e:
    print("Failed to load config.json:", e)
    config = {}

# set lmk from key
LMK = bytes.fromhex(config["ble"]["key"]) if "ble" in config and "key" in config["ble"] else None
if LMK:
    print("Using secure ESPNOW with LMK:", LMK.hex())

# Test: reset LMK
# LMK = None


wlan = network.WLAN(network.WLAN.IF_STA)
try:
    wlan.disconnect()
except Exception:
    pass

wlan.active(True)
while not wlan.active():
    print("Waiting for WLAN to become active...")

try:
    wlan.config(channel=WIFI_CHANNEL)
    wlan.config(pm=wlan.PM_NONE) # disable power save to prevent wifi disconnects during sleep
except Exception:
    pass


print("WLAN channel: %d" % WIFI_CHANNEL)

radio = espnow.ESPNow()
radio.active(True)
radio.set_pmk(SHARED_KEY)




SERVER_MAC = bytes.fromhex(S3U_SERVER)
if LMK != None:
    radio.add_peer(SERVER_MAC, LMK, channel=WIFI_CHANNEL)
else:
    radio.add_peer(SERVER_MAC, channel=WIFI_CHANNEL)

counter = 0
while True:
    hdr = SHARED_KEY[:16]
    print("Sending header:", hdr.hex())
    payload = hdr + ("sensor message %d" % counter).encode()
    print("Sending message %d" % counter)
    
    s = radio.send(
        SERVER_MAC,
        payload,
    )
    print("Send result:", s)
    counter += 1
    time.sleep(5)
