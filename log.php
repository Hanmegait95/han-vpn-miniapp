<?php
// Телеметрия прототипа мини-аппы. Пишет строки в файл вне веб-корня.
$raw = file_get_contents('php://input');
if ($raw !== false && strlen($raw) > 0 && strlen($raw) < 4000) {
    $line = date('c') . ' ' . str_replace(["\n", "\r"], ' ', $raw) . "\n";
    @file_put_contents(__DIR__ . '/../../miniapp.log', $line, FILE_APPEND | LOCK_EX);
}
http_response_code(204);
