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

- Wi-Fi STA is activated before ESP-NOW.
- Configuration for both server and client is stored in `/private.py`.

ESP-NOW initialization succeeds. Client send to server verified. Reverse communication is still to be verified.


#### "Known Issues / Lessons Learned" 
The synchronous callback behavior of submit_xfer() on this MicroPython build is unusual enough 
that it's worth documenting prominently for future maintenance. 

---

# Software structure

```
boot.py
    USB enumeration only

usb_channel_server.py
    USB transport
    framing
    channel management
    control channel
    debug support

button_sensor.py

rgb_sensor.py

espnow_server.py

sensor_test.py
    creates the test sensors
```

Sensor modules never import `boot.py`.

They obtain the gateway via:

```python
import usb_channel_server

gateway = usb_channel_server.get_gateway()
```

---

# Device installation

Copy:

- boot.py
- usb_channel_server.py
- button_sensor.py
- rgb_sensor.py
- espnow_server.py
- sensor_test.py

to the board.

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

Current keys:

- p : Ping
- c : Read channel list
- r/g/b/w/y/0 : RGB LED
- d : Toggle device debug
- s : Request gateway status
- x : Clear debug log
- q : Quit

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

- Verify ESP-NOW client communication.
- Add sensor base class.
- Add I²C sensor channels.
- Add SPI sensor channels.
- Add channel hot-plug notifications.
- Implement application protocol on top of transport.
