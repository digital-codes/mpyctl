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
- Security: WPA2 (no shared key needed)
- No peer management - clients auto-detected by IP address

### Configuration

WiFi uses the same `config.json` as ESP-NOW. Additional `private.py` settings:

```python
WIFI_SSID = "MPY"
WIFI_PASSWORD = "xxx"          # WPA2 auth
WIFI_CHANNEL = 3
WIFI_PORT = 8080
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
No peer index needed - server identifies clients by IP address.

### Running the Client (Linux)

```bash
python3 host/wifi_client.py -i wlan0              # Auto-detect gateway from interface
python3 host/wifi_client.py -i wlan0 -c 3         # Send 3 messages
python3 host/wifi_client.py -i wlan0 -m "hello"    # Single message
```

### Client Identification

WiFi clients are identified by IP address only (not port). When a client disconnects and reconnects:
- Server tracks by IP string key in `self.clients` dict
- TUI syncs client list every 5 seconds via `CTRL_GET_WIFI_CLIENTS`
- TUI also tracks clients from incoming messages
- Combined list ensures clients aren't lost during brief disconnects

### TUI Usage (WiFi Mode)

- Incoming messages display client IP address
- Press `m` to enter message mode
- Up/Down arrows cycle through seen client IPs
- Press Enter to send, Esc to cancel

The client derives gateway IP (.1 of local subnet) from the specified interface.

---

## Peer Management

Peer management is used only for ESP-NOW mode:

- Peers defined in `peers.json`: `[{"mac": "<hex>", "lmk": "<hex>"}]`
- Host loads this file and sends `MSG_PEER_ADD` / `MSG_PEER_DEL` to device
- Only authorized MAC addresses can communicate via ESP-NOW

WiFi mode does not use peer management - any client with the WPA2 password can connect.

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

## Dynamic Channel Loading

Sensors can be loaded dynamically at runtime via the `CTRL_LOAD_CHANNEL` control command. The device looks up the channel ID in a registry, imports the corresponding module and instantiates the sensor.

### Host Tool: channel_loader.py

Run with: `python3 host/channel_loader.py <command> [options]`

Commands:
- `rgb --pin <n>` - Load RGB LED sensor (channel 2)
- `button --pin <n>` - Load button sensor (channel 1)
- `espnow` - Load ESP-NOW radio (channel 3)
- `load --channel-id <n>` - Load any registered channel by ID

Options:
- `--device-serial <serial>` - Select specific device
- `--name <name>` - Channel name (optional)

Examples:
```bash
python3 host/channel_loader.py rgb --pin 35
python3 host/channel_loader.py button --pin 41 --name my-button
python3 host/channel_loader.py espnow
python3 host/channel_loader.py load --channel-id 2 --pin 35
```

### Protocol

Request: `CTRL_LOAD_CHANNEL + channel_id(1) + config_bytes`

Config format depends on channel type:
- RGB (id=2): `pin(1) + name_len(1) + name`
- Button (id=1): `pin(1) + name_len(1) + name`
- ESP-NOW (id=3): empty

Response: `MSG_STATUS` on success, `MSG_ERROR` on failure.

### Adding New Channel Types

To register a new channel type for dynamic loading, edit `stick/usb_channel_server.py`:

1. Add a config parser method (e.g., `_parse_my_sensor_config`)
2. Add an entry to `_channel_registry` mapping channel_id to:
   - `module`: Python module name to import
   - `class`: Class name to instantiate
   - `config_parser`: Method to parse config bytes
3. Register the parser in `_register_channel_parsers()`

Example:
```python
def _parse_my_sensor_config(self, config):
    return {"channel_id": 4, "param": config[0]}

_channel_registry[4] = {
    "module": "my_sensor",
    "class": "MySensor",
    "config_parser": None,
}

def _register_channel_parsers(self):
    self._channel_registry[CHANNEL_RGB]["config_parser"] = self._parse_rgb_config
    self._channel_registry[CHANNEL_BUTTON]["config_parser"] = self._parse_button_config
    self._channel_registry[4]["config_parser"] = self._parse_my_sensor_config
```

The corresponding sensor module (`my_sensor.py`) must exist on the device's filesystem.

---

## Device Installation

Copy to the board:

**Required:**
- `boot.py`
- `usb_channel_server.py`
- `channel_defs.py` (from common/)

**Sensor modules (required for static loading):**
- `button_sensor.py` (channel 1)
- `rgb_sensor.py` (channel 2)

These can also be loaded dynamically via `CTRL_LOAD_CHANNEL` (see Dynamic Channel Loading).

**Choose one wireless mode:**
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

Tests framing, ping, channel list, status, RGB round trip, button events, wireless receive path, peer management, and WiFi client list sync.

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

## Filesystem Operations

The gateway supports filesystem operations on the device, similar to `mpremote` commands. These are implemented via the control channel using `MSG_COMMAND` with `CTRL_FS_*` commands. Large files are transferred in 960-byte chunks.

### Host Tool: fs_test.py

Run with: `python3 host/fs_test.py <command> [options]`

Commands:
- `ls [path]` - List directory contents (like `mpremote ls`)
- `cat <path> [-o <file>]` - Read file contents (like `mpremote cat`)
- `put <src> [dst]` - Write local file to device (like `mpremote cp`)
- `rm <path>` - Delete file from device
- `exists <path>` - Check if file exists on device
- `reset` - Reset the device via `machine.reset()`

Options:
- `--device-serial <serial>` - Select specific device by USB serial number

Examples:
```bash
python3 host/fs_test.py ls /                # List root directory
python3 host/fs_test.py ls /flash           # List flash filesystem
python3 host/fs_test.py cat /main.py        # Read text file to stdout
python3 host/fs_test.py cat /image.bin -o local.bin  # Save binary file locally
python3 host/fs_test.py put local.py /main.py  # Write file to device
python3 host/fs_test.py put local.bin /data.bin  # Write binary file (images, etc)
python3 host/fs_test.py rm /test.py         # Delete file from device
python3 host/fs_test.py exists /boot.py     # Check if file exists
python3 host/fs_test.py reset               # Reset the device
```

### Protocol

All filesystem commands use `MSG_COMMAND` on channel 0 (control) with the following format:

```
Payload: CTRL_FS_* (1 byte) + command-specific data
Response: MSG_FS_RESPONSE with operation result
Error: MSG_ERROR on failure
```

#### CTRL_FS_LIST (0x10)
- Request: `CTRL_FS_LIST + path string (utf-8)`
- Response: List of entries, each: `name_len(1) + name + is_dir(1) + size(4)`

#### CTRL_FS_READ (0x11)
- Request: `CTRL_FS_READ + path + null + offset(4) + size(4)`
- Response: Raw file contents (up to max_payload bytes)
- Large files are read in 960-byte chunks by the host

#### CTRL_FS_WRITE (0x12)
- Request: `CTRL_FS_WRITE + path + null + offset(4) + data`
- Response: `bytes_written (u32)`
- Large files are written in 960-byte chunks, appended sequentially

#### CTRL_FS_DELETE (0x13)
- Request: `CTRL_FS_DELETE + path string (utf-8)`
- Response: `1` on success, `0` on failure

#### CTRL_FS_EXISTS (0x14)
- Request: `CTRL_FS_EXISTS + path string (utf-8)`
- Response: `1` if exists, `0` if not

#### CTRL_RESET (0x21)
- Request: `CTRL_RESET`
- Response: `MSG_STATUS` immediately before reset
- Effect: Calls `machine.reset()` on the device

### Binary File Support

- `put` automatically handles binary files (images, etc.)
- `cat` detects binary files and refuses to output to terminal (use `-o` to save)
- Device uses binary file modes (`rb`, `wb`, `ab`)

### Device Implementation

The filesystem handlers are implemented in `stick/usb_channel_server.py` in the `_handle_fs_*` methods. They use MicroPython's `os` module for filesystem operations:
- `os.listdir()` - List directory
- `os.stat()` - Get file info
- `open(path, "rb")` - Read file
- `open(path, "wb")` - Write file (truncates)
- `open(path, "ab")` - Append to file
- `os.remove()` - Delete file
- `os.path.exists()` - Check existence

---

## Next Steps

- Add sensor base class
- Add I²C sensor channels
- Add SPI sensor channels
- Add channel hot-plug notifications
- Implement application protocol on top of transport
