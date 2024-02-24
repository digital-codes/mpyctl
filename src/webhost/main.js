import './style.css'
import { bleInit, connect, disconnect,sendMpyCtl } from './ble.js'

document.querySelector('#app').innerHTML = `
<div id="ble" style="display:none;">
  <div>
    <p>BLE testing</p>
    <button id="b1">Connect</button>
    <button id="b2">Disconnect</button>
    <p id="stat" ></p>
  </div>

  <div>
    <p>Sensing</p>
    <p id="temp" >111</p>
  </div>

  <div>
    <p>Automation</p>
    <button id="l1">On</button>
    <button id="l2">Off</button>
    <p id="led" >&nbsp;</p>
  </div>
</div>

`


const ledOn = () => {
  console.log("led on")
  sendMpyCtl(1)  
}

const ledOff = () => {
  console.log("led off")
  sendMpyCtl(0)  
}



/**
   * Check if browser supports Web Bluetooth API.
   */
if (navigator.bluetooth != undefined) {
  document.getElementById("ble").style.display = "block";
  bleTest()
} else {
  console.assert("No bleutooth")
  alert("No bluetooth")
}


function bleTest() {
  bleInit()
  document.getElementById("b1").addEventListener("click", connect)
  document.getElementById("b2").addEventListener("click", disconnect)

  document.getElementById("l1").addEventListener("click", ledOn)
  document.getElementById("l2").addEventListener("click", ledOff)

  /**
   * Set the color of the display button to the currently selected palette color.
   */
  async function buttonClicked(event) {
    let id = event.target.id;
    console.log("button:", id)
    if (id == "button1") {
      sendMpyCtl(1)
      console.log("sent1")
    } else {
      sendMpyCtl(0)
      console.log("sent2")
    }
  }
}
