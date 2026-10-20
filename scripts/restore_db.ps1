<#
Khôi phục CSDL từ file sao lưu do backup_db.ps1 tạo. GHI ĐÈ dữ liệu hiện tại.
    powershell -ExecutionPolicy Bypass -File scripts\restore_db.ps1 backups\calories_20261019_2300.sql
    powershell -ExecutionPolicy Bypass -File scripts\restore_db.ps1 backups\db_20261019_2300.sqlite3
Nên dừng web server trước khi khôi phục.
#>
param([Parameter(Mandatory = $true)][string]$File)
. "$PSScriptRoot\_common.ps1"
Set-Location $ProjectRoot
if (-not (Test-Path $File)) { throw "Không thấy file $File" }
$db = Get-DbConfig

$answer = Read-Host "Khôi phục sẽ GHI ĐÈ CSDL '$($db.Name)'. Gõ 'yes' để tiếp tục"
if ($answer -ne "yes") { Write-Host "Đã hủy."; exit 0 }

if ($db.Engine -eq "mysql") {
    $cnf = New-MysqlDefaultsFile $db
    try {
        Write-Step "Nạp $File vào $($db.Name)"
        # Dùng cmd để chuyển file vào stdin nguyên byte (PowerShell 5.1 có thể đổi bảng mã khi pipe).
        $mysql = Join-Path $MysqlBinDir "mysql.exe"
        cmd /c "`"$mysql`" --defaults-extra-file=`"$cnf`" --default-character-set=utf8mb4 $($db.Name) < `"$((Resolve-Path $File).Path)`""
        if ($LASTEXITCODE -ne 0) { throw "mysql lỗi khi khôi phục" }
    } finally { Remove-Item $cnf -Force }
} else {
    Copy-Item $File (Join-Path $ProjectRoot $db.Name) -Force
}
Write-Host "Đã khôi phục. Chạy 'python manage.py migrate' nếu bản sao lưu cũ hơn code hiện tại." -ForegroundColor Green
