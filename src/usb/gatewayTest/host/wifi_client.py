#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# wifi_client.py
#
# Linux host WiFi client for the AtomS3U USB sensor gateway.
#
# Connects to the WiFi server (same as the MicroPython wifi_client_example.py)
# via TCP socket and sends/receives messages.
#
# Usage:
#   python3 host/wifi_client.py [--server-ip IP] [--port PORT]
#
# Default server IP is read from ../stick/private.py or defaults to 192.168.1.1
# Default port is 8080

import argparse
import socket
import sys
import time
import os
import json

# Default configuration
DEFAULT_SERVER_IP = "192.168.1.1"
DEFAULT_PORT = 8080

# Try to load configuration from private.py in stick directory
PRIVATE_PATH = os.path.join(os.path.dirname(__file__), "..", "stick", "private.py")

def load_private_config():
    """Try to load WiFi configuration from private.py."""
    try:
        if os.path.exists(PRIVATE_PATH):
            # Read the file and extract values
            with open(PRIVATE_PATH, "r") as f:
                content = f.read()
            
            # Simple extraction of constants
            result = {}
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('WIFI_SERVER_IP'):
                    result['server_ip'] = line.split('=')[1].strip().strip('"').strip("'")
                elif line.startswith('WIFI_PORT'):
                    result['port'] = int(line.split('=')[1].strip())
            return result
    except Exception as e:
        print(f"Warning: Could not load private.py: {e}")
    return {}


class WiFiClient:
    """TCP client for WiFi server communication."""
    
    def __init__(self, server_ip, port=8080, shared_key=None):
        self.server_ip = server_ip
        self.port = port
        self.socket = None
        self.connected = False
        self.received_count = 0
        
        # Load shared key from config
        if shared_key is None:
            # Try to load from config.json
            try:
                config_path = os.path.join(os.path.dirname(__file__), "..", "stick", "config.json")
                if os.path.exists(config_path):
                    with open(config_path, "r") as f:
                        config = json.load(f)
                        key_hex = config.get("ble", {}).get("key", "")
                        if key_hex:
                            shared_key = bytes.fromhex(key_hex)[:16]
            except Exception:
                pass
        
        if shared_key is None:
            raise ValueError("No shared key provided")
        
        self.shared_key = shared_key
    
    def connect(self):
        """Connect to the WiFi server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_ip, self.port))
            self.socket.settimeout(0.1)  # Short timeout for non-blocking feel
            self.connected = True
            print(f"Connected to {self.server_ip}:{self.port}")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the server."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        self.connected = False
    
    def send_message(self, message):
        """Send a message with shared key header."""
        if not self.connected or not self.socket:
            return False
        
        try:
            payload = self.shared_key + message.encode()
            self.socket.send(payload)
            return True
        except Exception as e:
            print(f"Send error: {e}")
            self.connected = False
            return False
    
    def receive_message(self):
        """Check for and receive a message."""
        if not self.connected or not self.socket:
            return None
        
        try:
            data = self.socket.recv(1024)
            if not data:
                # Connection closed
                self.connected = False
                return None
            
            # Check for shared key header
            if len(data) >= 16 and data[:16] == self.shared_key:
                application_data = data[16:]
                self.received_count += 1
                return application_data.decode()
            else:
                return data.decode()
        except socket.timeout:
            return None
        except Exception as e:
            print(f"Receive error: {e}")
            self.connected = False
            return None


def main():
    parser = argparse.ArgumentParser(description="WiFi client for sensor gateway")
    parser.add_argument("--server-ip", default=None, help="Server IP address")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    parser.add_argument("--message", "-m", help="Send a single message and exit")
    parser.add_argument("--count", "-c", type=int, default=5, help="Number of messages to send (default: 5)")
    parser.add_argument("--interval", "-i", type=int, default=5, help="Interval between messages in seconds (default: 5)")
    args = parser.parse_args()
    
    # Load configuration
    config = load_private_config()
    
    server_ip = args.server_ip or config.get('server_ip', DEFAULT_SERVER_IP)
    port = args.port or config.get('port', DEFAULT_PORT)
    
    print(f"WiFi Client")
    print(f"Server: {server_ip}:{port}")
    
    # Create client
    try:
        client = WiFiClient(server_ip, port)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Connect
    if not client.connect():
        print("Failed to connect, exiting...")
        sys.exit(1)
    
    if args.message:
        # Send single message and exit
        if client.send_message(args.message):
            print(f"Sent: {args.message}")
            time.sleep(1)
            response = client.receive_message()
            if response:
                print(f"Received: {response}")
        client.disconnect()
        return
    
    # Interactive loop
    counter = 0
    try:
        while counter < args.count:
            message = f"sensor message {counter}"
            print(f"\n--- Sending message {counter} ---")
            
            if client.send_message(message):
                print(f"Sent: {message}")
            else:
                print("Send failed, trying to reconnect...")
                client.disconnect()
                time.sleep(1)
                client.connect()
                continue
            
            # Check for responses
            for _ in range(10):  # Check for 1 second
                response = client.receive_message()
                if response:
                    print(f"Received: {response}")
                time.sleep(0.1)
            
            counter += 1
            
            if counter < args.count:
                print(f"Waiting {args.interval} seconds...")
                time.sleep(args.interval)
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    client.disconnect()
    print(f"\nTotal messages received: {client.received_count}")


if __name__ == "__main__":
    main()
