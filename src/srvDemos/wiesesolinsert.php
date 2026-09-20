<?php
/*

| index | id   | req  | bat  | rfu  | count | light | temp  | hum   | co2  | date                | rssi | pkt   | raw                              | pres | rep  |
+-------+------+------+------+------+-------+-------+-------+-------+------+---------------------+------+-------+----------------------------------+------+------+
| 84727 |    3 |    1 |  228 |    0 |  1399 |    18 | 27.03 |  44.2 |  409 | 2026-08-17 11:34:42 | -256 | 14747 | 0301e41205770a8f114401990000a320 |    0 |    0 |
| 84726 |    3 |    1 |  228 |    0 |  1398 |    48 | 27.05 | 45.52 |  405 | 2026-08-17 10:37:19 | -256 | 14746 | 0301e43005760a9111c801950000cc5b |    0 |

+-------+-------------+------+-----+---------+----------------+
| Field | Type        | Null | Key | Default | Extra          |
+-------+-------------+------+-----+---------+----------------+
| index | bigint(20)  | NO   | MUL | NULL    | auto_increment |
| id    | int(11)     | YES  |     | NULL    |                |
| req   | int(11)     | YES  |     | NULL    |                |
| bat   | float       | YES  |     | 0       |                |
| rfu   | float       | YES  |     | 0       |                |
| count | int(11)     | YES  |     | NULL    |                |
| light | float       | YES  |     | NULL    |                |
| temp  | float       | YES  |     | NULL    |                |
| hum   | float       | YES  |     | NULL    |                |
| co2   | float       | YES  |     | NULL    |                |
| date  | varchar(50) | YES  |     | NULL    |                |
| rssi  | float       | YES  |     | -125    |                |
| pkt   | int(11)     | YES  |     | NULL    |                |
| raw   | varchar(50) | YES  |     | NULL    |                |
| pres  | float       | YES  |     | 0       |                |
| rep   | int(11)     | YES  |     | NULL    |                |
+-------+-------------+------+-----+---------+----------------+


*/


/**
 * Database connection parameters
 * These should ideally come from environment variables or a config file

$cfg = parse_ini_file("../../files/iot/config.ini", false);

$dbhost = $cfg['db']['dbserv'] ?? 'localhost';
$dbname = $cfg['db']['dbname'] ?? 'your_database';
$dbuser = $cfg['db']['dbuser'] ?? 'your_username';
$dbpwd = $cfg['db']['dbpass'] ?? 'your_password';

*/


/** decode python struct into array */
function unpackPayload(array $dataArray)
{

    // Step 1: Pack bytes 0-3 into binary string for the 4 unsigned chars
    $binaryBytes = chr($dataArray[0]) . chr($dataArray[1]) . chr($dataArray[2]) . chr($dataArray[3]);
    $unpackedBytes = unpack('C4', $binaryBytes);
    
    // Step 2: Pack remaining bytes 4-21 into binary string for the 9 unsigned shorts
    $shortsBinary = '';
    for ($i = 4; $i < 22; $i++) {
        $shortsBinary .= chr($dataArray[$i]);
    }
    $unpackedShorts = unpack('n9', $shortsBinary);

    if ($unpackedBytes === false || $unpackedShorts === false) {
        return false;
    }
    $unpacked = array_merge($unpackedBytes, $unpackedShorts);

    /*
            sensor_ID,  # Sensor ID                                            
            dataFormat,  # Data format version
            0,  # bat
            0,  # Reserved
            # unsigned short 
            data_packet["cnt"],
            data_packet["light"],
            int(data_packet["temp"] + 273) * 10,  # add Kelvin conversion and scale up
            int(data_packet["hum"]),
            data_packet["co2"],
            int(data_packet["pres"]),    # Convert to deci-Pascals
            # new items
            data_packet["r"],
            data_packet["g"],
            data_packet["b"],
    */

    // Map indices to your database column names
    // Indices start at 1 in unpack() result
    // compute float from 3 imu values  
    $rfu = ($unpackedShorts[7] + $unpackedShorts[8] * 256 + $unpackedShorts[9] * 256 * 256);
    $result = [
        'id' => $unpackedBytes[1],
        'req' => $unpackedBytes[2],
        'bat' => ((float)$unpackedBytes[3])/10.0,
        'count' => $unpackedShorts[1],
        'pkt' => $unpackedShorts[1], // copy count to pkt for now
        'light' => $unpackedShorts[2],
        'temp' => (float)(((float)($unpackedShorts[3]) / 10.0) - 273.0), // Convert back to Celsius and scale down
        'hum' => $unpackedShorts[4],
        'co2' => $unpackedShorts[5],
        'rssi' => null,
        'raw' => null,
        'pres' => $unpackedShorts[6],
        'rfu' => $rfu,                   // Computed from imu_x, imu_y, imu_z
        'rep' => null,
        // Append current date/time
        'date'  => (new DateTime('now', new DateTimeZone(date_default_timezone_get())))->format('Y-m-d H:i:s'),
    ];

    return $result;
}


/**
 * Insert one row into the sensor_data table
 * 
 * @param string $dbhost Database host
 * @param string $dbname Database name
 * @param string $dbuser Database username
 * @param string $dbpwd Database password
 * @param array $row Single row associative array containing row data
 * @return bool True on success, false on failure
 */
function insertRow(string $dbhost, string $dbname, string $dbuser, string $dbpwd, array $row): bool
{
    try {
        // Establish PDO connection
        $dsn = "mysql:host=$dbhost;dbname=$dbname;charset=utf8mb4";
        $options = [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ];

        $pdo = new PDO($dsn, $dbuser, $dbpwd, $options);

        // Prepare INSERT statement with explicit NULL handling
        $sql = "INSERT INTO sensors
                (`id`, `req`, `bat`, `rfu`, `count`, `light`, `temp`, `hum`, `co2`, 
                 `date`, `rssi`, `pkt`, `raw`, `pres`, `rep`) 
                VALUES 
                (:id, :req, :bat, :rfu, :count, :light, :temp, :hum, :co2, 
                 :date, :rssi, :pkt, :raw, :pres, :rep)";

        $stmt = $pdo->prepare($sql);

        // Bind parameters, converting null strings to actual NULL
        $bindings = [
            ':id' => $row['id'] ?? null,
            ':req' => $row['req'] ?? null,
            ':bat' => $row['bat'] ?? 0.0,
            ':rfu' => $row['rfu'] ?? 0.0,
            ':count' => $row['count'] ?? null,
            ':light' => $row['light'] ?? null,
            ':temp' => isset($row['temp']) ? (float)$row['temp'] : null,
            ':hum' => $row['hum'] ?? null,
            ':co2' => $row['co2'] ?? null,
            ':date' => $row['date'] ?? null,
            ':rssi' => $row['rssi'] ?? -125.0,
            ':pkt' => $row['pkt'] ?? null,
            ':raw' => $row['raw'] ?? null,
            ':pres' => $row['pres'] ?? 0.0,
            ':rep' => $row['rep'] ?? null,
        ];

        // Convert empty strings to NULL for proper DB handling
        $bindings = array_map(function ($val) {
            return ($val === '' || $val === 'NULL') ? null : $val;
        }, $bindings);

        // Execute the statement
        $stmt->execute($bindings);

        return true;

    } catch (PDOException $e) {
        error_log("Database error: " . $e->getMessage());
        return false;
    }
}

/*
// =============================================
// EXAMPLE USAGE
// =============================================

// Single row example
$singleRow = [
    'id'    => 12345,
    'req'   => 1,
    'bat'   => 3.7,
    'rfu'   => 0.5,
    'count' => 10,
    'light' => 500.0,
    'temp'  => 22.5,
    'hum'   => 65.0,
    'co2'   => 400.0,
    'date'  => '2026-08-17 14:30:00',
    'rssi'  => -45,
    'pkt'   => 100,
    'raw'   => '{"sensor":"A1"}',
    'pres'  => 1013.25,
    'rep'   => 1
];


// Insert single row
if (insertRow($dbhost, $dbname, $dbuser, $dbpwd, $singleRow)) {
    echo "Row inserted successfully\n";
} else {
    echo "Failed to insert row\n";
}
*/
?>
