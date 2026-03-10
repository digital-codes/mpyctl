# display abstraction for atoms
import sys

sys.path.append("")
from micropython import const
import machine

# colors are (r,g,b) tuples or like st7789py.YELLOW


class DisPlay:
    def __init__(self, config):
        if config["io"].get("led") != None:
            import neopixel
            neoPin = config["io"]["led"]
            p = machine.Pin(neoPin)
            self.hardware = neopixel.NeoPixel(p,1)
            self.type = "neopixel"
        elif config["io"].get("lcd") == "s3atom":
            import st7789py
            import framebuf # only for text
            import time
            self.framebuf = framebuf
            # LCD Pin Configuration
            LCD_CS = 15     # spi cs
            LCD_DC = 33     # data/control
            LCD_SCLK = 17   # spi clk
            LCD_MOSI = 21   # spi mosi
            LCD_RST = 34    # reset
            LCD_BL = 16     # back light

            # Initialize SPI
            spi = machine.SPI(2, baudrate=10000000, sck=machine.Pin(LCD_SCLK), mosi=machine.Pin(LCD_MOSI))

            # Initialize CS, DC, and RST pins
            cs = machine.Pin(LCD_CS, machine.Pin.OUT)
            dc = machine.Pin(LCD_DC, machine.Pin.OUT)

            rst = machine.Pin(LCD_RST, machine.Pin.OUT)

            # Reset the LCD
            rst.value(1)
            time.sleep(0.1)
            rst.value(0)
            time.sleep(0.1)
            rst.value(1)
            time.sleep(0.1)

            # Initialize PWM for backlight
            bl = machine.PWM(machine.Pin(LCD_BL))
            bl.freq(500)  # 500 Hz
            bl.duty_u16(50000)  # Maximum brightness (0-65535)

            display = st7789py.ST7789(spi, 128, 128, xstart=3, ystart=2,reset=rst, dc=dc)
            display.init()
            # init for usb connector down
            display._set_mem_access_mode(3,0,0,True)
            self.hardware = display
            self.type = "lcd"
            self.convertColor = st7789py.color565
            
            self.FONT_WIDTH = const(8)
            self.FONT_HEIGHT = const(8)
            self.PIXEL_LEN = const(2)
            self.FBUF_LEN = const(4096)
            self.tbuf_ = bytearray(self.FBUF_LEN)
            self.tbuf = memoryview(self.tbuf_)
            
        else:
            self.type = None
    
    def fill(self, color):
        if self.type == "neopixel":
            self.hardware.fill(color)
            self.hardware.write()
        elif self.type == "lcd":
            col = self.convertColor(color[0],color[1],color[2])
            self.hardware.fill(col)
        else:
            return
        
    def line(self, x1,y1,x2,y2,color):
        if self.type == "lcd":
            col = self.convertColor(color[0],color[1],color[2])
            self.hardware.line(x1,y1,x2,y2,col)
        else:
            return 
        
    def pixel(self, x,y,color):
        if self.type == "lcd":
            col = self.convertColor(color[0],color[1],color[2])
            self.hardware.pixel(x,y,col)
        else:
            return  

    def text(self, s, x, y):
        if self.type == "lcd":
            text_width = len(s) * self.FONT_WIDTH
            text_mem = text_width * self.FONT_HEIGHT * self.PIXEL_LEN
            print(f"tmem: {text_mem}")
            if text_mem > len(self.tbuf):
                raise ValueError("buffer too small")

            f = self.framebuf.FrameBuffer(self.tbuf, text_width,
                                        self.FONT_HEIGHT, self.framebuf.RGB565)
            f.fill(0)
            f.text(s, 0, 0, 0xffff)
            self.hardware.blit_buffer(self.tbuf[:text_mem], x, y, text_width, self.FONT_HEIGHT)
        else:
            return

    