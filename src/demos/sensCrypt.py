import binascii
import struct
import random

try:
    import machine
    arch = "micropython"
    from crcX25 import crc16_x25
    import cryptolib
    x25crc = crc16_x25
except ImportError:
    print("Not running on micropython")
    arch = "host"
    from Crypto.Cipher import AES
    import libscrc
    x25crc = libscrc.x25

# crc is x25
# micropython


# sensdata is a bytearray, 32 bytes, forst 16 bytes is crap
# upper 16 bytes are filled with values
def insertSensor(id,temp,hum,pres,cnt,fmt=1):
    dset = struct.pack("!BBBBHHHHH",id,fmt,0,0,cnt,temp,hum,0,pres)
    print(dset)
    crc_ = x25crc(dset)
    crc = struct.pack("!H",crc_)
    print("CRC:",hex(crc_))
    sensData = bytearray([0]*16) + bytearray(list(dset)) + bytearray(list(crc))
    return sensData
    
d = insertSensor(1,2,3,4,5)
print(bytes(d),len(d))


_bleKey = b"Critical Zones20"
_ivBase = bytearray([0]*12) # first 3/4 iv
_cryptMode = 2 # CBC

def encryptMsgWithIv(msg):
    global _bleKey, _ivBase, _cryptMode
    #print(f"Msg: {msg.hex()}")
    ivPart_ = bytearray([random.randint(0,256) for i in range(4)])
    # ivPart_ = bytearray([1,2,3,4])
    iv = _ivBase + ivPart_
    #print(f"IV: {iv}")
    if arch == "host":
        fwd = AES.new(_bleKey, AES.MODE_CBC, IV=bytes(iv))
    else:   
        fwd = cryptolib.aes(_bleKey,_cryptMode,iv)
    encoded = fwd.encrypt(msg)
    return encoded

cryptData = encryptMsgWithIv(bytes(d))
print(cryptData.hex(),len(cryptData))


def checkMsg(msg):
    global _bleKey,_cryptMode
    if arch == "host":
        decryptor = AES.new(_bleKey, AES.MODE_CBC, IV=b"0000000000000000")
    else:
        decryptor = cryptolib.aes(_bleKey,_cryptMode,b"0000000000000000")
    encrypted = binascii.unhexlify(msg)
    #print("Encrypted: ",encrypted,len(encrypted))
    decrypted = decryptor.decrypt(encrypted)
    # first 16 bytes are garbade due to random IV
    payload = decrypted[16:]
    print("Decrypted: ",payload)
    # we expect 16 bytes
    if len(payload) != 16:
        print("Invalid payload length")
        return False

    # B: unsigned char
    # H: unsigned short
    payload_format = "!BBBBHHHHHH"
    payload_sc = struct.unpack(payload_format, payload)
    print(payload_sc)
    crc_rx = payload_sc[-1]
    print("Received CRC: ",crc_rx)
    # probably arduino library uses x25 crc algorithm
    crc = x25crc(payload[:14])
    print("Computed crc:",crc)

    if crc == crc_rx:
        print("CRC matching")
        return True
    else:
        print("CRC error")
        return False

check = checkMsg(cryptData.hex())
print("Check:",check)

