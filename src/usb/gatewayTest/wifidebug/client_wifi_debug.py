# client_wifi_debug.py
# WiFi debug client for MicroPython device (ESP32)
# Connects to WiFi AP, sends 5 packets with 5s delay
# No peer management, no strict key checking

import time
import network
import socket

WIFI_SSID = "MPY"
WIFI_PASSWORD = "0102030405060708090a0b0c0d0e0f"
WIFI_CHANNEL = 3
SERVER_PORT = 8080
SHARED_KEY = bytes.fromhex("00112233445566778899aabbccddeeff")

print("=" * 60)
print("DEBUG WiFi Client - MicroPython Device")
print("=" * 60)
print("DEBUG: SSID:", WIFI_SSID)
print("DEBUG: Server port:", SERVER_PORT)
print("DEBUG: Shared key:", SHARED_KEY.hex())

# Connect to WiFi
print("DEBUG: Connecting to WiFi...")
wlan = network.WLAN(network.STA_IF)
wlan.active(False)
time.sleep(1)
wlan.active(True)

while not wlan.active():
    print("DEBUG: Waiting for WiFi to activate...")
    time.sleep(1)

try:
    wlan.config(channel=WIFI_CHANNEL)
except Exception as e:
    print("DEBUG: Channel config:", e)

try:
    wlan.config(pm=wlan.PM_NONE)
except Exception as e:
    print("DEBUG: PM config:", e)

print("DEBUG: Connecting to AP...")
wlan.connect(WIFI_SSID, WIFI_PASSWORD)  # WPA2 auth
while not wlan.isconnected():
    print("DEBUG: Waiting for connection...")
    for _ in range(10):
        if wlan.isconnected():
            break
        time.sleep(1)

print("DEBUG: Connected!")
ip_config = wlan.ifconfig()
print("DEBUG: IP:", ip_config[0])
print("DEBUG: Gateway:", ip_config[2])
SERVER_IP = ip_config[2]
print("DEBUG: Server IP:", SERVER_IP)

# Connect to server
print("=" * 60)
print("DEBUG: Connecting to server...")
print("=" * 60)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.connect((SERVER_IP, SERVER_PORT))
    sock.settimeout(0)
    print("DEBUG: Connected to server!")
except Exception as e:
    print("DEBUG: Connection failed:", e)
    sock = None

received_count = 0
sent_count = 0

def receive_messages():
    global received_count
    if sock is None:
        return
    
    try:
        sock.setblocking(False)
        data = sock.recv(1024)
        if data:
            received_count += 1
            print("DEBUG: ============================================")
            print("DEBUG: RECEIVED from server")
            print("DEBUG: Raw bytes:", data)
            print("DEBUG: Raw hex:", data.hex())
            print("DEBUG: Length:", len(data))
            try:
                print("DEBUG: Decode:", data.decode('utf-8'))
            except Exception as e:
                print("DEBUG: Decode error:", e)
    except OSError:
        pass  # No data
    except Exception as e:
        print("DEBUG: Receive error:", e)

# Main loop - send 5 messages with 5s delay
counter = 0
max_messages = 5

while counter < max_messages:
    print("=" * 60)
    print("DEBUG: Message", counter, "of", max_messages)
    print("=" * 60)

    if sock is None:
        print("DEBUG: Trying to reconnect...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_IP, SERVER_PORT))
            sock.settimeout(0)
            print("DEBUG: Reconnected!")
        except Exception as e:
            print("DEBUG: Reconnect failed:", e)
            time.sleep(5)
            continue

    # Send message
    message = "sensor message %d" % counter
    payload = SHARED_KEY[:16] + message.encode()
    
    print("DEBUG: Sending:", message)
    print("DEBUG: Full payload (hex):", payload.hex())
    print("DEBUG: Payload length:", len(payload))
    
    try:
        sent = sock.send(payload)
        sent_count += 1
        print("DEBUG: Send result:", sent, "bytes")
    except Exception as e:
        print("DEBUG: Send error:", e)
        sock = None
        time.sleep(1)
        continue

    # Check for responses for a short time
    print("DEBUG: Waiting for response...")
    for _ in range(50):  # Check for 5 seconds
        receive_messages()
        time.sleep(0.1)

    counter += 1
    
    if counter < max_messages:
        print("DEBUG: Waiting 5 seconds before next message...")
        for _ in range(50):
            receive_messages()
            time.sleep(0.1)

print("=" * 60)
print("DEBUG: Done sending all messages!")
print("DEBUG: Stats - Sent:", sent_count, "Received:", received_count)
print("=" * 60)

# Final receive check
print("DEBUG: Final receive check...")
for _ in range(20):
    receive_messages()
    time.sleep(0.1)

if sock:
    try:
        sock.close()
    except:
        pass

print("DEBUG: Exiting")
