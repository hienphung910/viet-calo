<#
Sao lưu CSDL (và tùy chọn thư mục ảnh media/) vào thư mục backups/.
    powershell -ExecutionPolicy Bypass -File scripts\backup_db.ps1
    powershell -ExecutionPolicy Bypass -File scripts\backup_db.ps1 -WithMedia

MySQL: dùng mysqldump --single-transaction (sao lưu nhất quán mà không khóa bảng InnoDB).
SQLite: chép file .sqlite3.
#>
param([switch]$WithMedia)
. "$PSScriptRoot\_common.ps1"
Set-Location $ProjectRoot

$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$outDir = Join-Path $ProjectRoot "backups"
New-Item -ItemType Directory -Force $outDir | Out-Null
$db = Get-DbConfig

if ($db.Engine -eq "mysql") {
    $out = Join-Path $outDir "$($db.Name)_$stamp.sql"
    $cnf = New-MysqlDefaultsFile $db
    try {
        Write-Step "mysqldump $($db.Name) -> $out"
        # --defaults-extra-file phải là tham số đầu tiên. --result-file để tránh PowerShell đổi bảng mã.
        & (Join-Path $MysqlBinDir "mysqldump.exe") "--defaults-extra-file=$cnf" --single-transaction --routines `
            --triggers --default-character-set=utf8mb4 --set-gtid-purged=OFF "--result-file=$out" $db.Name
        if ($LASTEXITCODE -ne 0) { throw "mysqldump lỗi" }
    } finally { Remove-Item $cnf -Force }
} else {
    $src = Join-Path $ProjectRoot $db.Name
    $out = Join-Path $outDir "db_$stamp.sqlite3"
    Write-Step "Chép $src -> $out"
    Copy-Item $src $out
}
Write-Host ("Đã lưu: {0} ({1:N1} KB)" -f $out, ((Get-Item $out).Length / 1KB)) -ForegroundColor Green

if ($WithMedia -and (Test-Path media)) {
    $zip = Join-Path $outDir "media_$stamp.zip"
    Write-Step "Nén media/ -> $zip"
    Compress-Archive -Path media\* -DestinationPath $zip -Force
    Write-Host "Đã lưu: $zip" -ForegroundColor Green
}
