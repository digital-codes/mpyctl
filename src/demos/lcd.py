# https://gist.github.com/craigjb/da1bc4200f0378a886a6b4987837551c

from machine import Pin, SPI, PWM
import time

# LCD Pin Configuration
LCD_CS = 15     # spi cs
LCD_DC = 33     # data/control
LCD_SCLK = 17   # spi clk
LCD_MOSI = 21   # spi mosi
LCD_RST = 34    # reset
LCD_BL = 16     # back light


COL_OFFSET = 3
ROW_OFFSET = 2


# Initialize SPI
spi = SPI(2, baudrate=20000000, sck=Pin(LCD_SCLK), mosi=Pin(LCD_MOSI))

# Initialize CS, DC, and RST pins
cs = Pin(LCD_CS, Pin.OUT)
dc = Pin(LCD_DC, Pin.OUT)
rst = Pin(LCD_RST, Pin.OUT)


# Initialize PWM for backlight
bl = PWM(Pin(LCD_BL))
bl.freq(500)  # 500 Hz
bl.duty_u16(50000)  # Maximum brightness (0-65535)



cmds = {
    "sleepIn":0x10,
    "sleepOut": 0x11,
    "modePartial":0x12,
    "modeNormal":0x13,
    "inversionOn":0x21,
    "inversionOff":0x20,
    "displayOff":0x28,
    "displayOn":0x29,
    "idleOn":0x39,
    "idleOff":0x38,
    "colAddrSet":0x2a,
    "pageAddrSet":0x2b,
    "memWrite":0x2c,
    "pixFormat":0x3a
}


# Example init and basic routines for 0.85" 128x128 pixel LCD
# Sold under Wisevision N085-1212TBWIG41-H12
#
# Unnecessary init commands have been stripped out versus other 
# routines I found online



def write_cmd(cmd):
    dc.value(0)
    cs.value(0)
    spi.write(bytearray([cmd]))
    cs.value(1)


def write_cmd_data(cmd, data):
    dc.value(0)
    cs.value(0)
    spi.write(bytearray([cmd]))
    dc.value(1)
    spi.write(bytearray(data))
    cs.value(1)

def write_data(data):
    dc.value(1)
    cs.value(0)
    spi.write(bytearray(data))
    cs.value(1)


def init_lcd():
    # reset required on power up
    cs.value(1)
    rst.value(1)
    time.sleep(0.1)
    rst.value(0)
    time.sleep(0.1)
    rst.value(1)
    time.sleep(0.1)

    # Sleep out
    write_cmd(cmds["sleepOut"])

    # Display inversion off
    write_cmd(cmds["inversionOff"])

    # Display on
    write_cmd(cmds["displayOn"])
    # Wait 20 ms
    time.sleep(.020)

    # Normal mode
    write_cmd(cmds["modeNormal"])
    # Wait 20 ms
    time.sleep(.020)


def hi_byte(d):
    return (d & 0xFF00) >> 8


def lo_byte(d):
    return (d & 0xFF)


def set_window(x, y, width, height):
    col = x + COL_OFFSET
    col_data = [
        hi_byte(col), lo_byte(col),
        hi_byte(col + width - 1), lo_byte(col + width - 1)
    ]
    row = y + ROW_OFFSET
    row_data = [
        hi_byte(row), lo_byte(row),
        hi_byte(row + height - 1), lo_byte(row + height - 1)
    ]

    write_cmd_data(0x2A,col_data)
    write_cmd_data(0x2B,row_data)
    #write_cmd(0x2C)  # Memory write. important!


def write_window(x, y, width, height, data):
    #print("Len data:",len(data))
    set_window(x, y, width, height)
    write_cmd_data(0x2C,data)

    
def clear_to_color(color_r5g6b5):
    hi = hi_byte(color_r5g6b5)
    lo = lo_byte(color_r5g6b5)
    for y in range(128):
        write_window(0, y, 128, 1, [hi, lo, 0x80] * 128)

def gradient():
    r = 0x00
    g = 0x80
    b = 0x00
    for y in range(128):
        write_window(0, y, 128, 1, [r, g - y, b + y] * 128)


# Function to fill a rectangle with a gradient
def fill_gradient():
    width, height = 128, 128
    for y in range(height):
        red = 0x80 # 255 - int((y / height) * 255)
        blue = 0x80 # int((y / height) * 255)
        green = y # 0x40
        row_data = bytes([red,blue,green] * width)
        write_window(0,y, width - 1, 1, row_data)


# Main function to initialize and draw gradient
def main():
    # Initialize the LCD (add your LCD initialization sequence)
    print("Init")
    init_lcd()
    time.sleep(.200)
    print("on")
    write_cmd(cmds["displayOn"])
    time.sleep(1)

    print("off")
    write_cmd(cmds["displayOff"])

    time.sleep(1)
    print("on")
    write_cmd(cmds["displayOn"])

    time.sleep(1)
    print("invert")
    write_cmd(cmds["inversionOn"])

    time.sleep(1)
    print("invert off")
    write_cmd(cmds["inversionOff"])

    time.sleep(1)

    print("clear")
    clear_to_color(0xff00) #0x4567)

    time.sleep(2)

    print("clear")
    clear_to_color(0x00ff) #0x4567)

    time.sleep(2)

    print("clear")
    clear_to_color(0xffff) #0x4567)

    time.sleep(2)

    print("fill")
    fill_gradient()

    print("done")
    time.sleep(2)

    print("fill2")
    gradient()

    print("done")
    time.sleep(2)


if __name__ == "__main__":
    main()


