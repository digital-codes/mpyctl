# stick_wifi_debug.py
# WiFi AP debug server for AtomS3U (MicroPython)
# Minimal functionality - accepts all connections, echoes packets with prefix
# No peer management, no MAC checking, no USB channel

import os
import json
import network
import socket
import time

AP_SSID = "MPY"
AP_PASSWORD = "0102030405060708090a0b0c0d0e0f"
AP_CHANNEL = 3
AP_LISTEN_PORT = 8080
HEADER_LEN = 16

_CONF_FILE = "config.json"

def load_config():
    files = os.listdir("/")
    if _CONF_FILE not in files:
        print("DEBUG: No config file, using default key")
        return None
    try:
        with open(_CONF_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None

def main():
    print("=" * 60)
    print("DEBUG WiFi Server - Stick")
    print("=" * 60)

    config = load_config()
    if config:
        shared_key = bytes.fromhex(config["ble"]["key"])
        device_id = config.get("id", "unknown")
        print("DEBUG: Device ID:", device_id)
        print("DEBUG: Shared key:", shared_key.hex())
    else:
        shared_key = bytes.fromhex("00112233445566778899aabbccddeeff")
        print("DEBUG: Using default shared key:", shared_key.hex())

    print("DEBUG: Initializing WiFi AP...")
    print("DEBUG: SSID:", AP_SSID)
    print("DEBUG: Password:", AP_PASSWORD)
    print("DEBUG: Channel:", AP_CHANNEL)

    ap = network.WLAN(network.AP_IF)
    ap_mac = ap.config('mac')
    print("DEBUG: AP MAC:", ap_mac.hex())

    # Set authmode before activating (WPA2 = 3)
    ap.config(essid=AP_SSID, password=AP_PASSWORD, channel=AP_CHANNEL, authmode=3)
    ap.active(True)

    print("DEBUG: Waiting for AP to activate...")
    while not ap.active():
        time.sleep(0.1)
    
    ap_ip = ap.ifconfig()
    print("DEBUG: AP IP config:", ap_ip)
    server_ip = ap_ip[0]
    print("DEBUG: Server IP:", server_ip)

    print("DEBUG: Starting TCP server on port", AP_LISTEN_PORT)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((server_ip, AP_LISTEN_PORT))
    server_socket.listen(5)
    server_socket.settimeout(1.0)

    print("=" * 60)
    print("DEBUG: Server ready, waiting for clients...")
    print("=" * 60)

    clients = {}
    connected_count = 0
    received_count = 0
    sent_count = 0

    try:
        while True:
            # Accept new connections
            try:
                sock, addr = server_socket.accept()
                print("DEBUG: NEW CONNECTION from", addr)
                clients[addr] = sock
                connected_count += 1
                print("DEBUG: Total clients:", len(clients))
            except OSError:
                pass

            # Check each client for data
            for addr in list(clients.keys()):
                sock = clients[addr]
                try:
                    sock.settimeout(0)
                    data = sock.recv(1024)
                    if data:
                        received_count += 1
                        print("DEBUG: ============================================")
                        print("DEBUG: RECEIVED from", addr)
                        print("DEBUG: Raw bytes:", data)
                        print("DEBUG: Raw hex:", data.hex())
                        print("DEBUG: Length:", len(data))

                        if len(data) >= HEADER_LEN:
                            header = data[:HEADER_LEN]
                            payload = data[HEADER_LEN:]
                            print("DEBUG: Header (first 16 bytes):", header.hex())
                            print("DEBUG: Payload:", payload)
                            try:
                                print("DEBUG: Payload decode:", payload.decode('utf-8'))
                            except Exception as e:
                                print("DEBUG: Payload decode error:", e)

                            # Echo back with prefix
                            echo_msg = b"ECHO:" + payload
                            try:
                                sent = sock.send(echo_msg)
                                sent_count += 1
                                print("DEBUG: Sent echo:", echo_msg)
                                print("DEBUG: Echo bytes:", sent)
                            except Exception as e:
                                print("DEBUG: Send error:", e)
                                del clients[addr]
                        else:
                            print("DEBUG: ERROR - data too short (< 16 bytes)")
                    else:
                        # No data - connection closed
                        print("DEBUG: Connection closed by client", addr)
                        del clients[addr]
                except OSError:
                    pass  # No data
                except Exception as e:
                    print("DEBUG: Error with client", addr, ":", e)
                    try:
                        del clients[addr]
                    except KeyError:
                        pass

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nDEBUG: Shutting down...")
    finally:
        print("DEBUG: Stats - Connected:", connected_count, "Received:", received_count, "Sent:", sent_count)
        for addr, sock in clients.items():
            try:
                sock.close()
            except:
                pass
        server_socket.close()
        print("DEBUG: Done")

if __name__ == "__main__":
    main()
