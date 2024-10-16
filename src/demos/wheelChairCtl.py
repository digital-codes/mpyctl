#speed pulse: g9
speedPin = 9
#pwm: g6
ctlPin = 6
#extra: g20



speed = Pin(speedPin, Pin.IN, Pin.PULL_UP)


tick = 0
cnt = 0
def cb(p):
    """ interrupt to measure delay between pulses """
    global cnt, tick
    t = time.ticks_ms()
    delta = time.ticks_diff(t, tick)
    tick = t
    cnt += 1
    print(delta) # cnt)

tick = time.ticks_ms()
speed.irq(trigger=Pin.IRQ_FALLING, handler=cb)

# deinit
ctl = Pin(ctlPin, Pin.OUT)    # create output pin on GPIO0
ctl.off()
time.sleep(.5)

#sys.exit()


# start with some slow value
duty = 150
ctl = PWM(Pin(ctlPin), freq=50, duty=duty)

time.sleep(.1)

# pulse delay in range 40 .. 10 ms ~ 25 .. 100 Hz as expected

while duty < 400:
    time.sleep(.4)
    duty += 10
    # print("...",duty)
    ctl.duty(duty)

time.sleep(1)
while duty > 100:
    time.sleep(.4)
    duty -= 10
    # print("...",duty)
    ctl.duty(duty)

time.sleep(1)
# deinit
ctl = Pin(ctlPin, Pin.OUT)    # create output pin on GPIO0
ctl.off()
