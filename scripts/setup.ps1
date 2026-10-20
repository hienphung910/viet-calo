<#
Cài đặt dự án bằng một lệnh (không cần quyền Administrator):
    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1              # CSDL MySQL (mặc định)
    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Db sqlite   # thử nhanh bằng SQLite

Các bước: tạo .venv -> cài thư viện (PyTorch bản CUDA nếu máy có GPU NVIDIA) -> tạo .env
-> kiểm tra kết nối CSDL -> migrate -> nạp bảng dinh dưỡng -> collectstatic -> (tùy chọn) tạo tài khoản admin.
Chạy lại nhiều lần không sao: bước nào đã xong sẽ được bỏ qua.
#>
param(
    [ValidateSet("mysql", "sqlite")][string]$Db = "mysql",
    [switch]$SkipTorch
)
. "$PSScriptRoot\_common.ps1"
Set-Location $ProjectRoot

Write-Step "Kiểm tra Python"
$ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$ver -lt [version]"3.11") { throw "Cần Python >= 3.11 (đang có $ver)" }
Write-Host "Python $ver"

if (-not (Test-Path $Python)) {
    Write-Step "Tạo môi trường ảo .venv"
    & python -m venv .venv
}
& $Python -m pip install --upgrade pip -q

Write-Step "Cài thư viện web (requirements.txt)"
& $Python -m pip install -r requirements.txt -q

if (-not $SkipTorch) {
    $hasTorch = (& $Python -c "import importlib.util; print(importlib.util.find_spec('torch') is not None)") -eq "True"
    if (-not $hasTorch) {
        $gpu = Get-Command nvidia-smi -ErrorAction SilentlyContinue
        $index = if ($gpu) { "https://download.pytorch.org/whl/cu128" } else { "https://download.pytorch.org/whl/cpu" }
        Write-Step "Cài PyTorch ($(if ($gpu) {'CUDA, có GPU NVIDIA'} else {'CPU'})) - khoảng 2-3 GB, có thể mất vài phút"
        & $Python -m pip install torch torchvision --index-url $index -q
    }
    Write-Step "Cài thư viện ML (requirements-ml.txt)"
    & $Python -m pip install -r requirements-ml.txt -q
    & $Python -c "import torch; print('PyTorch', torch.__version__, '| CUDA:', torch.cuda.is_available())"
}

if (-not (Test-Path .env)) {
    Write-Step "Tạo file .env"
    $secret = & $Python -c "import secrets; print(secrets.token_urlsafe(48))"
    $dbPass = & $Python -c "import secrets; print(secrets.token_hex(12))"
    $text = [IO.File]::ReadAllText((Join-Path $ProjectRoot ".env.example"), [Text.Encoding]::UTF8)
    $text = $text -replace '(?m)^SECRET_KEY=.*$', "SECRET_KEY=$secret"
    $text = $text -replace '(?m)^DATABASE_URL=mysql://calories:[^@]+@', "DATABASE_URL=mysql://calories:$dbPass@"
    if ($Db -eq "sqlite") {
        $text = $text -replace '(?m)^DATABASE_URL=mysql', '# DATABASE_URL=mysql'
        $text = $text -replace '(?m)^# DATABASE_URL=sqlite', 'DATABASE_URL=sqlite'
    }
    [IO.File]::WriteAllText((Join-Path $ProjectRoot ".env"), $text, (New-Object Text.UTF8Encoding $false))
    Write-Host ".env đã tạo (SECRET_KEY và mật khẩu MySQL được sinh ngẫu nhiên)."
}

Write-Step "Kiểm tra kết nối CSDL"
$dbCfg = Get-DbConfig
& $Python manage.py shell -v 0 -c "from django.db import connection; connection.ensure_connection(); print('OK:', connection.vendor, connection.settings_dict['NAME'])"
if ($LASTEXITCODE -ne 0) {
    if ($dbCfg.Engine -eq "mysql") {
        Write-Host "`nChưa kết nối được MySQL. Mở PowerShell bằng 'Run as Administrator' và chạy:" -ForegroundColor Yellow
        Write-Host "    powershell -ExecutionPolicy Bypass -File scripts\setup_mysql.ps1" -ForegroundColor Yellow
        Write-Host "rồi chạy lại scripts\setup.ps1" -ForegroundColor Yellow
    }
    exit 1
}

Write-Step "Tạo/cập nhật bảng (migrate)"
& $Python manage.py migrate
Write-Step "Nạp bảng dinh dưỡng từ data/nutrition.csv"
& $Python manage.py seed_foods
Write-Step "Gom file tĩnh (collectstatic)"
& $Python manage.py collectstatic --noinput -v 0

$hasAdmin = & $Python manage.py shell -v 0 -c "from apps.accounts.models import User; print(User.objects.filter(is_superuser=True).exists())"
if ($hasAdmin -ne "True") {
    Write-Step "Tạo tài khoản admin (email + mật khẩu)"
    & $Python manage.py createsuperuser
}

Write-Host "`nXong! Chạy web:" -ForegroundColor Green
Write-Host "    .venv\Scripts\python.exe manage.py runserver        (phát triển, DEBUG=True)"
Write-Host "    powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1   (demo, DEBUG=False)"
