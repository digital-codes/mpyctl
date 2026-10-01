# AtomS3U USB 

## Speed Test
see speedTest

## Sensor Gateway
see gateway 

## Linux dependencies

Debian/Ubuntu:

```bash
sudo apt install python3-usb
```

Alternatively:

```bash
python3 -m pip install pyusb
```

For an initial permissions check, run the benchmark once with `sudo`.
For normal use, install the supplied udev rule:

```bash
sudo cp 70-atoms3u-vendor-usb.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug and reconnect the device after installing the rule.


