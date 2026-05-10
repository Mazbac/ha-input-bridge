#define MyAppName "HA Input Bridge"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Mazbac"
#define MyAppExeName "ha-input-bridge-agent.exe"

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

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\HA Input Bridge\Connection Info"; Filename: "{app}\connection-info.txt"
Name: "{autoprograms}\HA Input Bridge\Install Folder"; Filename: "{app}"

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall-cleanup.ps1"""; Flags: runhidden; RunOnceId: "HAInputBridgeCleanup"

[Code]
var
  ConfigPage: TInputQueryWizardPage;

function CRLF(): String;
begin
  Result := #13#10;
end;

function PsQuote(Value: String): String;
begin
  StringChangeEx(Value, Chr(39), Chr(39) + Chr(39), True);
  Result := Chr(39) + Value + Chr(39);
end;

function TrimText(Value: String): String;
begin
  Result := Trim(Value);
end;

function IsDigitsOnly(Value: String): Boolean;
var
  I: Integer;
begin
  Result := Length(Value) > 0;

  for I := 1 to Length(Value) do
  begin
    if Pos(Copy(Value, I, 1), '0123456789') = 0 then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

procedure InitializeWizard();
begin
  ConfigPage := CreateInputQueryPage(
    wpSelectDir,
    'Bridge configuration',
    'Configure the Windows bridge connection.',
    'Enter the Windows PC IP address and the Home Assistant IP address.'
  );

  ConfigPage.Add('Windows PC IP address to listen on:', False);
  ConfigPage.Add('Home Assistant IP address allowed to connect:', False);
  ConfigPage.Add('Bridge port:', False);

  ConfigPage.Values[0] := '';
  ConfigPage.Values[1] := '';
  ConfigPage.Values[2] := '8765';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  PortNumber: Integer;
begin
  Result := True;

  if CurPageID = ConfigPage.ID then
  begin
    ConfigPage.Values[0] := TrimText(ConfigPage.Values[0]);
    ConfigPage.Values[1] := TrimText(ConfigPage.Values[1]);
    ConfigPage.Values[2] := TrimText(ConfigPage.Values[2]);

    if ConfigPage.Values[0] = '' then
    begin
      MsgBox('Enter the Windows PC IP address.', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    if ConfigPage.Values[1] = '' then
    begin
      MsgBox('Enter the Home Assistant IP address.', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    if not IsDigitsOnly(ConfigPage.Values[2]) then
    begin
      MsgBox('Enter a numeric bridge port.', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    PortNumber := StrToIntDef(ConfigPage.Values[2], 0);

    if (PortNumber < 1) or (PortNumber > 65535) then
    begin
      MsgBox('Enter a bridge port between 1 and 65535.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;

function BuildPostInstallScript(): String;
var
  S: String;
  AppDir: String;
  BindHost: String;
  AllowedClientIp: String;
  Port: String;
begin
  AppDir := ExpandConstant('{app}');
  BindHost := ConfigPage.Values[0];
  AllowedClientIp := ConfigPage.Values[1];
  Port := ConfigPage.Values[2];

  S := '';
  S := S + '$ErrorActionPreference = "Stop"' + CRLF();
  S := S + CRLF();

  S := S + '$InstallDir = ' + PsQuote(AppDir) + CRLF();
  S := S + '$DataDir = Join-Path $env:ProgramData "HA Input Bridge"' + CRLF();
  S := S + '$AgentExe = Join-Path $InstallDir "ha-input-bridge-agent.exe"' + CRLF();
  S := S + '$StartScript = Join-Path $InstallDir "start_ha_input_bridge.ps1"' + CRLF();
  S := S + '$UninstallScript = Join-Path $InstallDir "uninstall-cleanup.ps1"' + CRLF();
  S := S + '$InfoPath = Join-Path $InstallDir "connection-info.txt"' + CRLF();
  S := S + '$RuntimeLog = Join-Path $DataDir "task_runtime.log"' + CRLF();
  S := S + '$BridgeLog = Join-Path $DataDir "ha_input_bridge.log"' + CRLF();
  S := S + '$TaskName = "HA Input Bridge"' + CRLF();
  S := S + '$FirewallRuleName = "HA Input Bridge - Home Assistant only"' + CRLF();
  S := S + '$BindHost = ' + PsQuote(BindHost) + CRLF();
  S := S + '$AllowedClientIp = ' + PsQuote(AllowedClientIp) + CRLF();
  S := S + '$Port = ' + Port + CRLF();
  S := S + '$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name' + CRLF();
  S := S + CRLF();

  S := S + 'New-Item -ItemType Directory -Path $DataDir -Force | Out-Null' + CRLF();
  S := S + '& icacls $DataDir /grant "${CurrentUser}:(OI)(CI)M" /T | Out-Null' + CRLF();
  S := S + CRLF();

  S := S + '$TokenBytes = New-Object byte[] 32' + CRLF();
  S := S + '$Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()' + CRLF();
  S := S + '$Rng.GetBytes($TokenBytes)' + CRLF();
  S := S + '$Rng.Dispose()' + CRLF();
  S := S + '$Token = [Convert]::ToBase64String($TokenBytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")' + CRLF();
  S := S + CRLF();

  S := S + '$StartContent = @"' + CRLF();
  S := S + '`$env:HA_INPUT_TOKEN = ''$Token''' + CRLF();
  S := S + '`$env:HA_ALLOWED_CLIENT_IP = ''$AllowedClientIp''' + CRLF();
  S := S + '`$env:HA_INPUT_BIND_HOST = ''$BindHost''' + CRLF();
  S := S + '`$env:HA_INPUT_PORT = ''$Port''' + CRLF();
  S := S + '`$env:HA_INPUT_LOG_FILE = ''$BridgeLog''' + CRLF();
  S := S + '& "$AgentExe" *> "$RuntimeLog"' + CRLF();
  S := S + '"@' + CRLF();
  S := S + 'Set-Content -Path $StartScript -Value $StartContent -Encoding UTF8' + CRLF();
  S := S + CRLF();

  S := S + '$UninstallContent = @"' + CRLF();
  S := S + 'Stop-ScheduledTask -TaskName ''HA Input Bridge'' -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Unregister-ScheduledTask -TaskName ''HA Input Bridge'' -Confirm:`$false -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Get-NetFirewallRule -DisplayName ''HA Input Bridge - Home Assistant only'' -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Get-CimInstance Win32_Process | Where-Object { `$_.CommandLine -like ''*ha-input-bridge-agent.exe*'' } | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force -ErrorAction SilentlyContinue }' + CRLF();
  S := S + 'Remove-Item -Path "$env:ProgramData\HA Input Bridge" -Recurse -Force -ErrorAction SilentlyContinue' + CRLF();
  S := S + '"@' + CRLF();
  S := S + 'Set-Content -Path $UninstallScript -Value $UninstallContent -Encoding UTF8' + CRLF();
  S := S + CRLF();

  S := S + 'Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue' + CRLF();
  S := S + 'Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue' + CRLF();
  S := S + CRLF();

  S := S + 'New-NetFirewallRule -DisplayName $FirewallRuleName -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -RemoteAddress $AllowedClientIp | Out-Null' + CRLF();
  S := S + CRLF();

  S := S + '$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""' + CRLF();
  S := S + '$Trigger = New-ScheduledTaskTrigger -AtLogOn' + CRLF();
  S := S + '$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited' + CRLF();
  S := S + 'Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Description "HA Input Bridge Windows agent" -Force | Out-Null' + CRLF();
  S := S + 'Start-ScheduledTask -TaskName $TaskName' + CRLF();
  S := S + 'Start-Sleep -Seconds 2' + CRLF();
  S := S + CRLF();

  S := S + '$Info = @"' + CRLF();
  S := S + 'HA Input Bridge connection details' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Use these values in Home Assistant:' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Host: $BindHost' + CRLF();
  S := S + 'Port: $Port' + CRLF();
  S := S + 'Token: $Token' + CRLF();
  S := S + '' + CRLF();
  S := S + 'Logs:' + CRLF();
  S := S + '$DataDir' + CRLF();
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
