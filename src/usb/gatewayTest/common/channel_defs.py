# SPDX-License-Identifier: AGPL-3.0-only
# channel_defs.py
#
# Shared constants between host and stick code:
# - Message types (MSG_*)
# - Channel kinds (KIND_*): 1=input (sensor), 2=output (actuator), 3=bidirectional
# - Directions (DIR_*)
# - Channel numbers (CHANNEL_*)
# - Control commands (CTRL_*)

MSG_DATA = 0x01
MSG_COMMAND = 0x02
MSG_RESPONSE = 0x03
MSG_EVENT = 0x04
MSG_CHANNEL_LIST_REQUEST = 0x05
MSG_CHANNEL_LIST_RESPONSE = 0x06
MSG_CHANNEL_ADDED = 0x07
MSG_CHANNEL_REMOVED = 0x08
MSG_ERROR = 0x09
MSG_PING = 0x0A
MSG_PONG = 0x0B
MSG_STATUS = 0x0C

MSG_PEER_ADD = 0x10
MSG_PEER_DEL = 0x11

KIND_CONTROL = 0
KIND_INPUT = 1
KIND_OUTPUT = 2
KIND_BIDI = 3

DIR_IN = 1
DIR_OUT = 2
DIR_BIDI = 3

CHANNEL_CONTROL = 0
CHANNEL_BUTTON = 1
CHANNEL_RGB = 2
CHANNEL_ESPNOW = 3
CHANNEL_WIFI = 3  # Same as ESP-NOW - uses same channel number

CTRL_SET_DEBUG = 0x01
CTRL_GET_STATUS = 0x02
CTRL_CLEAR_DEBUG = 0x03
CTRL_GET_WIFI_CLIENTS = 0x04
