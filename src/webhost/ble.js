
/**
 * Reset the app variable states.
 */
/*
  0000180a-0000 - 1000 - 8000 -00805f9b34fb(Handle: 26): Device Information
  00002a29-0000 - 1000 - 8000 -00805f9b34fb(Handle: 27): Manufacturer Name String
      mfg val: bytearray(b'Digital Codes')
  00002a25-0000 - 1000 - 8000 -00805f9b34fb(Handle: 31): Serial Number String
      sno val: bytearray(b'1234')
  00002a24-0000 - 1000 - 8000 -00805f9b34fb(Handle: 29): Model Number String
      mdl val: bytearray(b'MpyCtlxxx')

0000181a-0000 - 1000 - 8000 -00805f9b34fb(Handle: 19): Environmental Sensing
  00002a6e-0000 - 1000 - 8000 -00805f9b34fb(Handle: 20): Temperature

00001801-0000 - 1000 - 8000 -00805f9b34fb(Handle: 15): Generic Attribute Profile
  00002a05-0000 - 1000 - 8000 -00805f9b34fb(Handle: 16): Service Changed

00001815-0000 - 1000 - 8000 -00805f9b34fb(Handle: 23): Automation IO
  00002a56-0000 - 1000 - 8000 -00805f9b34fb(Handle: 24): Digital

*/

const AUTO_SRV = "00001815-0000-1000-8000-00805f9b34fb"
const AUTO_WR = "00002a56-0000-1000-8000-00805f9b34fb"
const AUTO_RD = "00002a56-0000-1000-8000-00805f9b34fb"
const SENSE_SRV = "0000181a-0000-1000-8000-00805f9b34fb"
const SENSE_RD = "00002a6e-0000-1000-8000-00805f9b34fb"

const BLE_DEFAULTS = {
    gattServer: null,
    devicePrefix: "MpyCtl",
    autoService: null,
    writeAutoCharacteristic: null,
    readAutoCharacteristic: null,
    senseService: null,
    readSenseCharacteristic: null,
    readIntervall:null,
    senseNotify:false,
    tempId: null
}


let bleVars;

const useNotify = true


let busy = false
let commandQueue = [];

const bleInit = () => {
    bleVars = JSON.parse(JSON.stringify(BLE_DEFAULTS))
    bleVars.tempId = document.getElementById("temp")
}


const readSensor = async () => {
    if (bleVars.gattServer == null) {
        console.log("read without server")
        if (bleVars.readIntervall != null) {
            clearInterval(bleVars.readIntervall);
        }
    } else {
        // read returns dataview. getUintXXX to retrieve value
        const senseVal = await bleVars.readSenseCharacteristic.readValue()
        console.log("Read sensor:",senseVal.getUint16(0, true)/100)
        bleVars.tempId.innerHTML = (senseVal.getUint16(0, true)/100).toString()
    }
}



const handleSensor = (event) => {
    const senseVal = event.target.value
    console.log("New sensor value:",senseVal.getUint16(0, true)/100)
    bleVars.tempId.innerHTML = (senseVal.getUint16(0, true)/100).toString()
}


/**
 * API error handler.
 */
function handleError(error) {
    console.log(error);
    bleInit();
}


function sendCommand(cmd) {
    if (bleVars.writeAutoCharacteristic) {
        // Handle one command at a time
        if (busy) {
            // Queue commands
            commandQueue.push(cmd);
            return Promise.resolve();
        }
        busy = true;

        
        //return writeCharacteristic.writeValue(cmd).then(() => {
        return bleVars.writeAutoCharacteristic.writeValueWithResponse(cmd).then(() => {
                busy = false;
            // Get next command from queue
            let nextCommand = commandQueue.shift();
            if (nextCommand) {
                sendCommand(nextCommand);
            }
        });
    } else {
        return Promise.resolve();
    }
}

function sendMpyCtl(val) {
    console.log('send ctl:', val);
    let cmd = new Uint8Array([val]);

    sendCommand(cmd).then(() => {
        console.log('write ok for: ', val);
    })
        .catch(handleError);
}

const connect = () => {
    if (bleVars.gattServer != null && bleVars.gattServer.connected) {
        console.log("Already connected")
        return
    }
    console.log('Connecting...');
    if ((bleVars.writeAutoCharacteristic == null) && (bleVars.readSenseCharacteristic == null)) {
        navigator.bluetooth.requestDevice({
            filters: [{
                namePrefix: bleVars.devicePrefix,
            }],
            optionalServices: [AUTO_SRV, SENSE_SRV]
        })
            .then(device => {
                console.log('Connecting to GATT Server...');
                return device.gatt.connect();
            })
            .then(server => {
                console.log('> Found GATT server');
                bleVars.gattServer = server;
                // Get command service
                return bleVars.gattServer.getPrimaryService(AUTO_SRV);
            })
            .then(service => {
                console.log('> Found AUTO service');
                bleVars.autoService = service;
                // Get write characteristic
                return bleVars.autoService.getCharacteristic(AUTO_WR);
            })
            .then(characteristic => {
                console.log('> Found auto write characteristic');
                bleVars.writeAutoCharacteristic = characteristic;
            }).then(() => {
                console.log('> Probing Sense Srv');
                // Get command service
                return bleVars.gattServer.getPrimaryService(SENSE_SRV);
            })
            .then(service => {
                console.log('> Found SENSE service');
                bleVars.senseService = service;
                // Get read characteristic
                return bleVars.senseService.getCharacteristic(SENSE_RD);
            })
            .then(characteristic => {
                console.log('> Found sense read characteristic');
                bleVars.readSenseCharacteristic = characteristic;
                if (!useNotify) {
                    // Set the function to be called every x milliseconds
                    bleVars.readIntervall = setInterval(readSensor, 2000);
                } else {
                    // setup notify
                    bleVars.readSenseCharacteristic.addEventListener('characteristicvaluechanged',
                    handleSensor)
                    bleVars.senseNotify = true
                    return bleVars.readSenseCharacteristic.startNotifications()
                }
            }).then(() => {
                document.getElementById("stat").innerHTML = "Connected"
            })
            .catch(handleError);
    } else {
        console.log("services not null",bleVars);
    }
}

const disconnect = async () => {
    if (bleVars.gattServer != null && bleVars.gattServer.connected) {
        if (bleVars.readIntervall != null) {
            clearInterval(bleVars.readIntervall);
        }
        if (bleVars.senseNotify) {
            await bleVars.readSenseCharacteristic.stopNotifications();            
            bleVars.senseNotify = false
            console.log("Notify stopped");
        }
        if (bleVars.gattServer.disconnect) {
            console.log('Disconnecting...');
            await bleVars.gattServer.disconnect();
        }
        bleInit()
        document.getElementById("stat").innerHTML = "Disconnected"
    }
}

export { disconnect, connect, bleInit, sendMpyCtl }
