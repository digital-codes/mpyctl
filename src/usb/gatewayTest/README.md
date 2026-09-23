# AtomS3U USB Sensor Gateway

Current status: **working baseline**

## Verified

### USB transport

- Composite USB device
  - Interface 0/1: MicroPython CDC REPL
  - Interface 2: Vendor-specific bulk interface
- 4-byte framing:
  - channel (u8)
  - message type (u8)
  - payload length (u16 little-endian)
- Full duplex operation
- Binary payloads
- Channel discovery
- Ping/Pong
- Dynamic channel registration
- Runtime debug logging

### Sensors

Verified:

- GPIO41 button input
- GPIO35 NeoPixel RGB output

The Linux TUI successfully receives button events and controls the RGB LED.

### ESP-NOW

Current implementation:

- Wi-Fi STA is activated before ESP-NOW (required on ESP32).
- In gateway mode the ingress sensor registers USB channel 3. The Wi-Fi
  channel is always read from `private.py` `ENOW_CHANNEL` and is
  independent of the USB channel number.
- On-air message: 16-byte shared key header + application data.
- USB event payload: 6-byte source MAC + 1-byte RSSI (offset by 256) +
  application data.

Testing status (2026-09-23):

- **Client to server is verified, with encryption, when the LMK is set.**
  `espnow_client_example.py` runs on a second ESP32 board.
- Server to client is still to be verified.

#### Configuration

The ESP-NOW server (gateway mode and stand-alone) reads `/config.json`:

```json
{
  "id":  "<device id>",
  "ble":  {"key": "<32 hex chars: 16-byte shared key / LMK>"},
  "wlan": {"addr": "<own MAC hex>"}
}
```

All ESP-NOW code (server and client) uses `private.py`:

>   ENOW_SERVER = \<hex mac address (no : )\> (client only)
    ENOW_KEY = \<hex key; first 16 bytes are the PMK and the message header\> (client only)
    ENOW_CHANNEL = \<Wi-Fi channel\> (all modes)

**Note:** `private.py` is kept in `stick/` together with the board code,
but the **client needs the same file** — copy it to the second ESP32
along with `client/espnow_client_example.py`. It is not in git
(gitignored) and must be created per deployment.

`espnow_client_example.py` additionally uses `config.json` `ble.key` as
the LMK for encrypted unicast.
Encryption only works when every peer is registered with the same LMK:
the server via `enableNode(mac, lmk)` or `peers.json`, the client via
`radio.add_peer(SERVER_MAC, LMK, ...)`.
The stand-alone server loads `peers.json`, a list of
`{"mac": "<hex>", "lmk": "<hex>"}` entries.

To run the client test: copy `client/espnow_client_example.py`,
`stick/private.py` and `config.json` to a second ESP32 and start it as a
script (it runs its send loop at import time). It transmits
`sensor message <n>` to the server every 5 seconds; the messages show up
on TUI channel 3.

#### Known Issues / Lessons Learned 
The synchronous callback behavior of submit_xfer() on this MicroPython build is unusual enough 
that it's worth documenting prominently for future maintenance. 

---

# Software structure

```
stick/                  AtomS3U MicroPython, installed on the board
    boot.py                 USB enumeration only
    usb_channel_server.py   USB transport, framing, channel management,
                            control channel, debug support
    button_sensor.py        channel 1, GPIO41 input
    rgb_sensor.py           channel 2, GPIO35 NeoPixel output
    espnow_server.py        channel 3, ESP-NOW ingress
    sensor_test.py          creates the test sensors
    manualTest.py           REPL scratch script for manual bring-up
                            (deletes boot.py from the device at the end!)
    config.json             shared key / LMK, device id, own MAC
    private.py              Wi-Fi channel (ENOW_CHANNEL), secrets;
                            also needed by client/ (see above)
    peers.json              stand-alone ESP-NOW testing only

host/                   Linux host application
    sensor_tui.py           curses UI (pyusb)

client/                 ESP-NOW test client for a second ESP32
    espnow_client_example.py

tests/                  host-side smoke test (stubs the MicroPython
                        modules; run: python3 tests/usb_channel_smoketest.py)
    usb_channel_smoketest.py
```

Sensor modules never import `boot.py`.

They obtain the gateway via:

```python
import usb_channel_server

gateway = usb_channel_server.get_gateway()
```

---

# Device installation

Copy the contents of `stick/`:

- boot.py
- usb_channel_server.py
- button_sensor.py
- rgb_sensor.py
- espnow_server.py
- sensor_test.py

to the board. Add `config.json` and `private.py` (see the ESP-NOW
configuration section) if the ESP-NOW sensor is used; `espnow_server.py`
refuses to start without `config.json` and imports `private.py` for the
Wi-Fi channel.

Power-cycle afterwards.

---

# REPL

USB transport only:

```python
import usb_channel_server

gateway = usb_channel_server.get_gateway()
gateway.stats()
```

Start the test sensors:

```python
import sensor_test
sensor_test.run()
```

Stop:

```python
sensor_test.stop()
```

---

# Linux TUI

Run `host/sensor_tui.py` (needs pyusb, curses):

```
python3 host/sensor_tui.py [--serial <serial>]
```

Current keys:

- p : Ping
- c : Read channel list
- r/g/b/w/y/0 : RGB LED
- d : Toggle device debug
- s : Request gateway status
- x : Clear debug log
- q : Quit

---

## Prerequisites

The default boot.py only instantiates the gateway server. The TUI cooperates with sensor_test.py
which must be started manually (unless you use a custom boot.py)

Enter the repl via *mpremote* and start the test

``` 
import sensor_test
sensor_test.run()
```

exit repl with Ctrl-X  (not Ctrl-D) => test keeps running

start `host/sensor_tui.py`




# Host smoke test

`tests/usb_channel_smoketest.py` runs the real `stick/` transport and
sensors plus `host/sensor_tui.py` parsing against a stubbed USB device
(no hardware needed):

```
python3 tests/usb_channel_smoketest.py
```

It covers framing, ping, channel discovery, status, the RGB round trip,
button events and the ESP-NOW receive path, and verifies identical
frames with synchronous and asynchronous USB IN completion.

---

# Debugging

Enable:

```python
gateway.set_debug(True)
```

Disable:

```python
gateway.set_debug(False)
```

Dump:

```python
gateway.dump_debug()
```

Clear:

```python
gateway.clear_debug()
```

---

# Important implementation detail

On the current ESP32-S3 MicroPython build,
`USBDevice.submit_xfer()` may complete synchronously.

The USB channel server therefore marks an IN transfer as busy **before**
calling `submit_xfer()` to avoid recursive submission of the same frame.

This behavior was required for reliable transmission of asynchronous
sensor events.

---

# Next steps

- Verify ESP-NOW server to client communication.
- Add sensor base class.
- Add I²C sensor channels.
- Add SPI sensor channels.
- Add channel hot-plug notifications.
- Implement application protocol on top of transport.
