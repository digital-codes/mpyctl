""" mpy version, not m5stack """
import network
import json
import time
import umqtt.simple
import neopixel
import machine
import math

# ### led stuff 
neoPin = 27
p = machine.Pin(neoPin)
rgb = neopixel.NeoPixel(p,25)

#rgb.fill((10,10,10))
#rgb.write()

colMap = {
    "off":(0,0,0),
    "on":(100,100,100),
    "fives":(100,100,0),
    "ones":(0,100,100),
    "idle":(0,50,0),
    "stop":(50,0,0),
    "loaded":(0,0,50),
    "active":(0,100,100),
    "init":(40,40,40),
    "error":(200,0,0)
    }

def rgbFill(color):
    rgb.fill(color)
    rgb.write()

def rgbSet(pos,color):
    rgb[pos-1] = color
    rgb.write()


def timeDisplay():
    global delay
    mins = math.ceil(delay / 60)
    fives = math.floor(mins / 5)
    ones = mins - fives * 5
##    fives = math.floor(delay / 60) // 5
##    ones = mins - fives * 5
##    if ones == 0 and fives > 0:
##        fives -= 1
##        ones = 5
    #print(delay,mins,fives,ones)
    # reset all
    rgbFill(colMap["off"])
    # second pulse
    if 0 == (delay % 2):
        c = colMap["on"]
    else:
        c = colMap["off"] if mins > 1 else colMap["error"]
    for i in range(21,26):
        rgbSet(i,c)

    # fifes go in row 2
    # ones go in row 1
    for i in range(fives):
        rgbSet(i+1,colMap["fives"])
    for i in range(ones):
        rgbSet(i+1+5,colMap["ones"])
        
    
# ### timer stuff
delay = 0
timer = machine.Timer(0)

def tmCount(x):
    global delay
    if delay > 0:
        delay -= 1
        #print("cnt: ",delay)
        timeDisplay()
        mqttConnection.publish(mqttStatusTopic.encode(), str(delay).encode(), retain=False, qos=0)
    else:
        tmStop()       
        #print("stopping")

def tmStop():
    global delay
    #print("stop")
    timer.deinit()
    delay = 0
    rgbFill(colMap["stop"])
    mqttConnection.publish(mqttStatusTopic.encode(), "done".encode(), retain=False, qos=0)
    time.sleep(1)
    rgbFill(colMap["idle"])
    mqttConnection.publish(mqttStatusTopic.encode(), "idle".encode(), retain=False, qos=0)
    

def tmStart():
    #print("start")
    timer.init(period=1000, mode=machine.Timer.PERIODIC, callback=lambda t:tmCount(0))
    

# ### mqtt stuff
cmd = None
mqttHost = "viz.ok-lab-karlsruhe.de"
mqttUser = "listen"
mqttPwd = "listen"
mqttClient = "catclient"
mqttTopic = "cat"
mqttStatusTopic = "catstat"
mqttPort = 1883
mqttConnection = None

# ###########

def cmdHandler(topic,msg):
    global delay, mqttConnection
    #print(topic,msg)
    cmd = msg.decode().lower()
    if not topic.decode().lower() == mqttTopic:
        return
    if cmd == 'start':
        if delay > 0:
            rgbFill(colMap["active"])
            tmStart()
            mqttConnection.publish(mqttStatusTopic.encode(), "active".encode(), retain=False, qos=0)
    elif cmd == 'stop':
        tmStop()
        rgbFill(colMap["stop"])
        time.sleep(1)
        rgbFill(colMap["idle"])
        mqttConnection.publish(mqttStatusTopic.encode(), "idle".encode(), retain=False, qos=0)
    else:
        try:
            # set for 1 seconds
            tmStop() # stop first
            delay = int(cmd)
            #print("delay: ",delay)
            rgbFill(colMap["loaded"])
            mqttConnection.publish(mqttStatusTopic.encode(), "loaded".encode(), retain=False, qos=0)
            pass
        except:
            rgbFill(colMap["error"])
            mqttConnection.publish(mqttStatusTopic.encode(), "error".encode(), retain=False, qos=0)
    pass

##
##def timeDisplay(run=True):
##    global delay
##    mins = delay // 6
##    fives = mins // 5
##    ones = mins % 5
##    print(delay,mins,fives,ones)
##    # reset all
##    rgb.setColorAll(0x000000)
##    # status row 5. red or green
##    if run:
##        rgb.setColorFrom(21, 25, 0x00ff00)
##    else:
##        rgb.setColorFrom(21, 25, 0xff0000)
##
##    # fifes go in row 2
##    # ones go in row 1
##    # fives are blue
##    for i in range(fives):
##        rgb.setColorFrom(6, 6+i, 0x0000ff)
##    # ones are yellow
##    for i in range(ones):
##        rgb.setColorFrom(1, 1+i, 0x00ffff)
##


# ### start up
rgbFill(colMap["init"])

wlan = network.WLAN(network.STA_IF)  # STA_IF stands for Station (client) interface
wlan.active(True)

wlan.disconnect()
time.sleep(1)

ssid = "karlsruhe.freifunk.net"  # Replace with your Wi-Fi network name (SSID)
password = ""  # Replace with your Wi-Fi network password

if not password == "":
    wlan.connect(ssid, password)
else:
    wlan.connect(ssid)

while not wlan.isconnected():
    print("Waiting for Wi-Fi")
    time.sleep(1)

print("IP address:", wlan.ifconfig()[0])

# ### mqtt connect

mqttConnection = umqtt.simple.MQTTClient(mqttClient, mqttHost, port=mqttPort,
                                         user=mqttUser, password=mqttPwd,
                                         keepalive=300, ssl=False, ssl_params={})

mqttConnection.connect()

if mqttConnection == None:
    print("Failed")
else:
    mqttConnection.set_callback(cmdHandler)
    mqttConnection.subscribe(mqttTopic.encode(), qos=1)
    #mqttConnection.wait_msg()
    #mqttConnection.check_msg()
    rgbFill(colMap["idle"])
    mqttConnection.publish(mqttStatusTopic.encode(), "idle".encode(), retain=False, qos=0)
    while True:
        #mqttConnection.wait_msg()
        mqttConnection.check_msg()
        time.sleep_ms(200)
        mqttConnection.ping()

