import machine
import st7789py
import time

i2c = machine.I2C(0,scl=machine.Pin(0),sda=machine.Pin(45),freq=400000)
print(i2c.scan())

lp5562_addr = 0x30

# enable chip
# Write to address 00h 0100 0000b (chip_en to '1')
i2c.writeto_mem(lp5562_addr,0x0,bytes([0x40]))
# internal clock
#Write to address 08h 0000 0001b (enable internal clock)
i2c.writeto_mem(lp5562_addr,0x8,bytes([1]))
# PWM frequency is either 256 Hz or 558 Hz. Frequency is set with PWM_HF bit in register 08h. 
# When the PWM_HF bit is 1, the PWM frequency is 558 Hz.
i2c.writeto_mem(lp5562_addr,0x8,bytes([1 << 6]))
#Write to address 70h 0000 0000b (Configure all LED outputs to be controlled from I2C registers)
i2c.writeto_mem(lp5562_addr,0x70,bytes([0]))
# white pwm and current
i2c.writeto_mem(lp5562_addr,0xe,bytes([0x40]))
i2c.writeto_mem(lp5562_addr,0xf,bytes([0x80]))
print(i2c.readfrom_mem(lp5562_addr,0xe,2))

# LCD Pin Configuration
LCD_CS = 14     # spi cs
LCD_DC = 42     # data/control
LCD_SCLK = 15   # spi clk
LCD_MOSI = 21   # spi mosi
LCD_RST = 48    # reset
# LCD_BL = via lp5562

# Initialize SPI
spi = machine.SPI(1, baudrate=10000000, sck=machine.Pin(LCD_SCLK), mosi=machine.Pin(LCD_MOSI))

print(spi)

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

display = st7789py.ST7789(spi, 128, 128, xstart=3, ystart=2,reset=rst, dc=dc)
display.init()
# init for usb connector down
display._set_mem_access_mode(3,0,0,True)

col = st7789py.color565(100,150,200)
display.fill(col)

while True:
    col = st7789py.color565(100,0,0)
    display.fill(col)
    time.sleep(1)
    col = st7789py.color565(0,100,0)
    display.fill(col)
    time.sleep(1)
    col = st7789py.color565(0,0,100)
    display.fill(col)
    time.sleep(1)
    


