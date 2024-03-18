""" demo for encrypt, decrypt
NB: in same program forward and backward cannot use same instance!
"""
import cryptolib
import random

# define key and iv
# Shared secret key
key1 = b'0123456789ABCDEF'  # 16 bytes key
key2 = b'123456789ABCDEF1'  # 16 bytes key
#iv = b'\x00' * 16
mode = 1 # ECB. requires no iv

#Encryption Process: The plaintext is divided into blocks of fixed size, and each block is encrypted
#separately using the same key. Each block is independent, meaning the same plaintext block will 
#always produce the same ciphertext block.
#Security Consideration: ECB mode is susceptible to certain attacks, especially when encrypting large
#amounts of data or when the plaintext contains patterns, as identical plaintext blocks produce
#identical ciphertext blocks.

fwd = cryptolib.aes(key1,mode) #,iv)
bwd = cryptolib.aes(key1,mode) # ,iv)

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


