# SPDX-License-Identifier: AGPL-3.0-only
# espnow_client_example.py
# Replace the values with /espnow.json from the AtomS3U.

import time
import json
import binascii
import network
import espnow

S3U_SERVER = "30eda0c9de44"
S3U_KEY = "cc2747dbf3011774c798f77348969a45"
SHARED_KEY = bytes.fromhex(S3U_KEY[:32])
print("Shared key:", SHARED_KEY.hex())
WIFI_CHANNEL = 5

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
