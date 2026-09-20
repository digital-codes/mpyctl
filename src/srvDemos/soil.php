<?php

/*
ttn:
https://www.thethingsnetwork.org/docs/applications/http/

auth hdr: "ttnsoil"

format:
    {
  "app_id": "my-app-id",              // Same as in the topic
  "dev_id": "my-dev-id",              // Same as in the topic
  "hardware_serial": "0102030405060708", // In case of LoRaWAN: the DevEUI
  "port": 1,                          // LoRaWAN FPort
  "counter": 2,                       // LoRaWAN frame counter
  "is_retry": false,                  // Is set to true if this message is a retry (you could also detect this from the counter)
  "confirmed": false,                 // Is set to true if this message was a confirmed message
  "payload_raw": "AQIDBA==",          // Base64 encoded payload: [0x01, 0x02, 0x03, 0x04]
  "payload_fields": {},               // Object containing the results from the payload functions - left out when empty
  "metadata": {
    "time": "1970-01-01T00:00:00Z",   // Time when the server received the message
    "frequency": 868.1,               // Frequency at which the message was sent
    "modulation": "LORA",             // Modulation that was used - LORA or FSK
    "data_rate": "SF7BW125",          // Data rate that was used - if LORA modulation
    "bit_rate": 50000,                // Bit rate that was used - if FSK modulation
    "coding_rate": "4/5",             // Coding rate that was used
    "gateways": [
      {
        "gtw_id": "ttn-herengracht-ams", // EUI of the gateway
        "timestamp": 12345,              // Timestamp when the gateway received the message
        "time": "1970-01-01T00:00:00Z",  // Time when the gateway received the message - left out when gateway does not have synchronized time
        "channel": 0,                    // Channel where the gateway received the message
        "rssi": -25,                     // Signal strength of the received message
        "snr": 5,                        // Signal to noise ratio of the received message
        "rf_chain": 0,                   // RF chain where the gateway received the message
        "latitude": 52.1234,             // Latitude of the gateway reported in its status updates
        "longitude": 6.1234,             // Longitude of the gateway
        "altitude": 6                    // Altitude of the gateway
      },
      //...more if received by more gateways...
    ],
    "latitude": 52.2345,              // Latitude of the device
    "longitude": 6.2345,              // Longitude of the device
    "altitude": 2                     // Altitude of the device
  },
  "downlink_url": "https://integrations.thethingsnetwork.org/ttn-eu/api/v2/down/my-app-id/my-process-id?key=ttn-account-v2.secret"
}

test with httpi like:
http POST https://critical-sensors.de/soil.php msg="abs" Authorization:ttnsoil dev_id=1 counter=5 payload_fields:='{"c":2,"t":-5,"w":3}'


*/


try {
    $input = json_decode(file_get_contents('php://input'), true);
		    
    $result = json_encode($input);

    // assume no errors: return 200
    header('HTTP/1.0 200 OK');

} catch (Exception $e) {
		//if ($e->getCode() == ApiException::MALFORMED_INPUT) {
		header('HTTP/1.0 409 Bad Request');
		$result = ['message' => $e->getMessage()];
}

$h = getallheaders();

$hdrs = json_encode($h);
 
header('Content-Type: application/json');


//print($result);
if ("Authorization" == array_search("ttnsoil",$h)) {
  $dt = Array();
  $dt["date"] = date("Y-m-d H:i:s");
  $dt["dev"] = $input["dev_id"];
  $dt["frame"] = $input["counter"];
  $pl = $input["payload_fields"];
  $dt["c"] = $pl["c"]; // conductivity
  $dt["t"] = $pl["t"]; // Temperature
  $dt["w"] = $pl["w"]; // water

  file_put_contents("soil.log", json_encode($dt) . PHP_EOL, FILE_APPEND);

  // 2021-03-02: also send post request to oklab
  // data
  $pr = array(
    "dev"=>$input["dev_id"],
    "frame"=>$input["counter"],
    "c"=>$input["payload_fields"]["c"],
    "t"=>$input["payload_fields"]["t"],
    "w"=>$input["payload_fields"]["w"]
  );
  // add token
  $pr["token"] = "phohTie7ahKeegoo4Gei";
  $prs = json_encode($pr);
  $url = "https://data.ok-lab-karlsruhe.de/index.php/api/v1/soil";
  //$hdr = array('Content-Type: application/json','Accept: application/json');
  $hdr = array('Content-Type: application/json',"Content-Length: " . strval(strlen($prs)),'Accept: application/json');          
  $cc = curl_init($url);
  curl_setopt($cc, CURLOPT_HTTPHEADER, $hdr);                       
  curl_setopt($cc, CURLOPT_POSTFIELDS, $prs);
  curl_setopt($cc, CURLOPT_RETURNTRANSFER, true);
  // don't want to see header
  curl_setopt($cc, CURLOPT_HEADER, false);
  curl_exec($cc);
  $st = curl_getinfo($cc, CURLINFO_HTTP_CODE);
  curl_close($cc);

  if ($st != 200){
    file_put_contents("soil1.log", date("Y-m-d H:i:s ") . "Post error:" . $st . PHP_EOL, FILE_APPEND);
  } 


} else {
  file_put_contents("soil1.log", date("Y-m-d H:i:s ") . "headers: " . $hdrs . ", data: " . $result . PHP_EOL, FILE_APPEND);
}

?>


