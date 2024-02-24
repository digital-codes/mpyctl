from numbers import Number
from m5stack import *
from m5ui import *
from uiflow import *
import wifiCfg
from m5mqtt import M5mqtt

rgb.set_screen([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
               0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])

cmd = None
delay = None


def fun_cat_(topic_data):
    global cmd, delay
    cmd = topic_data
    if cmd == 'start':
        # rgb.setColorAll(0x33ff33)
        timeDisplay(True)
        # timer every 10 seconds
        timerSch.run('timer1', 10000, 0x00)
    elif cmd == 'stop':
        rgb.setColorAll(0xff0000)
        timerSch.stop('timer1')
    else:
        try:
            # set for 10 seconds
            delay = 6 * int(cmd)
            rgb.setColorAll(0x000000)
            timeDisplay(False)
            pass
        except:
            rgb.setColorAll(0x666666)
    pass


def timeDisplay(run=True):
    global delay
    mins = delay // 6
    fives = mins // 5
    ones = mins % 5
    print(delay,mins,fives,ones)
    # reset all
    rgb.setColorAll(0x000000)
    # status row 5. red or green
    if run:
        rgb.setColorFrom(21, 25, 0x00ff00)
    else:
        rgb.setColorFrom(21, 25, 0xff0000)

    # fifes go in row 2
    # ones go in row 1
    # fives are blue
    for i in range(fives):
        rgb.setColorFrom(6, 6+i, 0x0000ff)
    # ones are yellow
    for i in range(ones):
        rgb.setColorFrom(1, 1+i, 0x00ffff)


@timerSch.event('timer1')
def ttimer1():
    global cmd, delay
    print(delay)
    if delay == 0:
        timerSch.stop('timer1')
        rgb.setColorAll(0xff0000)
    else:
        delay = (delay if isinstance(delay, Number) else 0) + -1
        timeDisplay()
        pass


rgb.setColorAll(0xffff33)
delay = 0
wifiCfg.doConnect('karlsruhe.freifunk.net', '')
while not (wifiCfg.wlan_sta.isconnected()):
    rgb.setColorAll(0xff99ff)
m5mqtt = M5mqtt('', 'viz.ok-lab-karlsruhe.de', 1883, 'listen', 'listen', 300)
m5mqtt.subscribe(str('cat'), fun_cat_)
m5mqtt.start()
rgb.setColorAll(0xffffff)
