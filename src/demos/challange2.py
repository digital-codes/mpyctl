""" demo for encrypt, decrypt
NB: in same program forward and backward cannot use same instance!
uses cbc mode with shared key and iv. make sure to re-initialize iv with every operation
works together with web crypto api
"""
import cryptolib
import random

# define key and iv
# Shared secret key
key1 = b'0123456789ABCDEF'  # 16 bytes key
key2 = b'123456789ABCDEF1'  # 16 bytes key
iv1 = b'123456789ABCDEF0'
iv2 = b'23456789ABCDEF01'
mode = 2 # CBC

#Encryption Process: The plaintext is divided into blocks of fixed size, and each block is encrypted
#separately using the same key. Each block is independent, meaning the same plaintext block will 
#always produce the same ciphertext block.
#Security Consideration: ECB mode is susceptible to certain attacks, especially when encrypting large
#amounts of data or when the plaintext contains patterns, as identical plaintext blocks produce
#identical ciphertext blocks.

fwd = cryptolib.aes(key1,mode,iv1)
bwd = cryptolib.aes(key1,mode,iv1)

msgBytes = 3

# message content is max 3 bytes (actually, only 3 bytes with %1000000)
#msg = random.randint(100000,999999).to_bytes(16,"big")
pin = random.getrandbits(8*msgBytes) % 1000000
print(f"PIN: {pin}")

# need to generate 16 byte message for encryption (padding)
# standard pkcs7 padding ?
msg = pin.to_bytes(msgBytes,"big") + bytes([16 - msgBytes]*(16 - msgBytes))
print(f"MSG: {msg.hex()}")

encoded = fwd.encrypt(msg)
print(f"ENC: {encoded.hex()}")

decoded = bwd.decrypt(encoded)
print(f"DEC: {decoded.hex()}")

# verify. strip of padding

decoded_pin = int.from_bytes(decoded[:msgBytes],"big")
print(f"DPIN: {decoded_pin}")

print(f"Result: {pin == decoded_pin}")



# from browser
fwd = cryptolib.aes(key1,mode,iv1)
bwd = cryptolib.aes(key1,mode,iv1)

pin = bytearray([49,50,51,51,50,49])
msg = pin + bytes([10]*(10))
print(f"MSG: {msg.hex()}")

encoded = fwd.encrypt(msg)
print(f"ENC: {encoded.hex()}")


brs = bytearray([151,144,122,22,234,98,156,158,117,223,128,121,61,64,7,149])
decoded = bwd.decrypt(brs)
print(f"DEC: {decoded.hex()}")
decoded_pin = int.from_bytes(decoded[:6],"big")
print(f"DPIN: {decoded_pin}")

######################################
# partially random iv
iv_fix_ = [1,2,3,4,1,2,3,4]
ivPart_ = [random.randint(0,256) for i in range(8)]

iv = bytearray(iv_fix_ + ivPart_)
print(f"IV: {iv.hex()}")

fwd = cryptolib.aes(key1,mode,iv)
bwd = cryptolib.aes(key1,mode,iv)

pin = random.getrandbits(8*msgBytes) % 1000000
print(f"PIN: {pin}")

# need to generate 16 byte message for encryption (padding)
# standard pkcs7 padding ?
msg = pin.to_bytes(msgBytes,"big") + bytes([16 - msgBytes]*(16 - msgBytes))
print(f"MSG: {msg.hex()}")

encoded = fwd.encrypt(msg)
print(f"ENC: {encoded.hex()}")

decoded = bwd.decrypt(encoded)
print(f"DEC: {decoded.hex()}")

# verify. strip of padding
decoded_pin = int.from_bytes(decoded[:msgBytes],"big")
print(f"DPIN: {decoded_pin}")

print(f"Result: {pin == decoded_pin}")
