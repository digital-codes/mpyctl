<?php
header("Access-Control-Allow-Origin: *");
header("Content-Type: application/json; charset=UTF-8");

/* fill database paramteres in config.ini */
$cfg = parse_ini_file("../../files/iot/config.ini", false);
//$cfg = parse_ini_file("config.ini", false);

/* we can check parameters via a filter like so: */
/* multiple parms: see https://www.php.net/manual/de/function.filter-input-array.php */
/* for testing with http, call like:
http GET  "http://127.0.0.1:8080" sens==123 last==2
When add_empty (3. parm) is true, all parms will be returned
missing are null
values failing the filter condition (e.g. validate int) are FALSE
*/
$parms = array(
	"days" => FILTER_VALIDATE_INT,
	"sens" => FILTER_VALIDATE_INT
);

$args = filter_input_array(INPUT_GET, $parms,TRUE);

/*
 missing or wrong paramters are False or Null. Must check with triple ===
*/
/*
if (!$args) 
	echo "No args".PHP_EOL;
else {
	print_r($args);
	// the following works only with triple === 
	if ($args["last"] === 0) echo "Last 0" . PHP_EOL;
	if ($args["sens"] === 0) echo "Sens 0" . PHP_EOL;
	if ($args["days"] === 0) echo "days 0" . PHP_EOL;
}
exit();
*/

$last = ($args  & ($args["days"] === 0));

// default period: 14 
$per = ($args  & ($args["days"] > 0)) ? $args["days"] : 14; /* days */


// date computation
$fmt = "Y-m-d h:m:s";
date_default_timezone_set("Europe/Berlin");
// now
$d0 = date($fmt);
//echo "Now: " . $d0 . PHP_EOL;
// target date
$d1 = date_create($d0);
date_sub($d1, date_interval_create_from_date_string($per . " days"));
$d2 = date_format($d1, $fmt);
//echo "New: " . $d2 . PHP_EOL;

$pdo = new PDO('mysql:host=' . $cfg["dbserv"] . ';dbname=' . $cfg["dbname"] , $cfg["dbuser"], $cfg["dbpass"]);
$pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE,PDO::FETCH_ASSOC);
/* $query = "SELECT * from sensors order by `index` asc"; */
/*$query = "SELECT id,count,co2,bat,pres,hum,temp,light,rssi,rfu,date,pkt,rep from sensors order by `index` asc"; */
$query = "SELECT id,req,count,co2,bat,pres,hum,temp,light,rssi,date,pkt,rep from sensors";
/* options to select sensor and to get only the last entry */
if ($args & ($args["sens"] !== Null) & ($args["sens"] !== False)) 
	$query .= " where id = " . $args["sens"];
else
	$query .= " where id >= 0"; // defaults to all

// period
$query .= " and `date` > \"" . $d2 . "\"";

$query .= " order by `date`";

if ($last) 
	$query .= " desc limit 1";
else
	$query .= " asc";


$statement = $pdo->query($query);
$data = array();
foreach ($statement as $row) {
    array_push($data,$row);
}
echo json_encode($data);

?>
