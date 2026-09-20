<?php

include_once "crc16x25.php";
include_once "wiesesolinsert.php";

// we need this for json
$data = json_decode(file_get_contents('php://input'), true);

// data is like  {"Payload":"0303130023333034616263643739","PacketType":"up", ..

$payload = $data["Payload"];
$type = $data["PacketType"];

file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " T:" . $type . PHP_EOL, FILE_APPEND);

$crcCheck = "ERROR";
if ($type == "up"){
  $crc16 = new Crc16();
  // Convert hex string to byte array. do not include last 2 bytes (the CRC itself) in the data for computing the CRC
  $dataWithCrc = array_map('hexdec', str_split($payload, 2));
  $dataRaw = array_slice($dataWithCrc, 0, -2); // exclude last 2 bytes (the CRC itself) for computing the CRC
  file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " Sliced" . PHP_EOL, FILE_APPEND);
  $resultWithCrc = $crc16->ComputeCrc($CRC_16_X_25_, $dataRaw);
  file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " Result crc" . PHP_EOL, FILE_APPEND);
  $inputCrc = ($dataWithCrc[count($dataWithCrc) - 2] << 8) | $dataWithCrc[count($dataWithCrc) - 1];
  file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " Input crc" . PHP_EOL, FILE_APPEND);
  if ($resultWithCrc->Crc == $inputCrc) {
    file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " CRC good" . PHP_EOL, FILE_APPEND);
    $crcCheck = "OK";

    $cfg = parse_ini_file("/var/www/files/iot/config.ini", true);
    file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " Config OK" . PHP_EOL, FILE_APPEND);
    $dbhost = $cfg['db']['dbserv'] ?? 'localhost';
    $dbname = $cfg['db']['dbname'] ?? 'your_database';
    $dbuser = $cfg['db']['dbuser'] ?? 'your_username';
    $dbpwd = $cfg['db']['dbpass'] ?? 'your_password';
    file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " DB:" . $dbhost . ", " . $dbname . " ," .  $dbuser . ", " . $dbpwd . $PHP_EOL, FILE_APPEND);

    // prepare the row
    $row = unpackPayload($dataRaw);
    file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " Converted" . json_encode($row) . PHP_EOL, FILE_APPEND);
    // skip id = 0, used during join sequence
    if ($row["id"] != 0){  
      $result = insertRow($dbhost, $dbname, $dbuser, $dbpwd,$row);
      file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " Inserted: " . $result . PHP_EOL, FILE_APPEND);
    }
  } else {
    file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " CRC bad" . PHP_EOL, FILE_APPEND);
  }

}

file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " P: " . $payload . " T:" . $type . PHP_EOL, FILE_APPEND);


file_put_contents("/var/www/html/cs/wiessl.log", date("Y-m-d H:i:s") . " fwd status: " . json_encode($data) . ", CRC: " . $crcCheck . PHP_EOL, FILE_APPEND);

echo "Received: " . json_encode($data);


?>


