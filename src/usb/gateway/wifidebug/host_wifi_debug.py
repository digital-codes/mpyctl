#!/usr/bin/env python3
# host_wifi_debug.py
# WiFi debug client for Linux host
# Connects to WiFi AP server, sends 5 packets with 5s delay
# No peer management, no strict key checking

import socket
import time
import sys
import argparse
import subprocess
import re

SERVER_PORT = 8080
SHARED_KEY = bytes.fromhex("00112233445566778899aabbccddeeff")
MESSAGE_COUNT = 5
MESSAGE_DELAY = 5
SERVER_IP = ""

def get_interface_for_ip(target_ip):
    """Auto-detect interface that can reach target IP."""
    try:
        result = subprocess.run(
            ["ip", "route", "get", target_ip],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout
        match = re.search(r'dev\s+(\S+)', output)
        if match:
            iface = match.group(1)
            print(f"DEBUG: Auto-detected interface: {iface}")
            return iface
    except Exception as e:
        print(f"DEBUG: Auto-detect failed: {e}")
    return None

def get_ifconfig(interface):
    """Get IP config for interface using ifconfig."""
    try:
        result = subprocess.run(
            ["ifconfig", interface],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout
        match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(\d+\.\d+\.\d+\.\d+)', output)
        if match:
            ip = match.group(1)
            netmask = match.group(2)
            return ip, netmask
    except Exception as e:
        print(f"DEBUG: ifconfig failed: {e}")
    return None, None

parser = argparse.ArgumentParser(description="WiFi debug client")
parser.add_argument("-i", "--interface", help="Network interface (e.g., wlan0, eth0)")
parser.add_argument("-s", "--server-ip", default="", help="Server IP address (default: auto-detect from interface)")
parser.add_argument("-p", "--port", type=int, default=SERVER_PORT, help="Server port")
args = parser.parse_args()

# Detect interface
interface = args.interface
if not interface:
    interface = get_interface_for_ip(SERVER_IP)
    if not interface:
        print("ERROR: Could not auto-detect interface. Use -i option.")
        sys.exit(1)

local_ip, netmask = get_ifconfig(interface)
if not local_ip:
    print(f"ERROR: Could not get IP for interface {interface}")
    sys.exit(1)

# Derive server IP (gateway = .1 of local subnet)
local_parts = [int(x) for x in local_ip.split('.')]
server_ip = f"{local_parts[0]}.{local_parts[1]}.{local_parts[2]}.1"
SERVER_IP = args.server_ip if args.server_ip else server_ip
SERVER_PORT = args.port

print("=" * 60)
print("DEBUG WiFi Client - Linux Host")
print("=" * 60)
print(f"DEBUG: Interface: {interface}")
print(f"DEBUG: Local IP: {local_ip}, Netmask: {netmask}")
print(f"DEBUG: Server (gateway): {SERVER_IP}:{SERVER_PORT}")
print("DEBUG: Shared key:", SHARED_KEY.hex())

# Connect to server
print("=" * 60)
print("DEBUG: Connecting to server...")
print("=" * 60)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.connect((SERVER_IP, SERVER_PORT))
    sock.settimeout(0.1)
    print("DEBUG: Connected to server!")
except Exception as e:
    print("DEBUG: Connection failed:", e)
    sys.exit(1)

received_count = 0
sent_count = 0

def receive_messages():
    global received_count
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
            print("DEBUG: Decode:", data.decode('utf-8', errors='replace'))
    except BlockingIOError:
        pass  # No data
    except Exception as e:
        print("DEBUG: Receive error:", e)

# Main loop - send 5 messages with 5s delay
counter = 0

while counter < MESSAGE_COUNT:
    print("=" * 60)
    print("DEBUG: Message", counter, "of", MESSAGE_COUNT)
    print("=" * 60)

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
        print("DEBUG: Trying to reconnect...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_IP, SERVER_PORT))
            sock.settimeout(0.1)
            print("DEBUG: Reconnected!")
            sent = sock.send(payload)
            sent_count += 1
            print("DEBUG: Send after reconnect:", sent, "bytes")
        except Exception as e2:
            print("DEBUG: Reconnect failed:", e2)
            time.sleep(1)
            continue

    # Check for responses for a short time
    print("DEBUG: Waiting for response...")
    for _ in range(50):  # Check for 5 seconds
        receive_messages()
        time.sleep(0.1)

    counter += 1
    
    if counter < MESSAGE_COUNT:
        print("DEBUG: Waiting", MESSAGE_DELAY, "seconds before next message...")
        for _ in range(MESSAGE_DELAY * 10):
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

sock.close()
print("DEBUG: Exiting")
