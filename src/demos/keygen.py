import hashlib

# Example MAC address and salt
mac_address = "00:1A:2B:3C:4D:5E"
salt = "exampleSalt"

# Concatenate the MAC address and salt
input_string = mac_address + salt

# Hash the concatenated string using SHA-256
hash_result = hashlib.sha256(input_string.encode()).hexdigest()

# Convert the hash to an integer and get the last 6 digits
encrypted_key = str(int(hash_result, 16))[-6:]

print("encrypted_key",encrypted_key)

