"""for M5Stack AtomS3R Cam"""

# should also work with https://github.com/cnadler86/micropython-camera-API
import M5
from M5 import *
from hardware import Pin
from hardware import I2C
import camera
import jpg
import time

i2c1 = None

img = None
img_buf = None
img_jpg = None
jpg_buf = None


def setup():
    global i2c1

    M5.begin()
    i2c1 = I2C(1, scl=Pin(39), sda=Pin(38), freq=100000)
    camera.init(pixformat=camera.RGB565, framesize=camera.FRAME_QQVGA)  # QQVGA or QVGA
    img = camera.snapshot()
    print("image received")
    img_buf = img.bytearray()
    print(len(img_buf))
    img_jpg = jpg.encode(img, 80)
    jpg_buf = img_jpg.bytearray()
    print(len(jpg_buf))
    # save raw image
    with open("img.bin", "wb") as f:
        f.write(img_buf)
    # save jpg image
    with open("img.jpg", "wb") as f:
        f.write(jpg_buf)
    time.sleep(1)


def loop():
    global i2c1
    M5.update()


if __name__ == "__main__":
    try:
        setup()
        while True:
            loop()
    except (Exception, KeyboardInterrupt) as e:
        try:
            from utility import print_error_msg

            print_error_msg(e)
        except ImportError:
            print("please update to latest firmware")
