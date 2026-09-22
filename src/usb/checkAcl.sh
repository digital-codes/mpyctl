#!/usr/bin/bash
DEVICE=$(
  for d in /dev/bus/usb/*/*; do
    udevadm info --query=property --name="$d" 2>/dev/null |
      grep -q '^ID_VENDOR_ID=303a$' &&
    udevadm info --query=property --name="$d" 2>/dev/null |
      grep -q '^ID_MODEL_ID=4001$' &&
    echo "$d"
  done
)
getfacl "$DEVICE"

