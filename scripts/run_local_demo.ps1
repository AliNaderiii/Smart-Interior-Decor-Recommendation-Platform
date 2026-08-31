<#
================================================================================
  run_local_demo.ps1 — اجرای نسخهٔ نمایشی روی کامپیوتر خودتان   [Stage 4 / N2]
================================================================================
  یک دستور، بدون دانش فنی. این اسکریپت خودش همه‌چیز را بررسی و آماده می‌کند.

  روش اجرا (در PowerShell، داخل پوشهٔ پروژه):

      .\scripts\run_local_demo.ps1

  اگر ویندوز اجازهٔ اجرا نداد، یک‌بار این را بزنید:

      powershell -ExecutionPolicy Bypass -File .\scripts\run_local_demo.ps1

  گزینه‌ها:
      -Stop      خاموش کردن نسخهٔ نمایشی (اطلاعات باقی می‌ماند)
      -Reset     پاک کردن کامل و شروع از صفر (اطلاعات حذف می‌شود)
      -Logs      دیدن گزارش زندهٔ سرور
      -Check     فقط بررسی پیش‌نیازها، بدون اجرا

  This script exists because two failures blocked the operator on the first
  attempt: (1) Docker Desktop's engine was not running, and (2) .env did not
  exist. Both are now detected and fixed/explained before anything else runs.
================================================================================
#>

[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Reset,
    [switch]$Logs,
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

# --- Persian output must survive Windows PowerShell 5.1 ----------------------
# Two separate problems, both fatal to a Persian-language script:
#   1. FILE encoding: PS 5.1 reads .ps1 as ANSI unless the file carries a UTF-8
#      BOM. This file is saved WITH a BOM (verified by scripts/check_ps1.py) —
#      do not strip it, or every message below becomes mojibake.
#   2. CONSOLE encoding: the host console codepage (often 437/1256) mangles the
#      text on the way OUT. Force UTF-8 for this session.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding           = [System.Text.Encoding]::UTF8
} catch { }

# ---------------------------------------------------------------------------
# نمایش پیام‌ها  (Persian output; ASCII-safe symbols so old consoles cope)
# ---------------------------------------------------------------------------
function Write-Title($text) {
    Write-Host ""
    Write-Host ("=" * 66) -ForegroundColor DarkCyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ("=" * 66) -ForegroundColor DarkCyan
}
function Write-Step($text) { Write-Host "`n>> $text" -ForegroundColor White }
function Write-Ok($text)   { Write-Host "   [OK] $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "   [!]  $text" -ForegroundColor Yellow }
function Write-Fail($text) { Write-Host "   [X]  $text" -ForegroundColor Red }
function Write-Info($text) { Write-Host "        $text" -ForegroundColor Gray }

# راهنمای خطا: همیشه می‌گوید «دقیقاً چه کاری انجام دهید»
function Stop-WithHelp($title, $lines) {
    Write-Host ""
    Write-Host ("-" * 66) -ForegroundColor Red
    Write-Host "  مشکل: $title" -ForegroundColor Red
    Write-Host ("-" * 66) -ForegroundColor Red
    Write-Host ""
    Write-Host "  راه حل:" -ForegroundColor Yellow
    foreach ($l in $lines) { Write-Host "    $l" -ForegroundColor White }
    Write-Host ""
    Write-Host "  بعد از انجام کارهای بالا، دوباره همین دستور را اجرا کنید:" -ForegroundColor Yellow
    Write-Host "    .\scripts\run_local_demo.ps1" -ForegroundColor White
    Write-Host ""
    exit 1
}

# ---------------------------------------------------------------------------
# ۰) محل پروژه — اسکریپت از هرجایی قابل اجراست
# ---------------------------------------------------------------------------
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path (Join-Path $RepoRoot 'docker-compose.yml'))) {
    Stop-WithHelp "پوشهٔ پروژه پیدا نشد" @(
        "این اسکریپت باید از داخل پوشهٔ پروژه اجرا شود.",
        "پوشه‌ای که فایل docker-compose.yml در آن است."
    )
}

$ComposeArgs = @('compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.dev.yml')
$AppUrl      = 'http://localhost:5173'
$ApiUrl      = 'http://localhost:8000'

Write-Title "نسخهٔ نمایشی پلتفرم دکوراسیون هوشمند"

# ---------------------------------------------------------------------------
# ۱) آیا Docker Desktop نصب است؟
# ---------------------------------------------------------------------------
Write-Step "بررسی نصب بودن Docker Desktop"

$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Stop-WithHelp "برنامهٔ Docker Desktop روی این کامپیوتر نصب نیست" @(
        "۱. به این آدرس بروید:  https://www.docker.com/products/docker-desktop/",
        "۲. دکمهٔ Download for Windows را بزنید و فایل را نصب کنید.",
        "۳. بعد از نصب، کامپیوتر را یک‌بار restart کنید.",
        "۴. برنامهٔ Docker Desktop را از منوی Start باز کنید و صبر کنید",
        "   تا در پایین پنجره عبارت 'Engine running' سبز شود."
    )
}
Write-Ok "Docker Desktop نصب است"

# ---------------------------------------------------------------------------
# ۲) آیا موتور Docker روشن است؟  (اولین چیزی که کار را متوقف کرده بود)
# ---------------------------------------------------------------------------
Write-Step "بررسی روشن بودن موتور Docker"

$engineOk = $false
try {
    # NOTE: do NOT use `2>&1` here — on a native command PowerShell 5.1 turns
    # stderr into ErrorRecords, and $ErrorActionPreference='Stop' would abort
    # the script instead of letting us read $LASTEXITCODE and help the user.
    & docker info 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $engineOk = $true }
} catch { $engineOk = $false }

if (-not $engineOk) {
    # شاید تازه باز شده و در حال بالا آمدن است — تا ۹۰ ثانیه صبر می‌کنیم
    Write-Warn "موتور Docker هنوز آماده نیست — تلاش برای اجرای خودکار..."

    $dd = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $dd) {
        if (-not (Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue)) {
            Write-Info "در حال باز کردن Docker Desktop..."
            Start-Process $dd | Out-Null
        }
        Write-Info "منتظر آماده شدن موتور Docker (تا ۹۰ ثانیه)..."
        for ($i = 1; $i -le 30; $i++) {
            Start-Sleep -Seconds 3
            try {
                & docker info 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) { $engineOk = $true; break }
            } catch { }
            if ($i % 5 -eq 0) { Write-Info "  ...هنوز در حال آماده‌سازی ($($i*3) ثانیه)" }
        }
    }
}

if (-not $engineOk) {
    Stop-WithHelp "موتور Docker روشن نیست" @(
        "۱. برنامهٔ Docker Desktop را از منوی Start ویندوز باز کنید.",
        "۲. صبر کنید تا نماد نهنگ در پایین-راست صفحه ثابت شود و در",
        "   پنجرهٔ برنامه عبارت 'Engine running' با رنگ سبز دیده شود.",
        "   (بار اول ممکن است ۲ تا ۳ دقیقه طول بکشد)",
        "",
        "اگر پیام 'WSL 2 is not installed' دیدید:",
        "   PowerShell را با راست‌کلیک و 'Run as administrator' باز کنید و بزنید:",
        "     wsl --install",
        "   سپس کامپیوتر را restart کنید."
    )
}
Write-Ok "موتور Docker روشن و آماده است"

# ---------------------------------------------------------------------------
# ۳) بررسی افزونهٔ compose
# ---------------------------------------------------------------------------
Write-Step "بررسی ابزار Docker Compose"
& docker compose version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Stop-WithHelp "ابزار Docker Compose در دسترس نیست" @(
        "معمولاً یعنی نسخهٔ Docker Desktop قدیمی است.",
        "۱. Docker Desktop را باز کنید.",
        "۲. از منوی چرخ‌دنده (Settings) گزینهٔ Software updates را بزنید.",
        "۳. آخرین نسخه را نصب کنید."
    )
}
Write-Ok "Docker Compose آماده است"

# پاک‌سازی دفاعی (BUG-401): docker-compose هنگام خواندن env_file کامنت‌های
# داخلِ مقدار را حذف نمی‌کند؛ یعنی الگوی `KEY=value # comment` باعث می‌شود
# مقدار متغیر به‌جای value، رشتهٔ `# comment` شود. این تابع کامنت‌های کنارِ
# مقدار را می‌زند تا یک قالبِ خراب هرگز نتواند رشتهٔ کامنت را وارد متغیر کند.
function Convert-EnvTemplateToSafeEnv {
    param(
        [string]$TemplatePath,
        [string]$EnvPath
    )
    $lines   = Get-Content -Path $TemplatePath
    $cleaned = @()
    foreach ($line in $lines) {
        if ($line -match '^[ \t]*[A-Za-z0-9_]+=.*?[ \t]+\x23') {
            $cleaned += ($line -replace '[ \t]+\x23.*$', '')
        } else {
            $cleaned += $line
        }
    }
    # بدون BOM بنویس تا دقیقاً مثل Copy-Item قبلی رفتار کند.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($EnvPath, $cleaned, $utf8NoBom)
}

# ---------------------------------------------------------------------------
# ۴) فایل تنظیمات .env  (دومین چیزی که کار را متوقف کرده بود)
# ---------------------------------------------------------------------------
Write-Step "بررسی فایل تنظیمات (.env)"

$envPath     = Join-Path $RepoRoot '.env'
$envTemplate = Join-Path $RepoRoot '.env.example'

if (-not (Test-Path $envPath)) {
    if (-not (Test-Path $envTemplate)) {
        Stop-WithHelp "فایل نمونهٔ تنظیمات (.env.example) پیدا نشد" @(
            "به نظر می‌رسد فایل‌های پروژه کامل دانلود نشده‌اند.",
            "پوشه را دوباره از GitHub دریافت کنید."
        )
    }
    Convert-EnvTemplateToSafeEnv $envTemplate $envPath
    Write-Ok "فایل .env ساخته شد (از روی .env.example)"
    Write-Info "برای نسخهٔ نمایشی هیچ تغییری لازم نیست — همه‌چیز آفلاین کار می‌کند."
} else {
    Write-Ok "فایل .env از قبل وجود دارد"
}

# ---------------------------------------------------------------------------
# ۵) بررسی آزاد بودن پورت‌ها
# ---------------------------------------------------------------------------
Write-Step "بررسی آزاد بودن پورت‌های مورد نیاز"
$busy = @()
if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    foreach ($p in 5173, 8000, 5432, 6379) {
        try {
            $inUse = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
            if ($inUse) { $busy += $p }
        } catch { }
    }
} else {
    Write-Info "بررسی پورت‌ها روی این نسخهٔ ویندوز ممکن نیست — از این مرحله می‌گذریم."
}
if ($busy.Count -gt 0) {
    Write-Warn ("این پورت‌ها الان مشغول‌اند: " + ($busy -join ', '))
    Write-Info "اگر نسخهٔ نمایشی قبلاً روشن است، مشکلی نیست و ادامه می‌دهیم."
    Write-Info "در غیر این صورت برنامه‌ای که از این پورت‌ها استفاده می‌کند را ببندید."
} else {
    Write-Ok "همهٔ پورت‌ها آزادند"
}

if ($Check) {
    Write-Host ""
    Write-Ok "بررسی پیش‌نیازها کامل شد — همه‌چیز آماده است."
    Write-Info "برای اجرا:  .\scripts\run_local_demo.ps1"
    Write-Host ""
    exit 0
}

# ---------------------------------------------------------------------------
# حالت‌های خاص: خاموش کردن / پاک کردن / گزارش
# ---------------------------------------------------------------------------
if ($Stop) {
    Write-Step "در حال خاموش کردن نسخهٔ نمایشی"
    & docker @ComposeArgs stop
    Write-Ok "خاموش شد. برای روشن کردن دوباره:  .\scripts\run_local_demo.ps1"
    exit 0
}

if ($Reset) {
    Write-Step "پاک کردن کامل و شروع از صفر"
    Write-Warn "تمام اطلاعات نسخهٔ نمایشی (کاربران، پروژه‌ها) حذف می‌شود."
    $answer = Read-Host "برای تایید حرف  y  را بزنید و Enter کنید"
    if ($answer -ne 'y') { Write-Info "لغو شد."; exit 0 }
    & docker @ComposeArgs down -v
    Write-Ok "پاک شد. حالا دوباره اجرا کنید:  .\scripts\run_local_demo.ps1"
    exit 0
}

if ($Logs) {
    Write-Step "گزارش زندهٔ سرور (برای خروج Ctrl+C بزنید)"
    & docker @ComposeArgs logs -f backend
    exit 0
}

# ---------------------------------------------------------------------------
# ۶) ساخت و اجرا
# ---------------------------------------------------------------------------
Write-Step "ساخت و اجرای نسخهٔ نمایشی"
Write-Info "بار اول حدود ۱۰ تا ۱۵ دقیقه طول می‌کشد (دانلود و ساخت)."
Write-Info "دفعات بعد فقط چند ثانیه است. لطفاً پنجره را نبندید."
Write-Host ""

& docker @ComposeArgs up -d --build
if ($LASTEXITCODE -ne 0) {
    Stop-WithHelp "ساخت نسخهٔ نمایشی با خطا متوقف شد" @(
        "معمول‌ترین دلیل‌ها:",
        "  - اینترنت قطع شده یا خیلی کند است (باید فایل‌ها دانلود شوند).",
        "  - فضای خالی دیسک کم است (حداقل ۱۰ گیگابایت لازم است).",
        "  - Docker Desktop وسط کار بسته شده است.",
        "",
        "برای دیدن جزئیات خطا این را بزنید:",
        "  .\scripts\run_local_demo.ps1 -Logs"
    )
}
Write-Ok "سرویس‌ها اجرا شدند"

# ---------------------------------------------------------------------------
# ۷) صبر تا آماده شدن سرور
# ---------------------------------------------------------------------------
Write-Step "منتظر آماده شدن سرور"
Write-Info "این مرحله تا ۵ دقیقه ممکن است طول بکشد (ساخت پایگاه داده و داده‌های نمونه)."

$ready = $false
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 5
    try {
        $r = Invoke-WebRequest -Uri "$ApiUrl/api/v1/health/ready" `
             -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    if ($i % 6 -eq 0) { Write-Info "  ...در حال آماده‌سازی ($($i*5) ثانیه)" }
}

if (-not $ready) {
    Write-Fail "سرور در زمان انتظار آماده نشد"
    Write-Host ""
    Write-Info "آخرین خطوط گزارش سرور:"
    & docker @ComposeArgs logs --tail 25 backend

    # گزارش کامل را خودکار در یک فایل ذخیره می‌کنیم تا کاربر مجبور نباشد
    # دستور دیگری اجرا کند و متن را از پنجره کپی کند.
    $LogFile = Join-Path $RepoRoot "demo-logs.txt"
    try {
        $allLogs = & docker @ComposeArgs logs --tail 400 2>$null
        Set-Content -Path $LogFile -Value $allLogs -Encoding UTF8
        Write-Host ""
        Write-Ok "گزارش کامل در این فایل ذخیره شد:"
        Write-Host "    $LogFile" -ForegroundColor White
        Write-Info "لطفاً همین فایل را برای تیم فنی بفرستید."
    } catch {
        Write-Warn "ذخیرهٔ خودکار گزارش ممکن نشد؛ لطفاً دستور -Logs را اجرا کنید."
    }

    Stop-WithHelp "سرور بالا نیامد" @(
        "۱. چند دقیقه صبر کنید و دوباره اجرا کنید — گاهی بار اول کند است.",
        "۲. اگر خطای رمز پایگاه داده (password authentication failed) دیدید،",
        "   یعنی اطلاعات قدیمی روی کامپیوتر شما مانده است. از صفر شروع کنید:",
        "     .\scripts\run_local_demo.ps1 -Reset",
        "     .\scripts\run_local_demo.ps1",
        "۳. اگر مشکل ادامه داشت، فایل demo-logs.txt را برای تیم فنی بفرستید."
    )
}
Write-Ok "سرور آماده است"

# ---------------------------------------------------------------------------
# ۸) بررسی بارگذاری محصولات
# ---------------------------------------------------------------------------
Write-Step "بررسی داده‌های نمونه"
# اجرای exec می‌تواند بلافاصله بعد از آماده‌شدن سرور یک لحظه خطا بدهد؛ چند بار
# با فاصلهٔ کوتاه تلاش می‌کنیم تا هشدار کاذب نشان داده نشود و «خطای واقعی» از
# «کاتالوگ واقعاً خالی» قابل تشخیص بماند. بررسی همچنان انجام می‌شود (ضعیف نشده).
$count = $null
for ($i = 1; $i -le 5; $i++) {
    try {
        $raw = (& docker @ComposeArgs exec -T postgres `
                psql -U decor -d decor -tAc 'select count(*) from products' 2>$null)
        if ($null -ne $raw) {
            $text = ([string]($raw -join '')).Trim()
            if ($text -match '^\d+$') { $count = [int]$text; break }
        }
    } catch { }
    if ($i -lt 5) { Start-Sleep -Seconds 3 }
}
if ($null -ne $count -and $count -ge 1) {
    Write-Ok "$count محصول در کاتالوگ بارگذاری شد"
} elseif ($null -ne $count) {
    Write-Warn "کاتالوگ خالی است — ممکن است چند لحظه دیگر پر شود."
} else {
    Write-Warn "شمارش محصولات ممکن نشد (مهم نیست، برنامه کار می‌کند)."
}

# ---------------------------------------------------------------------------
# ۹) آماده! نمایش اطلاعات ورود
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host ("=" * 66) -ForegroundColor Green
Write-Host "  نسخهٔ نمایشی آماده است!" -ForegroundColor Green
Write-Host ("=" * 66) -ForegroundColor Green
Write-Host ""
Write-Host "  آدرس برنامه:" -ForegroundColor Cyan
Write-Host "    $AppUrl" -ForegroundColor White
Write-Host ""
Write-Host "  حساب‌های آمادهٔ ورود:" -ForegroundColor Cyan
Write-Host ""
Write-Host "    مشتری (خانه‌دار)" -ForegroundColor Yellow
Write-Host "      ایمیل : demo@smartdecor.dev"
Write-Host "      رمز   : Demo1234!"
Write-Host ""
Write-Host "    طراح" -ForegroundColor Yellow
Write-Host "      ایمیل : designer@smartdecor.dev"
Write-Host "      رمز   : Design123!"
Write-Host ""
Write-Host "    مدیر سیستم" -ForegroundColor Yellow
Write-Host "      ایمیل : admin@smartdecor.dev"
Write-Host "      رمز   : Admin123!"
Write-Host ""
Write-Host "  توجه: این رمزها فقط برای نسخهٔ نمایشی روی کامپیوتر شماست." -ForegroundColor DarkYellow
Write-Host "        روی نسخهٔ عمومی هرگز ساخته نمی‌شوند." -ForegroundColor DarkYellow
Write-Host ""
Write-Host "  هر حساب فقط به بخش‌های خودش دسترسی دارد:" -ForegroundColor DarkYellow
Write-Host "        اگر پیام «دسترسی کافی نیست» یا خطای ۴۰۳ دیدید، ایراد نیست —" -ForegroundColor DarkYellow
Write-Host "        یعنی آن صفحه برای نقش دیگری است. مثلاً مدیریت کاتالوگ فقط با" -ForegroundColor DarkYellow
Write-Host "        حساب «مدیر سیستم» باز می‌شود، نه با حساب مشتری." -ForegroundColor DarkYellow
Write-Host ""
Write-Host ("-" * 66) -ForegroundColor DarkGray
Write-Host "  دستورهای مفید:" -ForegroundColor Cyan
Write-Host "    خاموش کردن      :  .\scripts\run_local_demo.ps1 -Stop"
Write-Host "    روشن کردن دوباره:  .\scripts\run_local_demo.ps1"
Write-Host "    شروع از صفر     :  .\scripts\run_local_demo.ps1 -Reset"
Write-Host "    دیدن گزارش سرور :  .\scripts\run_local_demo.ps1 -Logs"
Write-Host ("-" * 66) -ForegroundColor DarkGray
Write-Host ""

# باز کردن خودکار مرورگر
try {
    Start-Process $AppUrl | Out-Null
    Write-Info "مرورگر به‌صورت خودکار باز شد."
} catch {
    Write-Info "لطفاً آدرس بالا را در مرورگر خودتان باز کنید."
}
Write-Host ""
