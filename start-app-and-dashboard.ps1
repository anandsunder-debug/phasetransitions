param(
    [switch]$SkipInstall,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Ensure-Command {
    param(
        [string]$Name,
        [string]$InstallHint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required but not found. $InstallHint"
    }
}

function Ensure-FileContainsLine {
    param(
        [string]$Path,
        [string]$Line
    )

    if (-not (Test-Path $Path)) {
        Set-Content -Path $Path -Value $Line -Encoding UTF8
        return
    }

    $content = Get-Content -Path $Path -Raw
    if ($content -notmatch [Regex]::Escape($Line)) {
        if ($content.Trim().Length -eq 0) {
            Set-Content -Path $Path -Value $Line -Encoding UTF8
        } else {
            Add-Content -Path $Path -Value "`n$Line" -Encoding UTF8
        }
    }
}

function Start-ServiceWindow {
    param(
        [string]$Title,
        [string]$WorkingDir,
        [string]$Command
    )

    $fullCommand = "$host.ui.RawUI.WindowTitle = '$Title'; Set-Location '$WorkingDir'; $Command"
    Start-Process powershell -ArgumentList '-NoExit', '-Command', $fullCommand | Out-Null
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$backendEnvFile = Join-Path $backendDir '.env'
$frontendEnvFile = Join-Path $frontendDir '.env'
$venvPython = Join-Path $backendDir 'venv\Scripts\python.exe'

Write-Step 'Checking prerequisites'
Ensure-Command -Name 'python' -InstallHint 'Install Python 3.11+ and add it to PATH.'
Ensure-Command -Name 'node' -InstallHint 'Install Node.js 18+ and add it to PATH.'

$frontendRunner = $null
$frontendInstall = $null
if (Get-Command yarn -ErrorAction SilentlyContinue) {
    $frontendRunner = 'yarn start'
    $frontendInstall = 'yarn install'
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    $frontendRunner = 'npm start'
    $frontendInstall = 'npm install'
} else {
    throw 'Neither yarn nor npm was found. Install Yarn 1.22+ (recommended) or npm.'
}

Write-Step 'Preparing backend environment'
if (-not (Test-Path $venvPython)) {
    Push-Location $backendDir
    try {
        python -m venv venv
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path $backendEnvFile)) {
    $jwtSecret = [guid]::NewGuid().ToString('N')
    @(
        'MONGO_URL=mongodb://localhost:27017'
        'DB_NAME=freshcart'
        "JWT_SECRET=$jwtSecret"
        'INFLUX_URL=http://localhost:8086'
        'INFLUX_TOKEN='
        'INFLUX_ORG=freshcart'
        'INFLUX_BUCKET=metrics'
    ) | Set-Content -Path $backendEnvFile -Encoding UTF8
}

if (-not $SkipInstall) {
    $needsPipInstall = -not (Test-Path (Join-Path $backendDir 'venv\Scripts\uvicorn.exe'))
    if ($needsPipInstall) {
        Push-Location $backendDir
        try {
            & $venvPython -m pip install --upgrade pip
            & $venvPython -m pip install -r requirements.txt
        } finally {
            Pop-Location
        }
    }
}

Write-Step 'Preparing frontend environment'
Ensure-FileContainsLine -Path $frontendEnvFile -Line 'PORT=3001'
Ensure-FileContainsLine -Path $frontendEnvFile -Line 'REACT_APP_BACKEND_URL=http://localhost:8001'

if (-not $SkipInstall) {
    if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
        Push-Location $frontendDir
        try {
            Invoke-Expression $frontendInstall
        } finally {
            Pop-Location
        }
    }
}

Write-Step 'Checking MongoDB availability'
$mongoService = Get-Service -Name 'MongoDB' -ErrorAction SilentlyContinue
if ($mongoService -and $mongoService.Status -ne 'Running') {
    try {
        Start-Service -Name 'MongoDB'
        Write-Host 'Started MongoDB service.' -ForegroundColor Green
    } catch {
        Write-Warning 'MongoDB service exists but could not be started automatically.'
    }
}

$mongoReachable = Test-NetConnection -ComputerName 'localhost' -Port 27017 -InformationLevel Quiet
if (-not $mongoReachable) {
    Write-Warning 'MongoDB is not reachable on localhost:27017. Backend startup may fail until MongoDB is running.'
}

Write-Step 'Launching observability service (port 8002)'
Start-ServiceWindow -Title 'FreshCart OBS (8002)' -WorkingDir $backendDir -Command "& '$venvPython' -m uvicorn obs_server:app --host 0.0.0.0 --port 8002 --reload"

Write-Step 'Launching main backend service (port 8001)'
Start-ServiceWindow -Title 'FreshCart API (8001)' -WorkingDir $backendDir -Command "& '$venvPython' -m uvicorn server:app --host 0.0.0.0 --port 8001 --reload"

Write-Step 'Launching frontend (port 3001)'
$env:PORT = '3001'
Start-ServiceWindow -Title 'FreshCart Frontend (3001)' -WorkingDir $frontendDir -Command "(`$env:PORT = '3001'); $frontendRunner"

if (-not $NoBrowser) {
    Write-Step 'Opening app and operations dashboard in browser'
    Start-Process 'http://localhost:3001' | Out-Null
    Start-Process 'http://localhost:3001/dashboard' | Out-Null
}

Write-Host "`nStartup triggered successfully." -ForegroundColor Green
Write-Host 'Main app:          http://localhost:3001'
Write-Host 'Ops dashboard:     http://localhost:3001/dashboard'
Write-Host 'Backend API:       http://localhost:8001'
Write-Host 'Observability API: http://localhost:8002'
Write-Host "`nNote: /dashboard requires authentication; use admin credentials from your seeded data." -ForegroundColor Yellow
