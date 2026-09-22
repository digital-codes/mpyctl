# Licensing and Attribution

## Project license

Unless stated otherwise, the original source code of this project is intended to
be released under the **GNU Affero General Public License v3.0 (AGPL-3.0-only)**.

Include the following header in newly created source files:

```text
Copyright (C) 2026 <Project Authors>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, version 3.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
```

## Third-party software and documentation

This project depends on or references the following external software and
documentation. These remain under their respective licenses.

| Component | Purpose | Upstream |
|-----------|---------|----------|
| MicroPython | Runtime | https://micropython.org/ |
| MicroPython documentation | USBDevice, ESP-NOW, machine APIs | https://docs.micropython.org/ |
| ESP-IDF USB / ESP32-S3 implementation | Underlying firmware platform | https://github.com/espressif/esp-idf |
| M5Stack AtomS3U hardware | Target hardware | https://docs.m5stack.com/en/core/AtomS3U |
| PyUSB | Linux USB host implementation | https://github.com/pyusb/pyusb |
| libusb | USB backend | https://libusb.info/ |

## Attribution

Parts of the implementation were developed with assistance from OpenAI's
ChatGPT. AI-generated code has been reviewed, tested and modified as required
for this project.

## Notes

- The AGPL applies only to the original project code.
- Third-party libraries, firmware and documentation retain their own licenses.
- When redistributing this project, include the AGPL license text (COPYING or
  LICENSE) and preserve existing copyright and license notices.
