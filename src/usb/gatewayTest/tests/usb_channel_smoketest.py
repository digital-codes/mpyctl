#!/usr/bin/env python3
"""Host-side smoke test for the AtomS3U USB sensor gateway.

Stubs the MicroPython-only modules (machine, neopixel, micropython,
network, espnow) plus private/pyusb, then exercises the real
stick/usb_channel_server, the stick sensor modules and host/sensor_tui
parsing against a fake USBDevice. The full scenario runs twice: with
synchronous and with asynchronous IN-transfer completion (the quirk
documented in the README), and the resulting host-visible frame traces
must be identical.

Checks: framing/ping/channel-list/status/RGB round trip/button events,
drain continuing past unknown peers, the ESP-NOW init log line format,
sensor_test.run() repairing a partially stopped sensor set, the
Wi-Fi channel coming from private.py (decoupled from the USB channel id),
and peer_add/peer_del message handling.

Run with: python3 tests/usb_channel_smoketest.py
"""
import atexit
import io
import json
import os
import shutil
import sys
import tempfile
import types
from contextlib import redirect_stdout

DEBUG = True

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # gatewayTest/
STICK = os.path.join(ROOT, "stick")               # AtomS3U MicroPython
HOST = os.path.join(ROOT, "host")                 # Linux TUI
COMMON = os.path.join(ROOT, "common")              # common/

WIFI_CHANNEL = 6          # pretend private.ENOW_CHANNEL (must NOT equal channel id 3)
SHARED_KEY = bytes.fromhex("00112233445566778899aabbccddeeff")


def debug(*args, **kwargs):
    if DEBUG:
        print("[DEBUG]", *args, **kwargs)

# config.json is opened relative to the cwd: use a scratch directory
WORKDIR = tempfile.mkdtemp(prefix="mpyctl-smoke-")
atexit.register(shutil.rmtree, WORKDIR, True)
os.chdir(WORKDIR)

with open(os.path.join(WORKDIR, "config.json"), "w") as f:
    json.dump({
        "id": "smoketest",
        "ble": {"key": SHARED_KEY.hex()},
        "wlan": {"addr": "aabbccddeeff"},
    }, f)

# espnow_server checks os.listdir("/") but opens "config.json" relatively
_real_listdir = os.listdir


def _listdir(path="."):
    entries = _real_listdir(path)
    if path == "/" and "config.json" not in entries:
        entries = entries + ["config.json"]
    return entries


os.listdir = _listdir

# --- controllable clock ---------------------------------------------
import time

CLOCK = [0]
time.ticks_ms = lambda: CLOCK[0]
time.ticks_diff = lambda a, b: a - b

# --- stub modules ----------------------------------------------------
machine = types.ModuleType("machine")


class _Pin:
    IN = 0
    OUT = 1
    PULL_UP = 2

    def __init__(self, pin=None, mode=None, pull=None):
        self.pin_no = pin
        self._value = 1

    def value(self, v=None):
        if v is None:
            return self._value
        self._value = v


class _Timer:
    PERIODIC = 1

    def __init__(self, timer_id=None):
        self.callback = None

    def init(self, period=None, mode=None, callback=None):
        self.callback = callback

    def deinit(self):
        self.callback = None


machine.Pin = _Pin
machine.Timer = _Timer
sys.modules["machine"] = machine

neopixel = types.ModuleType("neopixel")


class _NeoPixel:
    def __init__(self, pin, n):
        self.px = [(0, 0, 0)] * n

    def __setitem__(self, i, v):
        self.px[i] = v

    def write(self):
        self.written = list(self.px)


neopixel.NeoPixel = _NeoPixel
sys.modules["neopixel"] = neopixel

micropython = types.ModuleType("micropython")
micropython.schedule = lambda fn, arg: fn(arg)
sys.modules["micropython"] = micropython

network = types.ModuleType("network")


class _WLAN:
    IF_STA = 0
    AP_IF = 1
    PM_NONE = 0

    def __init__(self, iface=None):
        self.cfg_calls = []
        self._iface = iface
        self._active = False

    def disconnect(self):
        pass

    def active(self, state=None):
        if state is not None:
            self._active = state
        return True

    def config(self, *args, **kwargs):
        self.cfg_calls.append((args, kwargs))
        # Return appropriate values based on what's being configured
        if args and args[0] == 'essid':
            return True
        if args and args[0] == 'channel':
            return WIFI_CHANNEL
        if args and args[0] == 'mac':
            return b"\xaa" * 6
        if args and args[0] == 'ip':
            return '192.168.1.1'
        return {"channel": WIFI_CHANNEL, "mac": b"\xaa" * 6}

    def ifconfig(self):
        return ('192.168.1.1', '255.255.255.0', '192.168.1.1', '8.8.8.8')


network.WLAN = _WLAN
network.AP_IF = 1
sys.modules["network"] = network

# select module stub for WiFi server
select = types.ModuleType("select")


class _poll:
    POLLIN = 1
    POLLHUP = 2
    POLLERR = 4


select.poll = lambda: _poll()
sys.modules["select"] = select

# Socket mock for WiFi server
socket_mod = types.ModuleType("socket")


class _socket:
    AF_INET = 2
    SOCK_STREAM = 1
    SOL_SOCKET = 4096
    SO_REUSEADDR = 2

    def __init__(self, family=AF_INET, type=SOCK_STREAM):
        self.family = family
        self.type = type
        self._closed = False

    def setsockopt(self, level, optname, value):
        pass

    def bind(self, address):
        pass

    def listen(self, backlog):
        pass

    def settimeout(self, timeout):
        pass

    def accept(self):
        raise OSError("no pending connection")

    def send(self, data):
        return len(data)

    def recv(self, bufsize):
        return b""

    def close(self):
        self._closed = True


socket_mod.socket = _socket
sys.modules["socket"] = socket_mod

espnow_mod = types.ModuleType("espnow")


class _ESPNow:
    MAX_DATA_LEN = 250
    MAX_ENCRYPT_PEER_NUM = 20
    MAX_TOTAL_PEER_NUM = 20
    
    def __init__(self):
        self.peers_table = {}
        self.rx = []

    def active(self, state=None):
        return True

    def config(self, **kwargs):
        pass

    def set_pmk(self, key):
        self.pmk = key

    def irq(self, callback):
        self.irq_cb = callback

    def add_peer(self, mac, lmk=None, channel=None):
        self.peers_table[bytes(mac)] = (-55, lmk, channel)

    def del_peer(self, mac):
        self.peers_table.pop(bytes(mac), None)

    def get_peer(self, mac):
        return self.peers_table[bytes(mac)]

    def irecv(self, timeout):
        if self.rx:
            return self.rx.pop(0)
        return (None, None)

    def send(self, mac, message):
        """Mock send - returns True for success."""
        return True

    def stats(self):
        return {}


espnow_mod.MAX_DATA_LEN = 250
espnow_mod.MAX_ENCRYPT_PEER_NUM = 20
espnow_mod.MAX_TOTAL_PEER_NUM = 20
espnow_mod.ESPNow = _ESPNow
sys.modules["espnow"] = espnow_mod

private = types.ModuleType("private")
private.ENOW_CHANNEL = WIFI_CHANNEL
private.ENOW_SERVER = "aabbccddeeff"
private.ENOW_KEY = SHARED_KEY.hex()
sys.modules["private"] = private

usb_pkg = types.ModuleType("usb")
usb_core = types.ModuleType("usb.core")
usb_util = types.ModuleType("usb.util")
usb_pkg.core = usb_core
usb_pkg.util = usb_util
sys.modules["usb"] = usb_pkg
sys.modules["usb.core"] = usb_core
sys.modules["usb.util"] = usb_util

# --- real modules under test -----------------------------------------
sys.path.insert(0, STICK)
sys.path.insert(0, HOST)
sys.path.insert(0, COMMON)
import usb_channel_server as ucs
import sensor_test
import espnow_server
import sensor_tui

EP_IN = 0x83
EP_OUT = 0x03


class FakeUSBD:
    def __init__(self, sync_in):
        self.sync_in = sync_in
        self.complete = None
        self.in_frames = []
        self._pending = []
        self.out_arms = 0

    def submit_xfer(self, ep, buf):
        data = bytes(buf)
        if ep == EP_IN:
            if self.sync_in:
                self.in_frames.append(data)
                self.complete(ep, 0, len(data))
            else:
                self._pending.append(data)
            return True
        self.out_arms += 1
        return True

    def pump(self):
        while self._pending:
            data = self._pending.pop(0)
            self.in_frames.append(data)
            self.complete(EP_IN, 0, len(data))


def parse(raw):
    assert len(raw) >= 4, raw
    length = raw[2] | (raw[3] << 8)
    assert len(raw) == 4 + length, (len(raw), length)
    return (raw[0], raw[1], raw[4:])


class Harness:
    def __init__(self, sync_in):
        self.dev = FakeUSBD(sync_in)
        self.server = ucs.USBChannelServer(
            self.dev, interface=2, ep_out=EP_OUT, ep_in=EP_IN
        )
        self.dev.complete = self.server.on_transfer_complete
        ucs.set_default_gateway(self.server)
        self.server.on_interface_open()
        self.sync_in = sync_in

    def flush(self):
        self.dev.pump()

    def inject(self, ch, typ, payload=b""):
        raw = bytes((ch, typ, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF))
        raw += payload
        n = len(raw)
        self.server.rx_buffer[:n] = raw
        self.server.on_transfer_complete(EP_OUT, 0, n)
        self.flush()

    def frames_since(self, mark):
        self.flush()
        return [parse(raw) for raw in self.dev.in_frames[mark:]]

    def mark(self):
        self.flush()
        return len(self.dev.in_frames)


def run_scenario(sync_in):
    h = Harness(sync_in)
    trace = []

    def take(mark):
        frames = h.frames_since(mark)
        trace.extend(frames)
        return frames

    debug(f"=== Starting scenario (sync_in={sync_in}) ===")

    # --- sensor creation + init log line ------------------------------
    debug("Creating sensors...")
    mark = h.mark()
    buf = io.StringIO()
    with redirect_stdout(buf):
        sensor_test.run()
    h.flush()
    log = buf.getvalue()
    assert "Wi-Fi channel: %d address:" % WIFI_CHANNEL in log, log
    assert set(h.server.channels) == {0, 1, 2, 3}, sorted(h.server.channels)

    st = sensor_test
    assert st.button is not None and st.rgb is not None and st.radio is not None
    debug(f"Sensors created: button={st.button is not None}, rgb={st.rgb is not None}, radio={st.radio is not None}")

    # Wi-Fi channel from private.py, USB channel stays 3
    assert st.radio.wifi_channel == WIFI_CHANNEL, st.espnow.wifi_channel
    assert st.radio.channel_id == 3
    wlan = st.radio.wlan
    assert ((), {"channel": WIFI_CHANNEL}) in wlan.cfg_calls, wlan.cfg_calls

    add_events = take(mark)  # channel-added announcements + initial button state
    kinds = {(f[2][1], f[2][0]) for f in add_events if f[1] == ucs.MSG_CHANNEL_ADDED}
    assert kinds == {(1, 1), (2, 2), (3, 3)}, kinds  # (channel id, kind)
    assert (1, ucs.MSG_EVENT, b"\x00") in add_events  # initial button release

    # --- ping ---------------------------------------------------------
    debug("Testing ping...")
    mark = h.mark()
    h.inject(0, ucs.MSG_PING)
    assert take(mark) == [(0, ucs.MSG_PONG, b"AS3U\x01")]

    # --- channel list, host-side parsed -------------------------------
    debug("Testing channel list...")
    mark = h.mark()
    h.inject(0, ucs.MSG_CHANNEL_LIST_REQUEST)
    frames = take(mark)
    assert frames[0][0:2] == (0, ucs.MSG_CHANNEL_LIST_RESPONSE)
    channels = sensor_tui.parse_channels(frames[0][2])
    assert set(channels) == {0, 1, 2, 3}
    assert channels[0].name == "control" and channels[0].kind == 0
    assert channels[1].name == "button" and channels[1].kind == 1
    assert channels[1].direction == ucs.DIR_IN
    assert channels[2].name == "rgb-led" and channels[2].direction == ucs.DIR_OUT
    assert channels[2].max_packet == 3
    assert channels[3].name == "espnow-radio" and channels[3].kind == 3
    assert channels[3].max_packet == 250

    # --- RGB round trip ----------------------------------------------
    debug("Testing RGB round trip...")
    mark = h.mark()
    h.inject(2, ucs.MSG_COMMAND, b"\x01\x02\x03")
    assert take(mark) == [(2, ucs.MSG_RESPONSE, b"\x01\x02\x03")]
    assert st.rgb.pixel.written == [(1, 2, 3)]
    tui = sensor_tui.TUI(None)
    tui.handle_frame(2, ucs.MSG_RESPONSE, b"\x01\x02\x03")
    assert tui.rgb == (1, 2, 3)
    debug("RGB test passed")

    # --- button debounce + event --------------------------------------
    debug("Testing button debounce...")
    mark = h.mark()
    st.button.pin.value(0)          # press (active low)
    st.button._poll(None)           # raw edge, start debounce
    CLOCK[0] += 50
    st.button._poll(None)           # stable -> emit
    frames = take(mark)
    assert (1, ucs.MSG_EVENT, b"\x01") in frames, frames
    debug("Button test passed")

    # --- status + debug toggle, host-side parsed ----------------------
    debug("Testing status and debug toggle...")
    mark = h.mark()
    mark = h.mark()
    h.inject(0, ucs.MSG_COMMAND, bytes((ucs.CTRL_GET_STATUS,)))
    frames = take(mark)
    assert frames[0][0:2] == (0, ucs.MSG_STATUS) and len(frames[0][2]) == 28
    status = sensor_tui.parse_status(frames[0][2])
    assert status["rx_frames"] >= 4 and status["tx_frames"] >= 4
    assert not status["debug"]

    mark = h.mark()
    h.inject(0, ucs.MSG_COMMAND, bytes((ucs.CTRL_SET_DEBUG, 1)))
    frames = take(mark)
    assert sensor_tui.parse_status(frames[0][2])["debug"]

    # --- drain continues past unknown peers ---------------------------
    debug("Testing drain past unknown peers...")
    mac_unknown = bytes.fromhex("deadbeef0001")
    mac_peer = bytes.fromhex("aabbccddeeff")
    e = st.radio
    e.enableNode(mac_peer, lmk=b"\x5a" * 16)
    e.radio.rx = [
        (mac_unknown, SHARED_KEY + b"junk"),
        (mac_peer, SHARED_KEY + b"hello"),
    ]
    mark = h.mark()
    e._irq(None)
    frames = take(mark)
    events = [f for f in frames if f[0] == 3 and f[1] == ucs.MSG_EVENT]
    assert len(events) == 1, frames  # unknown peer skipped, drain continued
    payload = events[0][2]
    assert payload[:6] == mac_peer and payload[7:] == b"hello"
    assert payload[6] == ((-55 + 256) & 0xFF)
    assert e.received == 1
    tui.handle_frame(3, ucs.MSG_EVENT, payload)
    assert "hello" in tui.esp_messages[-1] and "RSSI -55" in tui.esp_messages[-1]
    debug("Drain test passed")

    # --- peer_add and peer_del via USB channel -------------------------
    debug("Testing MSG_PEER_ADD and MSG_PEER_DEL...")
    e = st.radio
    assert e.get_peer_count() == 1, "should have 1 peer (mac_peer)"

    # Send MSG_PEER_ADD to add a new peer
    debug("Testing peer_add via USB channel...")
    mac_new = bytes.fromhex("112233445566")
    lmk_new = bytes.fromhex("aabbccddeeff00112233445566778899aabb")
    debug(f"Current peer count before: {e.get_peer_count()}")
    mark = h.mark()
    h.inject(3, ucs.MSG_PEER_ADD, mac_new + lmk_new)
    take(mark)
    assert e.get_peer_count() == 2, "should have 2 peers after peer_add"
    assert mac_new in e.get_peer_macs(), "new peer should be registered"
    debug(f"After peer_add: {e.get_peer_count()} peers")

    # Send MSG_PEER_DEL to remove a peer
    mark = h.mark()
    h.inject(3, ucs.MSG_PEER_DEL, mac_new)
    take(mark)
    assert e.get_peer_count() == 1, "should have 1 peer after peer_del"
    assert mac_new not in e.get_peer_macs(), "peer should be removed"
    debug(f"After peer_del: {e.get_peer_count()} peers")

    # Test peer_add without LMK (uses default)
    mac_no_lmk = bytes.fromhex("ffeeddccbbaa")
    mark = h.mark()
    h.inject(3, ucs.MSG_PEER_ADD, mac_no_lmk)
    take(mark)
    assert mac_no_lmk in e.get_peer_macs(), "peer without LMK should be added"
    debug(f"After peer_add (no LMK): {e.get_peer_count()} peers")

    # --- run() repairs a partially stopped set ------------------------
    b0, r0 = st.button, st.rgb
    mark = h.mark()
    st.stop(("radio",))
    dropped = take(mark)
    assert (0, ucs.MSG_CHANNEL_REMOVED, b"\x03") in dropped
    assert 3 not in h.server.channels and st.radio is None

    with redirect_stdout(io.StringIO()):
        st.run()                    # requests all three again
    assert st.button is b0 and st.rgb is r0, "live sensors must be untouched"
    assert st.radio is not None, "missing espnow sensor must be recreated"
    assert set(h.server.channels) == {0, 1, 2, 3}

    # idempotent when everything is live
    with redirect_stdout(io.StringIO()):
        st.run()
    assert st.button is b0 and st.rgb is r0

    # --- odd USB channel id must not move the radio -------------------
    with redirect_stdout(io.StringIO()):
        e2 = espnow_server.ESPNowRadio(channel_id=7)
    try:
        assert e2.wifi_channel == WIFI_CHANNEL, e2.wifi_channel
        assert 7 in h.server.channels and 3 in h.server.channels
    finally:
        e2.close()
    assert 7 not in h.server.channels and 3 in h.server.channels

    # --- control channel invariants ------------------------------------
    try:
        h.server.unregister_channel(0)
        raise AssertionError("control channel must not be removable")
    except ValueError:
        pass

    combined = st.stats()
    assert combined["usb"]["rx_frames"] >= 5 and combined["radio"] is not None

    st.stop()
    h.flush()
    assert 1 not in h.server.channels and 2 not in h.server.channels
    debug("=== Scenario complete ===")
    return trace


trace_sync = run_scenario(sync_in=True)
trace_async = run_scenario(sync_in=False)
assert trace_sync == trace_async, "sync/async IN completion must be indistinguishable"
print("PASS: %d traced frames identical in sync and async IN-completion modes"
      % len(trace_sync))


# --- WiFi-specific tests -------------------------------------------------
print("\n=== WiFi-specific tests ===")

debug("Testing WiFi client tracking by IP...")

import wifi_server


class FakeGateway:
    def __init__(self):
        self.sent = []

    def send(self, channel, msg_type, payload, raise_on_full=True):
        self.sent.append((channel, msg_type, payload))
        return True

    def register_channel(self, *args, **kwargs):
        pass


ws = wifi_server.WiFiServer(channel_id=3, debug=False)
ws.gateway = FakeGateway()

ws.clients["192.168.4.2"] = (None, None)
ws.clients["192.168.4.3"] = (None, None)

assert len(ws.clients) == 2
assert "192.168.4.2" in ws.clients
assert "192.168.4.3" in ws.clients

client_list = ws.get_client_list()
ips = [c["ip"] for c in client_list]
assert "192.168.4.2" in ips
assert "192.168.4.3" in ips
debug("WiFi client tracking test passed")

debug("Testing TUI WiFi client handling...")

tui = sensor_tui.TUI(None, use_wifi=True)
assert tui.use_wifi == True
assert tui.wifi_clients == []

test_payload = bytes([192, 168, 4, 2]) + b"hello world"
tui.handle_frame(3, ucs.MSG_EVENT, test_payload)

assert "192.168.4.2" in tui.wifi_clients
debug("TUI WiFi client handling test passed")

debug("Testing TUI WiFi client list sync...")

# Build sync payload: count(1) + ip_len(1) + ip + mac_len(1) + mac
sync_payload = bytes([1]) + bytes([11]) + b'192.168.4.3' + bytes([7]) + b'unknown'
tui._parse_wifi_clients(sync_payload)

assert "192.168.4.2" in tui.wifi_clients
assert "192.168.4.3" in tui.wifi_clients
debug("TUI WiFi client sync test passed")

print("PASS: All WiFi-specific tests passed")
