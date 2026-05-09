param(
    [string]$InstallDir = "C:\ha-input-bridge"
)

$ErrorActionPreference = "Stop"

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)

    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host ""
        Write-Host "This uninstaller must be run as Administrator." -ForegroundColor Red
        Write-Host "Open PowerShell as Administrator and run this script again."
        exit 1
    }
}

Assert-Admin

$TaskName = "HA Input Bridge"
$RuleName = "HA Input Bridge - Home Assistant only"

Write-Host ""
Write-Host "Uninstalling HA Input Bridge..." -ForegroundColor Cyan

Write-Host "Stopping scheduled task..."
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

Write-Host "Removing scheduled task..."
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Write-Host "Removing firewall rule..."
Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

Write-Host "Stopping leftover Python bridge processes from install directory..."

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -like "*$InstallDir*" -and
        $_.CommandLine -like "*ha_input_bridge.py*"
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

if (Test-Path $InstallDir) {
    Write-Host "Removing install directory: $InstallDir"
    Remove-Item -Path $InstallDir -Recurse -Force
}

Write-Host ""
Write-Host "HA Input Bridge has been uninstalled." -ForegroundColor Green
