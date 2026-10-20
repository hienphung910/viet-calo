<#
Tạo database + tài khoản MySQL cho dự án, theo thông tin trong dòng DATABASE_URL=mysql://... của file .env
(dòng đó có thể đang bị comment bằng '#').

Cách chạy: mở PowerShell bằng "Run as Administrator" (cần quyền này để bật service MySQL), rồi:
    cd E:\Major\Project\AI\Calories
    powershell -ExecutionPolicy Bypass -File scripts\setup_mysql.ps1

Script sẽ hỏi mật khẩu root của MySQL (mật khẩu đặt lúc cài MySQL). Chạy lại nhiều lần không sao.
Lưu ý: mật khẩu trong .env được đặt vào câu SQL trong dấu nháy đơn -> không dùng ký tự ' trong mật khẩu
(mật khẩu do setup.ps1 sinh ra chỉ gồm 0-9a-f nên luôn an toàn).
#>
param(
    [string]$MysqlBin = "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
    [string]$Service = "MySQL80"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# 1. Bật service MySQL
$svc = Get-Service $Service
if ($svc.Status -ne "Running") {
    Write-Host "Bật service $Service..."
    Start-Service $Service
}
Write-Host "Service $Service đang chạy."
# (Tùy chọn) để MySQL tự chạy khi bật máy:  Set-Service $Service -StartupType Automatic

# 2. Đọc thông tin kết nối từ .env
$line = Get-Content (Join-Path $root ".env") | Where-Object { $_ -match '^\s*#?\s*DATABASE_URL=mysql://' } | Select-Object -First 1
if (-not $line) { throw "Không thấy dòng DATABASE_URL=mysql://user:pass@host:port/db trong .env" }
if ($line -notmatch 'mysql://([^:]+):([^@]+)@[^/]+/([A-Za-z0-9_]+)') { throw "DATABASE_URL không đúng dạng: mysql://user:pass@host:port/db" }
$user = $Matches[1]
$pass = [uri]::UnescapeDataString($Matches[2])
$db = $Matches[3]

# 3. Tạo database (utf8mb4 cho tiếng Việt), tài khoản, cấp quyền (kể cả database test_<db> Django tạo khi chạy test)
$sql = @"
CREATE DATABASE IF NOT EXISTS ``$db`` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$user'@'localhost' IDENTIFIED BY '$pass';
ALTER USER '$user'@'localhost' IDENTIFIED BY '$pass';
GRANT ALL PRIVILEGES ON ``$db``.* TO '$user'@'localhost';
GRANT ALL PRIVILEGES ON ``test_$db``.* TO '$user'@'localhost';
FLUSH PRIVILEGES;
"@
Write-Host "Nhập mật khẩu root của MySQL:"
& $MysqlBin -u root -p -e $sql
if ($LASTEXITCODE -ne 0) { throw "Lệnh mysql bị lỗi (sai mật khẩu root?)" }
Write-Host "Xong: database '$db', tài khoản '$user'@localhost."
Write-Host "Tiếp theo: trong .env, bỏ dấu # ở dòng DATABASE_URL=mysql://... và thêm # vào dòng sqlite, rồi chạy: python manage.py migrate"
