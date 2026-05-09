param(
    [string]$InstallDir = "C:\ha-input-bridge",
    [int]$Port = 8765,
    [string]$BindHost = "",
    [string]$AllowedClientIp = ""
)

$ErrorActionPreference = "Stop"

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)

    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host ""
        Write-Host "This installer must be run as Administrator." -ForegroundColor Red
        Write-Host "Open PowerShell as Administrator and run this script again."
        exit 1
    }
}

function New-BridgeToken {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToBase64String($bytes)
}

function Get-DefaultIPv4 {
    $addresses = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object {
            $_.IPAddress -ne "127.0.0.1" `
            -and $_.IPAddress -notlike "169.254.*" `
            -and $_.PrefixOrigin -ne "WellKnown"
        } |
        Sort-Object InterfaceMetric |
        Select-Object -ExpandProperty IPAddress

    return $addresses
}

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            & py -3 --version *> $null
            return @{ Mode = "py"; Path = "py" }
        } catch {}
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        try {
            & $python.Source --version *> $null
            return @{ Mode = "python"; Path = $python.Source }
        } catch {}
    }

    return $null
}

Assert-Admin

$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceBridge = Join-Path $SourceDir "ha_input_bridge.py"
$SourceRequirements = Join-Path $SourceDir "requirements.txt"

if (-not (Test-Path $SourceBridge)) {
    throw "Missing source file: $SourceBridge"
}

if (-not (Test-Path $SourceRequirements)) {
    throw "Missing source file: $SourceRequirements"
}

if (-not $BindHost) {
    Write-Host ""
    Write-Host "Available local IPv4 addresses:" -ForegroundColor Cyan

    $ips = @(Get-DefaultIPv4)

    for ($i = 0; $i -lt $ips.Count; $i++) {
        Write-Host "[$($i + 1)] $($ips[$i])"
    }

    if ($ips.Count -gt 0) {
        $defaultBindHost = $ips[0]
        $inputBindHost = Read-Host "Windows PC IP to bind to [$defaultBindHost]"
        if ($inputBindHost) {
            $BindHost = $inputBindHost.Trim()
        } else {
            $BindHost = $defaultBindHost
        }
    } else {
        $BindHost = Read-Host "Windows PC IP to bind to"
    }
}

if (-not $AllowedClientIp) {
    $AllowedClientIp = Read-Host "Home Assistant IP allowed to connect"
}

if (-not $AllowedClientIp) {
    throw "Home Assistant IP is required"
}

$Token = New-BridgeToken

Write-Host ""
Write-Host "Installing HA Input Bridge..." -ForegroundColor Cyan
Write-Host "Install dir: $InstallDir"
Write-Host "Bind host:   $BindHost"
Write-Host "Port:        $Port"
Write-Host "Allowed IP:  $AllowedClientIp"

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

Copy-Item $SourceBridge (Join-Path $InstallDir "ha_input_bridge.py") -Force
Copy-Item $SourceRequirements (Join-Path $InstallDir "requirements.txt") -Force

$Python = Find-Python
if (-not $Python) {
    throw "Python was not found. Install Python 3 first, then rerun this installer."
}

$VenvDir = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host ""
    Write-Host "Creating Python virtual environment..." -ForegroundColor Cyan

    if ($Python.Mode -eq "py") {
        & py -3 -m venv $VenvDir
    } else {
        & $Python.Path -m venv $VenvDir
    }
}

Write-Host ""
Write-Host "Installing Python requirements..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $InstallDir "requirements.txt")

$StartScript = Join-Path $InstallDir "start_ha_input_bridge.ps1"

@"
`$ErrorActionPreference = "Stop"

`$env:HA_INPUT_TOKEN = "$Token"
`$env:HA_INPUT_BIND_HOST = "$BindHost"
`$env:HA_INPUT_PORT = "$Port"
`$env:HA_ALLOWED_CLIENT_IP = "$AllowedClientIp"

Set-Location "$InstallDir"

& "$VenvPython" "$InstallDir\ha_input_bridge.py" *> "$InstallDir\task_runtime.log"
"@ | Set-Content -Path $StartScript -Encoding UTF8

$TaskName = "HA Input Bridge"

Write-Host ""
Write-Host "Creating Scheduled Task..." -ForegroundColor Cyan

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

$RuleName = "HA Input Bridge - Home Assistant only"

Write-Host ""
Write-Host "Creating Windows Firewall rule..." -ForegroundColor Cyan

Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

New-NetFirewallRule `
    -DisplayName $RuleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalAddress $BindHost `
    -LocalPort $Port `
    -RemoteAddress $AllowedClientIp `
    -Profile Any | Out-Null

Write-Host ""
Write-Host "Starting HA Input Bridge..." -ForegroundColor Cyan

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName $TaskName

Start-Sleep -Seconds 3

$Task = Get-ScheduledTask -TaskName $TaskName
$Listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -eq $BindHost }

Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
Write-Host ""
Write-Host "Scheduled Task:"
Write-Host "  Name:  $TaskName"
Write-Host "  State: $($Task.State)"
Write-Host ""

if ($Listen) {
    Write-Host "Bridge is listening:"
    Write-Host "  http://${BindHost}:${Port}"
} else {
    Write-Host "Bridge is not listening yet. Check:" -ForegroundColor Yellow
    Write-Host "  $InstallDir\task_runtime.log"
    Write-Host "  $InstallDir\ha_input_bridge.log"
}

Write-Host ""
Write-Host "Use these values in Home Assistant:" -ForegroundColor Cyan
Write-Host "  Host:  $BindHost"
Write-Host "  Port:  $Port"
Write-Host "  Token: $Token"
Write-Host ""
Write-Host "Keep the token private." -ForegroundColor Yellow
