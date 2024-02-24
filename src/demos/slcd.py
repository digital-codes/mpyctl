# https://gist.github.com/craigjb/da1bc4200f0378a886a6b4987837551c

from machine import Pin, SPI, PWM
import time
from tools import st7789py
from micropython import const

import framebuf

# LCD Pin Configuration
LCD_CS = 15     # spi cs
LCD_DC = 33     # data/control
LCD_SCLK = 17   # spi clk
LCD_MOSI = 21   # spi mosi
LCD_RST = 34    # reset
LCD_BL = 16     # back light

# Initialize SPI
spi = SPI(2, baudrate=10000000, sck=Pin(LCD_SCLK), mosi=Pin(LCD_MOSI))

# Initialize CS, DC, and RST pins
cs = Pin(LCD_CS, Pin.OUT)
dc = Pin(LCD_DC, Pin.OUT)

rst = Pin(LCD_RST, Pin.OUT)

# Reset the LCD
rst.value(1)
time.sleep(0.1)
rst.value(0)
time.sleep(0.1)
rst.value(1)
time.sleep(0.1)

# Initialize PWM for backlight
bl = PWM(Pin(LCD_BL))
bl.freq(500)  # 500 Hz
bl.duty_u16(50000)  # Maximum brightness (0-65535)


display = st7789py.ST7789(spi, 128, 128, xstart=3, ystart=2,reset=rst, dc=dc)
display.init()
# init for usb connector down
display._set_mem_access_mode(3,0,0,True)
display.fill(st7789py.BLACK)
time.sleep(1)
display.pixel(40, 40, st7789py.YELLOW)
display.pixel(80, 80, st7789py.RED)
display.pixel(80, 40, st7789py.BLUE)
display.line(0,0,30,30, st7789py.RED)
display.line(10,0,30,30, st7789py.GREEN)
display.line(20,0,30,30, st7789py.BLUE)

FONT_WIDTH = const(8)
FONT_HEIGHT = const(8)
PIXEL_LEN = const(2)
FBUF_LEN = const(4096)
tbuf_ = bytearray(FBUF_LEN)
tbuf = memoryview(tbuf_)
def text(display,s, x, y):
    global tbuf
    text_width = len(s) * FONT_WIDTH
    text_mem = text_width * FONT_HEIGHT * PIXEL_LEN
    print(f"tmem: {text_mem}")
    if text_mem > len(tbuf):
        raise ValueError("buffer too small")

    f = framebuf.FrameBuffer(tbuf, text_width,
                                FONT_HEIGHT, framebuf.RGB565)
    f.fill(0)
    f.text(s, 0, 0, 0xffff)
    display.blit_buffer(tbuf[:text_mem], x, y, text_width, FONT_HEIGHT)

text(display,f"wdwq{ 13.5}",10,20)

