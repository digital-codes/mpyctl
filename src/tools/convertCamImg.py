#!/usr/bin/env python3
"""
ESP32 RGB565 Decoder - Matches esp32-camera Library Exactly

Based on convert_line_format() from esp32-camera:
https://github.com/espressif/esp32-camera

Memory layout:
  Byte 0: RRRRRGGG  (Red upper 5 bits + Green lower 3 bits)
  Byte 1: GGG BBBBB (Green upper 3 bits + Blue 5 bits)
"""

import numpy as np
from PIL import Image

def rgb565_to_rgb888_esp32(data: bytes, width: int = 160, height: int = 120) -> np.ndarray:
    """
    Exact replica of ESP32's RGB565 to RGB888 conversion.
    
    ESP32 C code logic:
        dst[o++] = src[i] & 0xF8;                        // Red (upper 5 bits scaled)
        dst[o++] = (src[i] & 0x07) << 5 | (src[i+1] & 0xE0) >> 3;  // Green (combined)
        dst[o++] = (src[i+1] & 0x1F) << 3;               // Blue (lower 5 bits scaled)
    """
    expected_size = width * height * 2
    if len(data) != expected_size:
        raise ValueError(
            f"Data size mismatch: expected {expected_size} bytes, got {len(data)}"
        )
    
    # Reshape to (height, width, 2) for per-pixel processing
    bytes_arr = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 2))
    
    # Extract according to ESP32's exact formula
    byte0 = bytes_arr[:, :, 0]  # RRRRRGGG
    byte1 = bytes_arr[:, :, 1]  # GGG BBBBB
    
    # Red: upper 5 bits of byte 0, expand 5→8 bit
    r = (byte0 & 0xF8).astype(np.uint8)  # Keeps bits 7-3 as-is (already 8-bit with lower 3 zeros)
    # Actually we need to scale: (R5 << 3) gives us R8
    r = ((byte0 & 0xF8)).astype(np.uint8)  # 0xF8 masks upper 5, keeps them at position
    
    # Wait, the C code does: dst[o++] = src[i] & 0xF8;
    # This puts 5-bit R into 8-bit with lower 3 bits zero
    # That's NOT proper 5→8 scaling, it's just masking
    
    # Let me match EXACTLY what C does:
    r = (byte0 & 0xF8).astype(np.uint8)                    # Red: bits 7-3 of byte 0
    
    # Green: combine (byte0 & 0x07) << 5 | (byte1 & 0xE0) >> 3
    g_low = (byte0 & 0x07).astype(np.uint16) << 5          # Lower 3 bits of G shifted left 5
    g_high = (byte1 & 0xE0).astype(np.uint16) >> 3         # Upper 3 bits of G shifted right 3
    g = (g_low | g_high).astype(np.uint8)                # Combine to 6-bit G
    
    # Blue: (byte1 & 0x1F) << 3
    b = ((byte1 & 0x1F).astype(np.uint8) << 3)           # Lower 5 bits of byte 1, shift left 3
    
    # Stack as RGB (each channel is 8-bit)
    rgb = np.stack([r, g, b], axis=-1)
    return rgb


# ============================================================================
# TEST/DEBUG SCRIPT
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ESP32 RGB565 Decoder Test")
    parser.add_argument("-i", "--input_file", required=True, help="Input binary file containing RGB565 data")
    parser.add_argument("-w","--width", type=int, default=160, help="Image width (default: 160)")
    parser.add_argument("-m","--mirror", action="store_true", help="Flip image horizontally") 
    args = parser.parse_args()
    input_file = args.input_file
    
    print(f"Loading: {input_file}")
    with open(input_file, 'rb') as f:
        data = f.read()
    
    print(f"Size: {len(data)} bytes")
    # we expect 4:3 ratio, 160x120 = 19200 bytes or 320x240 = 76800 bytes
    
    # Show raw bytes for first pixel
    print(f"\nFirst 4 bytes (hex): {data[:4].hex()}")
    print(f"  Byte 0: {data[0]:02X} = {data[0]:08b}")
    print(f"  Byte 1: {data[1]:02X} = {data[1]:08b}")
    
    # Decode using exact ESP32 logic
    print("\n=== Testing decoders ===")
    
    rgb_exact = rgb565_to_rgb888_esp32(data, width=args.width, height=len(data)//(args.width*2))
    # mirror if requested
    if args.mirror:
        rgb_exact = np.flip(rgb_exact, axis=1)
    img_exact = Image.fromarray(rgb_exact, mode='RGB')
    img_exact.save(f"{input_file.replace('.bin', '_exact.png')}")
    print(f"Saved: {input_file.replace('.bin', '_exact.png')}")
    
    # Show sample pixel values
    print("\nFirst 4 pixels (RGB):")
    for i in range(min(4, 160)):
        print(f"  Pixel {i}: {rgb_exact[0, i]}")
    
    # Open best result
    print("\nOpening most accurate result...")
    img_exact.show()
    
    