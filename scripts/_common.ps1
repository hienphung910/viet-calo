# Hàm dùng chung cho các script (được dot-source: . "$PSScriptRoot\_common.ps1")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$MysqlBinDir = "C:\Program Files\MySQL\MySQL Server 8.0\bin"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

function Get-DbConfig {
    <# Đọc dòng DATABASE_URL đang dùng (không bị comment) trong .env #>
    $envFile = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envFile)) { throw "Chưa có file .env (chạy scripts\setup.ps1 trước)" }
    $line = Get-Content $envFile | Where-Object { $_ -match '^\s*DATABASE_URL=' } | Select-Object -First 1
    if (-not $line) { return @{ Engine = "sqlite"; Name = "db.sqlite3" } }
    $url = ($line -split '=', 2)[1].Trim()
    if ($url -match '^sqlite:///(.+)$') { return @{ Engine = "sqlite"; Name = $Matches[1] } }
    if ($url -match '^mysql://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/([A-Za-z0-9_]+)') {
        return @{
            Engine = "mysql"; User = $Matches[1]; Password = [uri]::UnescapeDataString($Matches[2])
            Host = $Matches[3]; Port = $(if ($Matches[4]) { $Matches[4] } else { "3306" }); Name = $Matches[5]
        }
    }
    throw "Không hiểu DATABASE_URL trong .env: $url"
}

function New-MysqlDefaultsFile($db) {
    <# File cấu hình tạm chứa mật khẩu, để mật khẩu không xuất hiện trên dòng lệnh. Nhớ xóa sau khi dùng. #>
    $tmp = [IO.Path]::GetTempFileName()
    $content = "[client]`nuser=$($db.User)`npassword=$($db.Password)`nhost=$($db.Host)`nport=$($db.Port)`n"
    [IO.File]::WriteAllText($tmp, $content, (New-Object Text.UTF8Encoding $false))
    return $tmp
}
