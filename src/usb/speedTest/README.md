# AtomS3U USB bulk echo test

## Device

Copy `boot.py` to the MicroPython filesystem:

```bash
mpremote connect /dev/ttyACM0 fs cp boot.py :boot.py
```

Power-cycle the AtomS3U. Confirm that `/dev/ttyACM0` still works and that
`lsusb -v -d 303a:4001` shows interface 2 with endpoints 0x03 and 0x83.

The transfer callback lives in `boot.py`, so no `main.py` is required.

At the REPL, counters are available with:

```python
import boot
boot.usb_stats()
```

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

## Run

```bash
python3 usb_bench.py --duration 10 --size 4096
```

Test variable logical transfer sizes:

```bash
for size in 64 256 1024 4096; do
    python3 usb_bench.py --duration 5 --size "$size"
done
```

The reported "verified one-way" rate counts each payload once. The actual USB
traffic is approximately twice that value because every block is echoed.

## Expected behaviour

The initial implementation is strict request/reply:

1. Linux writes one block.
2. The device echoes it.
3. Linux verifies every byte.
4. The next block begins.

This is intentionally conservative and is suitable for validating a
500-kbit/s target. A later version can use independent RX/TX ring buffers and
multiple queued host transfers for full-duplex operation.
