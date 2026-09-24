# AtomS3U USB Sensor Gateway

Current status: **working baseline** with ESP-NOW and WiFi support.

## Overview

The AtomS3U USB Sensor Gateway provides two wireless communication options:

1. **ESP-NOW** - Low-power peer-to-peer communication
2. **WiFi AP** - Access point mode with TCP sockets

Both use channel 3 on the USB interface and share the same message protocol.

---

## Software Structure

```
common/                     Shared constants between host and stick
    channel_defs.py        Message types, channel kinds, directions

stick/                     AtomS3U MicroPython, installed on the board
    boot.py                USB enumeration only
    usb_channel_server.py  USB transport, framing, channel management
    button_sensor.py       channel 1, GPIO41 input
    rgb_sensor.py          channel 2, GPIO35 NeoPixel output
    espnow_server.py       channel 3, ESP-NOW radio (bi-directional)
    wifi_server.py         channel 3, WiFi AP server (bi-directional)
    sensor_test_espnow.py  creates test sensors with ESP-NOW
    sensor_test_wifi.py    creates test sensors with WiFi
    config.json            shared key, device id, own MAC
    private.py             Wi-Fi secrets (see Configuration)

host/                      Linux host applications
    sensor_tui.py          curses UI (pyusb)
    wifi_client.py         standalone WiFi client (optional)
    wifi/                  WiFi client files
        wifi_client.py     Linux WiFi TCP client

client/                    MicroPython clients for second ESP32
    espnow_client_example.py
    wifi_client_example.py

tests/                     Host-side smoke test
    usb_channel_smoketest.py
```

---

## Quick Start

### ESP-NOW Mode

1. Copy `stick/` contents to device (see Device Installation)
2. Start the sensor on the device:
   ```
   import sensor_test_espnow
   sensor_test_espnow.run()
   ```
3. Run the TUI:
   ```
   python3 host/sensor_tui.py -e
   ```

### WiFi Mode

1. Copy `stick/` contents to device
2. Start the sensor on the device:
   ```
   import sensor_test_wifi
   sensor_test_wifi.run()
   ```
3. Run the TUI:
   ```
   python3 host/sensor_tui.py -w
   ```

---

## USB Transport

- Composite USB device
  - Interface 0/1: MicroPython CDC REPL
  - Interface 2: Vendor-specific bulk interface
- 4-byte framing:
  - channel (u8)
  - message type (u8)
  - payload length (u16 little-endian)
- Full duplex operation, binary payloads
- Channel discovery, Ping/Pong, dynamic registration, debug logging

---

## Sensors

- **GPIO41 button** - Push button input with debouncing
- **GPIO35 NeoPixel** - RGB LED output

The Linux TUI successfully receives button events and controls the RGB LED.

---

## ESP-NOW

### How It Works

- Wi-Fi STA is activated before ESP-NOW (required on ESP32)
- Radio sensor registers USB channel 3
- On-air message: 16-byte shared key header + application data
- USB event payload: 6-byte source MAC + 1-byte RSSI + application data

### Configuration

The ESP-NOW server reads `/config.json`:

```json
{
  "id":  "<device id>",
  "ble":  {"key": "<32 hex chars = 16-byte shared key>"},
  "wlan": {"addr": "<own MAC hex>"}
}
```

All ESP-NOW code uses `private.py`:

```python
ENOW_SERVER = <hex mac>      # Server MAC (client only)
ENOW_KEY = <hex key>        # Shared key (first 16 bytes = PMK)
ENOW_CHANNEL = <channel>     # Wi-Fi channel
```

**Note:** `private.py` is device-specific and must be created per deployment.

### Running the Client

Copy to a second ESP32 and run:
- `client/espnow_client_example.py`
- `stick/private.py`
- `config.json`

The client sends `sensor message <n>` every 5 seconds.

---

## WiFi AP Server

### How It Works

- Creates Access Point: SSID "MPY", password from `private.py`, channel 3
- TCP server on port 8080
- Gateway IP: 192.168.4.1 (always .1 of AP subnet)
- Clients auto-authorize on first data (no peer management needed)
- Same 16-byte shared key header protocol as ESP-NOW

### Configuration

WiFi uses the same `config.json` as ESP-NOW. Additional `private.py` settings:

```python
WIFI_SSID = "MPY"
WIFI_PASSWORD = "xxx"          # WPA2 auth (authmode=3)
WIFI_CHANNEL = 3
WIFI_PORT = 8080
WIFI_KEY = <hex key>           # Same as ENOW_KEY for shared key
```

### Running the Server

On the AtomS3U device:

```python
import sensor_test_wifi
sensor_test_wifi.run()              # Start with debug=False
sensor_test_wifi.run(debug=True)    # Start with debug output
```

### Running the Client (MicroPython)

Copy to a second ESP32 and run:
- `client/wifi_client_example.py`
- `stick/private.py`
- `config.json`

Client automatically uses gateway IP from WiFi interface config.

### Running the Client (Linux)

```bash
python3 host/wifi_client.py -i wlan0              # Auto-detect gateway from interface
python3 host/wifi_client.py -i wlan0 -c 3         # Send 3 messages
python3 host/wifi_client.py -i wlan0 -m "hello"  # Single message
```

The client derives gateway IP (.1 of local subnet) from the specified interface.

---

## Peer Management

Both ESP-NOW and WiFi use the same peer management mechanism:

- Peers defined in `peers.json`: `[{"mac": "<hex>", "lmk": "<hex>"}]`
- Host loads this file and sends `MSG_PEER_ADD` / `MSG_PEER_DEL` to gateway
- Only authorized MAC addresses can connect (WiFi) or communicate (ESP-NOW)

---

## Linux TUI

Run with: `python3 host/sensor_tui.py [options]`

Options:
- `--serial <serial>` - Select specific device
- `-e, --espnow` - Use ESP-NOW mode
- `-w, --wifi` - Use WiFi mode

Keys:
- `p` - Ping
- `c` - Read channel list
- `r/g/b/w/y/0` - RGB LED
- `d` - Toggle device debug
- `s` - Request gateway status
- `x` - Clear debug log / save to file
- `m` - Send message to peer
- `q` - Quit

---

## Device Installation

Copy to the board:

**Required:**
- `boot.py`
- `usb_channel_server.py`
- `button_sensor.py`
- `rgb_sensor.py`
- `channel_defs.py` (from common/)

**Choose one:**
- `espnow_server.py` + `sensor_test_espnow.py` (ESP-NOW mode)
- `wifi_server.py` + `sensor_test_wifi.py` (WiFi mode)

**Add (device-specific):**
- `config.json`
- `private.py`

Power-cycle after installation.

---

## REPL

```python
import usb_channel_server
gateway = usb_channel_server.get_gateway()
gateway.stats()
```

Start sensors:
```python
import sensor_test_espnow  # or sensor_test_wifi
sensor_test_espnow.run()
```

Stop:
```python
sensor_test_espnow.stop()
```

---

## Smoke Test

```bash
python3 tests/usb_channel_smoketest.py
```

Tests framing, ping, channel list, status, RGB round trip, button events, and wireless receive path.

---

## Debugging

```python
gateway.set_debug(True)   # Enable
gateway.set_debug(False)  # Disable
gateway.dump_debug()      # Print log
gateway.clear_debug()     # Clear
```

---

## Important Implementation Detail

On ESP32-S3 MicroPython (v1.27.0), `USBDevice.submit_xfer()` may complete **synchronously**.

The USB channel server marks an IN transfer as busy **before** calling `submit_xfer()` to avoid recursive submission.

---

## Configuration Files

### config.json (per device)
```json
{
  "id": "device-001",
  "ble": {"key": "00112233445566778899aabbccddeeff"},
  "wlan": {"addr": "aabbccddeeff"}
}
```

### private.py (per device)
```python
# ESP-NOW
ENOW_SERVER = "aabbccddeeff"
ENOW_KEY = "00112233445566778899aabbccddeeff"
ENOW_CHANNEL = 3

# WiFi
WIFI_SSID = "MPY"
WIFI_PASSWORD = "xxx"
WIFI_CHANNEL = 3
WIFI_PORT = 8080
WIFI_KEY = "00112233445566778899aabbccddeeff"
```

### peers.json (optional, for multiple clients)
```json
[
  {"mac": "aabbccddeeff0011", "lmk": "00112233445566778899aabbccddeeff"}
]
```

---

## Next Steps

- Add sensor base class
- Add I²C sensor channels
- Add SPI sensor channels
- Add channel hot-plug notifications
- Implement application protocol on top of transport
