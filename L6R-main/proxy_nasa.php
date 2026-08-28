<?php
// Proxy em PHP para buscar o CSV da NASA sem bloqueios de CORS.
// Muito mais leve e confiável para hospedagem compartilhada HostGator do que o Python.

header("Access-Control-Allow-Origin: *");
header("Content-Type: text/csv");

$url = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_South_America_7d.csv";

$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, $url);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, 1);
curl_setopt($ch, CURLOPT_TIMEOUT, 60);
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false); // Evita problemas de certificado na Hostgator

$data = curl_exec($ch);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$error = curl_error($ch);
curl_close($ch);

if ($http_code != 200 || !$data) {
    http_response_code(502);
    echo "Error fetching NASA CSV. HTTP Code: " . $http_code . " Error: " . $error;
} else {
    echo $data;
}
?>
