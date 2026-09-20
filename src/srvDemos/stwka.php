<?php

$cfg = parse_ini_file("../../files/iot/stwk.ini",false);

// we need this for json
$data = json_decode(file_get_contents('php://input'), true);

// forward
function httpPost($url, $d)
{
    $curl = curl_init($url);
	curl_setopt($curl, CURLOPT_POSTFIELDS, json_encode($d));       
	curl_setopt($curl, CURLOPT_HTTPHEADER,array('Content-Type: application/json')); 
    curl_setopt($curl, CURLOPT_RETURNTRANSFER, true);
    //$response = curl_exec($curl);  // retrieves body . not needed here
    curl_exec($curl);
	$stat = curl_getinfo($curl, CURLINFO_HTTP_CODE);
    curl_close($curl);
    return $stat;
}

$target=$cfg["target"];


$f = httpPost($target,$data);
//file_put_contents("log.log", date("Y-m-d H:i:s") . " fwd status: " . $f . PHP_EOL, FILE_APPEND);


?>


