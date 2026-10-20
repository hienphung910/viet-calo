<#
Chạy web ở chế độ demo (DEBUG=False) bằng waitress, web server viết bằng Python, chạy được trên Windows.
    powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1          # chỉ máy này: http://127.0.0.1:8000
    powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Lan     # cho điện thoại cùng mạng Wi-Fi truy cập

Khác runserver: không tự reload code, không hiện trang lỗi chi tiết (an toàn khi demo),
file tĩnh do whitenoise phục vụ, ảnh do view có kiểm tra quyền phục vụ.
#>
param(
    [int]$Port = 8000,
    [int]$Threads = 8,
    [switch]$Lan
)
. "$PSScriptRoot\_common.ps1"
Set-Location $ProjectRoot

# Biến môi trường được ưu tiên hơn giá trị trong .env.
$env:DEBUG = "False"
$listenHost = "127.0.0.1"
$hosts = @("localhost", "127.0.0.1")
if ($Lan) {
    $listenHost = "0.0.0.0"
    $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
    if ($ip) { $hosts += $ip }
    Write-Host "Điện thoại cùng mạng mở: http://${ip}:$Port  (Windows Firewall có thể hỏi cho phép Python)" -ForegroundColor Yellow
}
$env:ALLOWED_HOSTS = $hosts -join ","

Write-Step "Gom file tĩnh"
& $Python manage.py collectstatic --noinput -v 0

Write-Step "Chạy waitress tại http://${listenHost}:$Port  (Ctrl+C để dừng)"
& (Join-Path $ProjectRoot ".venv\Scripts\waitress-serve.exe") --listen="${listenHost}:$Port" --threads=$Threads config.wsgi:application
