$ErrorActionPreference = "Stop"

$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WindowsDir = Split-Path -Parent $InstallerDir
$RepoRoot = Split-Path -Parent $WindowsDir

$VenvDir = Join-Path $InstallerDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
$PyInstallerExe = Join-Path $VenvDir "Scripts\pyinstaller.exe"

$AgentSpecFile = Join-Path $InstallerDir "ha-input-bridge-agent.spec"
$TraySpecFile = Join-Path $InstallerDir "ha-input-bridge-tray.spec"
$InnoScript = Join-Path $InstallerDir "HAInputBridgeSetup.iss"

$AgentSourceFile = Join-Path $WindowsDir "ha_input_bridge.py"
$TraySourceFile = Join-Path $WindowsDir "ha_input_bridge_tray.py"
$RecorderSourceFile = Join-Path $WindowsDir "ha_input_bridge_recorder.py"

$AgentDistExe = Join-Path $InstallerDir "dist\ha-input-bridge-agent.exe"
$TrayDistExe = Join-Path $InstallerDir "dist\ha-input-bridge-tray.exe"
$SetupExe = Join-Path $InstallerDir "dist\HA-Input-Bridge-Setup.exe"

Write-Host ""
Write-Host "HA Input Bridge Windows installer build"
Write-Host "Repo root:      $RepoRoot"
Write-Host "Windows dir:    $WindowsDir"
Write-Host "Installer dir:  $InstallerDir"
Write-Host ""

if (-not (Test-Path $AgentSourceFile)) {
  throw "Missing windows\ha_input_bridge.py"
}

if (-not (Test-Path $TraySourceFile)) {
  throw "Missing windows\ha_input_bridge_tray.py"
}

if (-not (Test-Path $RecorderSourceFile)) {
  throw "Missing windows\ha_input_bridge_recorder.py"
}

if (-not (Test-Path $AgentSpecFile)) {
  throw "Missing $AgentSpecFile"
}

if (-not (Test-Path $TraySpecFile)) {
  throw "Missing $TraySpecFile"
}

if (-not (Test-Path $InnoScript)) {
  throw "Missing $InnoScript"
}

$PythonCommand = Get-Command py -ErrorAction SilentlyContinue

if ($PythonCommand) {
  Write-Host "Creating build virtual environment using py launcher..."
  & py -3 -m venv $VenvDir
}
else {
  $PythonCommand = Get-Command python -ErrorAction SilentlyContinue

  if (-not $PythonCommand) {
    throw "Python was not found. Install Python 3 first."
  }

  Write-Host "Creating build virtual environment using python..."
  & python -m venv $VenvDir
}

if (-not (Test-Path $PythonExe)) {
  throw "Virtual environment Python was not created: $PythonExe"
}

Write-Host "Upgrading pip..."
& $PythonExe -m pip install --upgrade pip

Write-Host "Installing build dependencies..."
& $PipExe install `
  "pyinstaller>=6,<7" `
  "flask>=3,<4" `
  "waitress>=3,<4" `
  "pyautogui>=0.9.54,<1" `
  "pystray>=0.19,<1" `
  "pillow>=10,<12" `
  "pynput>=1.7.7,<2" `
  "six>=1.16,<2"

Write-Host ""
Write-Host "Installed package versions:"
& $PipExe freeze

Write-Host ""
Write-Host "Verifying Python syntax..."
& $PythonExe -m py_compile $AgentSourceFile
& $PythonExe -m py_compile $TraySourceFile
& $PythonExe -m py_compile $RecorderSourceFile

Write-Host "Verifying runtime imports..."
$ImportCheck = @"
import flask
import waitress
import pyautogui
import pystray
import PIL
import pynput
from pynput import mouse, keyboard
import six
print("Import check OK")
"@

& $PythonExe -c $ImportCheck

Write-Host "Cleaning old build output..."
Remove-Item -Path (Join-Path $InstallerDir "build") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path (Join-Path $InstallerDir "dist") -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Building agent executable with PyInstaller..."
Push-Location $InstallerDir
try {
  & $PyInstallerExe --clean --noconfirm $AgentSpecFile
}
finally {
  Pop-Location
}

if (-not (Test-Path $AgentDistExe)) {
  throw "PyInstaller did not create $AgentDistExe"
}

Write-Host "Agent built:"
Write-Host $AgentDistExe

Write-Host ""
Write-Host "Building tray executable with PyInstaller..."
Push-Location $InstallerDir
try {
  & $PyInstallerExe --clean --noconfirm $TraySpecFile
}
finally {
  Pop-Location
}

if (-not (Test-Path $TrayDistExe)) {
  throw "PyInstaller did not create $TrayDistExe"
}

Write-Host "Tray app built:"
Write-Host $TrayDistExe

Write-Host ""
Write-Host "Verifying built executables exist..."
if ((Get-Item $AgentDistExe).Length -le 0) {
  throw "Agent executable is empty: $AgentDistExe"
}

if ((Get-Item $TrayDistExe).Length -le 0) {
  throw "Tray executable is empty: $TrayDistExe"
}

$IsccExe = $null
$IsccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue

if ($IsccCommand) {
  if ($IsccCommand.Source) {
    $IsccExe = $IsccCommand.Source
  }
  elseif ($IsccCommand.Path) {
    $IsccExe = $IsccCommand.Path
  }
}

if (-not $IsccExe) {
  $CandidatePaths = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 7\ISCC.exe"
  )

  foreach ($CandidatePath in $CandidatePaths) {
    if ($CandidatePath -and (Test-Path $CandidatePath)) {
      $IsccExe = $CandidatePath
      break
    }
  }
}

if (-not $IsccExe) {
  throw "Inno Setup compiler ISCC.exe was not found. Install Inno Setup 6 or 7 first."
}

Write-Host ""
Write-Host "Using Inno Setup compiler:"
Write-Host $IsccExe

Write-Host "Compiling installer with Inno Setup..."
Push-Location $InstallerDir
try {
  & $IsccExe $InnoScript
}
finally {
  Pop-Location
}

if (-not (Test-Path $SetupExe)) {
  throw "Inno Setup did not create $SetupExe"
}

if ((Get-Item $SetupExe).Length -le 0) {
  throw "Installer executable is empty: $SetupExe"
}

Write-Host ""
Write-Host "Build complete:"
Write-Host $SetupExe
Write-Host ""