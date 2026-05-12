#define MyAppName "HA Input Bridge"
#define MyAppVersion "0.9.0"
#define MyAppPublisher "Mazbac"
#define MyAgentExeName "ha-input-bridge-agent.exe"
#define MyTrayExeName "ha-input-bridge-tray.exe"

[Setup]
AppId={{F7D823F3-6BB1-4D73-B61E-6E85C5E9E1A8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={commonpf}\HA Input Bridge
DefaultGroupName=HA Input Bridge
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=HA-Input-Bridge-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "starttray"; Description: "Start the tray icon after installation"; GroupDescription: "Startup:"; Flags: checkedonce
Name: "starttrayonlogin"; Description: "Start the tray icon when Windows starts"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
Source: "dist\{#MyAgentExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\{#MyTrayExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\HA Input Bridge\HA Input Bridge Tray"; Filename: "{app}\{#MyTrayExeName}"
Name: "{autoprograms}\HA Input Bridge\Connection Info"; Filename: "{app}\connection-info.txt"
Name: "{autoprograms}\HA Input Bridge\Logs Folder"; Filename: "{commonappdata}\HA Input Bridge"
Name: "{autoprograms}\HA Input Bridge\Install Folder"; Filename: "{app}"
Name: "{autodesktop}\HA Input Bridge"; Filename: "{app}\{#MyTrayExeName}"; Tasks: desktopicon
Name: "{userstartup}\HA Input Bridge Tray"; Filename: "{app}\{#MyTrayExeName}"; Tasks: starttrayonlogin

[Run]
Filename: "{app}\{#MyTrayExeName}"; Description: "Start HA Input Bridge tray icon"; Flags: nowait postinstall skipifsilent; Tasks: starttray

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall-cleanup.ps1"""; Flags: runhidden; RunOnceId: "HAInputBridgeCleanup"

[Code]
function CRLF(): String;
begin
  Result := #13#10;
end;

function PsQuote(Value: String): String;
begin
  StringChangeEx(Value, Chr(39), Chr(39) + Chr(39), True);
  Result := Chr(39) + Value + Chr(39);
end;

function BuildPostInstallScript(): String;
var
  S: String;
  AppDir: String;
begin
  AppDir := ExpandConstant('{app}');
  S := '';

  S := S + '$ErrorActionPreference = "Stop"' + CRLF();
  S := S + CRLF();

  S := S + '$InstallDir = ' + PsQuote(AppDir) + CRLF();
  S := S + '$DataDir = Join-Path $env:ProgramData "HA Input Bridge"' + CRLF();
  S := S + '$RecordingsDir = Join-Path $DataDir "recordings"' + CRLF();
  S := S + '$ConfigPath = Join-Path $DataDir "config.json"' + CRLF();
  S := S + '$AgentExe = Join-Path $InstallDir "ha-input-bridge-agent.exe"' + CRLF();
  S := S + '$TrayExe = Join-Path $InstallDir "ha-input-bridge-tray.exe"' + CRLF();
  S := S + '$StartScript = Join-Path $InstallDir "start_ha_input_bridge.ps1"' + CRLF();
  S := S + '$UninstallScript = Join-Path $InstallDir "uninstall-cleanup.ps1"' + CRLF();
  S := S + '$InfoPath = Join-Path $InstallDir "connection-info.txt"' + CRLF();
  S := S + '$RuntimeLog = Join-Path $DataDir "task_runtime.log"' + CRLF();
  S := S + '$BridgeLog = Join-Path $DataDir "ha_input_bridge.log"' + CRLF();
  S := S + '$TaskName = "HA Input Bridge"' + CRLF();
  S := S + '$FirewallRuleName = "HA Input Bridge - Home Assistant only"' + CRLF();
  S := S + '$DefaultBindHost = "0.0.0.0"' + CRLF();
  S := S + '$DefaultAllowedClientIp = ""' + CRLF();
  S := S + '$DefaultFirewallRemoteAddress = "LocalSubnet"' + CRLF();
  S := S + '$DefaultPort = 8765' + CRLF();
  S := S + '$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name' + CRLF();
  S := S + CRLF();

  S := S + 'function Get-HostScore {' + CRLF();
  S := S + '  param([string]$IpAddress)' + CRLF();
  S := S + '  $Parts = $IpAddress.Split(".")' + CRLF();
  S := S + '  if ($Parts.Count -lt 2) { return 50 }' + CRLF();
  S := S + '  $First = 0' + CRLF();
  S := S + '  $Second = 0' + CRLF();
  S := S + '  if (-not [int]::TryParse($Parts[0], [ref]$First)) { return 50 }' + CRLF();
  S := S + '  if (-not [int]::TryParse($Parts[1], [ref]$Second)) { return 50 }' + CRLF();
  S := S + '  if ($First -eq 192 -and $Second -eq 168) { return 10 }' + CRLF();
  S := S + '  if ($First -eq 10) { return 20 }' + CRLF();
  S := S + '  if ($First -eq 172 -and $Second -ge 16 -and $Second -le 31) { return 30 }' + CRLF();
  S := S + '  if ($First -eq 100 -and $Second -ge 64 -and $Second -le 127) { return 40 }' + CRLF();
  S := S + '  return 50' + CRLF();
  S := S + '}' + CRLF();
  S := S + CRLF();

  S := S + 'function Get-HostCandidates {' + CRLF();
  S := S + '  @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |' + CRLF();
  S := S + '    Where-Object {' + CRLF();
  S := S + '      $_.IPAddress -notlike "127.*" -and' + CRLF();
  S := S + '      $_.IPAddress -notlike "169.254.*" -and' + CRLF();
  S := S + '      $_.IPAddress -ne "0.0.0.0"' + CRLF();
  S := S + '    } |' + CRLF();
  S := S + '    Select-Object -ExpandProperty IPAddress -Unique |' + CRLF();
  S := S + '    Sort-Object @{ Expression = { Get-HostScore $_ } }, @{ Expression = { $_ } })' + CRLF();
  S := S + '}' + CRLF();
  S := S + CRLF();

  S := S + 'New-Item -ItemType Directory -Path $DataDir -Force | Out-Null' + CRLF();
  S := S + 'New-Item -ItemType Directory -Path $RecordingsDir -Force | Out-Null' + CRLF();
  S := S + '& icacls $DataDir /grant "${CurrentUser}:(OI)(CI)M" /T | Out-Null' + CRLF();
  S := S + CRLF();

  S := S + '$ExistingConfig = $null' + CRLF();
  S := S + 'if (Test-Path $ConfigPath) {' + CRLF();
  S := S + '  try {' + CRLF();
  S := S + '    $ExistingConfig = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json' + CRLF();
  S := S + '  }' + CRLF();
  S := S + '  catch {' + CRLF();
  S := S + '    $ExistingConfig = $null' + CRLF();
  S := S + '  }' + CRLF();
  S := S + '}' + CRLF();
  S := S + CRLF();

  S := S + '$BindHost = $DefaultBindHost' + CRLF();
  S := S + '$AllowedClientIp = $DefaultAllowedClientIp' + CRLF();
  S := S + '$FirewallRemoteAddress = $DefaultFirewallRemoteAddress' + CRLF();
  S := S + '$Port = $DefaultPort' + CRLF();
  S := S + '$Token = ""' + CRLF();
  S := S + '$StartBridgeOnLogin = $true' + CRLF();
  S := S + '$StartTrayOnLogin = $true' + CRLF();
  S := S + CRLF();

  S := S + 'if ($null -ne $ExistingConfig) {' + CRLF();
  S := S + '  if ($ExistingConfig.bind_host) { $BindHost = [string]$ExistingConfig.bind_host }' + CRLF();
  S := S + '  if ($null -ne $ExistingConfig.allowed_client_ip) { $AllowedClientIp = [string]$ExistingConfig.allowed_client_ip }' + CRLF();
  S := S + '  if ($ExistingConfig.firewall_remote_address) { $FirewallRemoteAddress = [string]$ExistingConfig.firewall_remote_address }' + CRLF();
  S := S + '  elseif ($ExistingConfig.allowed_client_ip) { $FirewallRemoteAddress = [string]$ExistingConfig.allowed_client_ip }' + CRLF();
  S := S + '  if ($ExistingConfig.port) { $Port = [int]$ExistingConfig.port }' + CRLF();
  S := S + '  if ($ExistingConfig.token) { $Token = [string]$ExistingConfig.token }' + CRLF();
  S := S + '  if ($null -ne $ExistingConfig.start_bridge_on_login) { $StartBridgeOnLogin = [bool]$ExistingConfig.start_bridge_on_login }' + CRLF();
  S := S + '  if ($null -ne $ExistingConfig.start_tray_on_login) { $StartTrayOnLogin = [bool]$ExistingConfig.start_tray_on_login }' + CRLF();
  S := S + '}' + CRLF();
  S := S + CRLF();

  S := S + 'if ($Port -lt 1 -or $Port -gt 65535) { $Port = $DefaultPort }' + CRLF();
  S := S + 'if ([string]::IsNullOrWhiteSpace($BindHost)) { $BindHost = $DefaultBindHost }' + CRLF();
  S := S + 'if ([string]::IsNullOrWhiteSpace($FirewallRemoteAddress)) { $FirewallRemoteAddress = $DefaultFirewallRemoteAddress }' + CRLF();
  S := S + CRLF();

  S := S + 'if ([string]::IsNullOrWhiteSpace($Token)) {' + CRLF();
  S := S + '  $TokenBytes = New-Object byte[] 32' + CRLF();
  S := S + '  $Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()' + CRLF();
  S := S + '  $Rng.GetBytes($TokenBytes)' + CRLF();
  S := S + '  $Rng.Dispose()' + CRLF();
  S := S + '  $Token = [Convert]::ToBase64String($TokenBytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")' + CRLF();
  S := S + '}' + CRLF();
  S := S + CRLF();

  S := S + '$HostCandidates = @(Get-HostCandidates)' + CRLF();
  S := S + '$RecommendedHost = if ($HostCandidates.Count -gt 0) { $HostCandidates[0] } else { "Use the Windows PC IP address" }' + CRLF();
  S := S + '$HostCandidateText = if ($HostCandidates.Count -gt 0) { $HostCandidates -join ", " } else { "Use the Windows PC IP address" }' + CRLF();
  S := S + CRLF();

  S := S + '$Config = [ordered]@{' + CRLF();
  S := S + '  bind_host = $BindHost' + CRLF();
  S := S + '  allowed_client_ip = $AllowedClientIp' + CRLF();
  S := S + '  firewall_remote_address = $FirewallRemoteAddress' + CRLF();
  S := S + '  port = [int]$Port' + CRLF();
  S := S + '  token = $Token' + CRLF();
  S := S + '  log_file = $BridgeLog' + CRLF();
  S := S + '  start_bridge_on_login = $StartBridgeOnLogin' + CRLF();
  S := S + '  start_tray_on_login = $StartTrayOnLogin' + CRLF();
  S := S + '}' + CRLF();
  S := S + '$Config | ConvertTo-Json -Depth 5 | Set-Content -Path $ConfigPath -Encoding UTF8' + CRLF();
  S := S + CRLF();

  S := S + '$StartContent = @"' + CRLF();
  S := S + '`$env:HA_INPUT_CONFIG_FILE = ''$ConfigPath''' + CRLF();
  S := S + '& "$AgentExe" *> "$RuntimeLog"' + CRLF();
  S := S + '"@' + CRLF();
  S := S + 'Set-Content -Path $StartScript -Value $StartContent -Encoding UTF8' + CRLF();
  S := S + CRLF();

  S := S + '$UninstallContent = @"' + CRLF();
  S := S + 'Stop-ScheduledTask -TaskName ''HA Input Bridge'' -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Unregister-ScheduledTask -TaskName ''HA Input Bridge'' -Confirm:`$false -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Get-NetFirewallRule -DisplayName ''HA Input Bridge - Home Assistant only'' -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Get-CimInstance Win32_Process | Where-Object { `$_.CommandLine -like ''*ha-input-bridge-agent.exe*'' -or `$_.CommandLine -like ''*ha-input-bridge-tray.exe*'' } | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force -ErrorAction SilentlyContinue }' + CRLF();
  S := S + 'Remove-Item -Path "$env:ProgramData\HA Input Bridge" -Recurse -Force -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Remove-Item -Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\HA Input Bridge Tray.lnk" -Force -ErrorAction SilentlyContinue' + CRLF();
  S := S + '"@' + CRLF();
  S := S + 'Set-Content -Path $UninstallScript -Value $UninstallContent -Encoding UTF8' + CRLF();
  S := S + CRLF();

  S := S + 'Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue' + CRLF();
  S := S + CRLF();

  S := S + 'Get-CimInstance Win32_Process |' + CRLF();
  S := S + '  Where-Object {' + CRLF();
  S := S + '    $_.CommandLine -like "*ha-input-bridge-agent.exe*" -or' + CRLF();
  S := S + '    $_.CommandLine -like "*ha-input-bridge-tray.exe*"' + CRLF();
  S := S + '  } |' + CRLF();
  S := S + '  ForEach-Object {' + CRLF();
  S := S + '    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue' + CRLF();
  S := S + '  }' + CRLF();
  S := S + CRLF();

  S := S + 'New-NetFirewallRule -DisplayName $FirewallRuleName -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -RemoteAddress $FirewallRemoteAddress | Out-Null' + CRLF();
  S := S + CRLF();

  S := S + '$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""' + CRLF();
  S := S + '$Trigger = New-ScheduledTaskTrigger -AtLogOn' + CRLF();
  S := S + '$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited' + CRLF();
  S := S + 'Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Description "HA Input Bridge Windows agent" -Force | Out-Null' + CRLF();
  S := S + CRLF();

  S := S + 'if ($StartBridgeOnLogin) {' + CRLF();
  S := S + '  Enable-ScheduledTask -TaskName $TaskName | Out-Null' + CRLF();
  S := S + '  Start-ScheduledTask -TaskName $TaskName' + CRLF();
  S := S + '}' + CRLF();
  S := S + 'else {' + CRLF();
  S := S + '  Disable-ScheduledTask -TaskName $TaskName | Out-Null' + CRLF();
  S := S + '}' + CRLF();
  S := S + CRLF();

  S := S + 'Start-Sleep -Seconds 2' + CRLF();
  S := S + CRLF();

  S := S + '$Info = @"' + CRLF();
  S := S + 'HA Input Bridge connection details' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Use these values in Home Assistant:' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Host: $RecommendedHost' + CRLF();
  S := S + 'Port: $Port' + CRLF();
  S := S + 'Token: $Token' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Possible Host values:' + CRLF();
  S := S + '$HostCandidateText' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Bridge bind address:' + CRLF();
  S := S + '$BindHost' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Firewall remote address:' + CRLF();
  S := S + '$FirewallRemoteAddress' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Tray app:' + CRLF();
  S := S + '$TrayExe' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Config:' + CRLF();
  S := S + '$ConfigPath' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Logs:' + CRLF();
  S := S + '$DataDir' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Recordings:' + CRLF();
  S := S + '$RecordingsDir' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Home Assistant setup:' + CRLF();
  S := S + 'Settings -> Devices & services -> Add integration -> HA Input Bridge' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Keep this token private.' + CRLF();
  S := S + '"@' + CRLF();
  S := S + 'Set-Content -Path $InfoPath -Value $Info -Encoding UTF8' + CRLF();

  Result := S;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  ScriptPath: String;
  InfoPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    ScriptPath := ExpandConstant('{app}\install-service.ps1');
    InfoPath := ExpandConstant('{app}\connection-info.txt');

    if not SaveStringToFile(ScriptPath, BuildPostInstallScript(), False) then
    begin
      MsgBox('Could not write install-service.ps1.', mbError, MB_OK);
      Exit;
    end;

    if not Exec(
      'powershell.exe',
      '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    ) then
    begin
      MsgBox('Could not start PowerShell post-install step.', mbError, MB_OK);
      Exit;
    end;

    if ResultCode <> 0 then
    begin
      MsgBox('PowerShell post-install step failed. Check the setup log.', mbError, MB_OK);
      Exit;
    end;

    ShellExec('', InfoPath, '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
  end;
end;
