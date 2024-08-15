# CRC-16-X.25 implementation in Python
# Based on the CRC-16-X.25 algorithm described at https://en.wikipedia.org/wiki/Computation_of_cyclic_redundancy_checks
# verify with https://crccalc.com/
# Params: initial: 0xffff, poly: 0x1021, final: 0xffff, reflect_in: True, reflect_out: True
# chatgpt version, 20240815
def _reflect_bits(data: int, num_bits: int) -> int:
    reflection = 0
    for i in range(num_bits):
        if data & (1 << i):
            reflection |= 1 << (num_bits - 1 - i)
    return reflection

def crc16_x25(data: bytes) -> int:
    crc = 0xFFFF  # Initial value for CRC
    poly = 0x1021  # Polynomial for CRC-16-X.25

    for byte in data:
        byte = _reflect_bits(byte, 8)  # Reflect each byte before processing
        crc ^= (byte << 8)  # Bring the next byte into the CRC calculation
        for _ in range(8):  # Process each bit
            if crc & 0x8000:  # If the highest bit (15th) is set
                crc = (crc << 1) ^ poly  # Shift left and XOR with the polynomial
            else:
                crc <<= 1  # Otherwise just shift left
            crc &= 0xFFFF  # Ensure CRC remains within 16 bits

    crc = _reflect_bits(crc, 16)  # Reflect the output CRC
    crc ^= 0xFFFF  # XOR the final CRC with 0xFFFF
    return crc

