; GX Shell: WezTerm GX + Oh My Zsh GX (GX Zsh) + herdr in one per-user installer.
; Payload is assembled by scripts/gx_shell_package.py; component launchers locate
; their resources relative to their own executables, so the layout below is fixed.
#ifndef GxVersion
  #error GxVersion is required
#endif
#ifndef GxPayload
  #error GxPayload is required
#endif
#ifndef GxOutput
  #error GxOutput is required
#endif
#ifndef GxFilename
  #error GxFilename is required
#endif
#ifndef GxIcon
  #error GxIcon is required
#endif

[Setup]
AppId={{EDDE7553-FF3A-4F95-B9A5-E4D037FEE617}
AppName=GX Shell
AppVersion={#GxVersion}
AppVerName=GX Shell {#GxVersion}
AppPublisher=gx0404
AppPublisherURL=https://github.com/gx0404/gx_shell
DefaultDirName={localappdata}\Programs\GXShell
DisableDirPage=yes
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763
OutputDir={#GxOutput}
OutputBaseFilename={#GxFilename}
SetupIconFile={#GxIcon}
UninstallDisplayIcon={app}\wezterm\wezterm-gui.exe
UninstallDisplayName=GX Shell
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
ChangesEnvironment=yes
ChangesAssociations=no
CloseApplications=no
RestartApplications=no
RestartIfNeededByRun=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[CustomMessages]
english.LegacyPrompt=Separately installed GX components were found:%n%1%nThey will be uninstalled first; user settings are kept. Continue?
chinesesimplified.LegacyPrompt=检测到单独安装的旧版 GX 组件：%n%1%n将先卸载它们，用户配置会保留。是否继续？
english.LegacyDeclined=Installation cancelled. Uninstall the older GX components first.
chinesesimplified.LegacyDeclined=已取消安装。请先卸载旧版 GX 组件。
english.LegacyFailed=Could not uninstall %1. Close its programs or uninstall it manually, then run setup again.
chinesesimplified.LegacyFailed=无法卸载 %1。请关闭相关程序或手动卸载后重新运行安装程序。
english.LegacyMachine=WezTerm GX is installed for all users and cannot be removed by this per-user setup. Uninstall it from Settings > Apps to avoid duplicate shortcuts.
chinesesimplified.LegacyMachine=检测到为所有用户安装的 WezTerm GX，按用户安装的本程序无法移除它。请在“设置 > 应用”中卸载，以免出现重复的快捷方式。
english.UnsupportedPath=Choose a local installation path of 4 to 100 characters without semicolons or line breaks.
chinesesimplified.UnsupportedPath=请选择 4 到 100 个字符、不含分号和换行的本地安装路径。
english.OwnedElsewhere=Uninstall the existing GX Shell before changing its directory. User profile data will be preserved.
chinesesimplified.OwnedElsewhere=请先卸载现有的 GX Shell 再更换安装目录，用户配置会保留。
english.UnownedDirectory=Refusing to install over a non-empty directory that GX Shell does not own.
chinesesimplified.UnownedDirectory=目标目录非空且不属于 GX Shell，已拒绝安装。
english.BusyFiles=Close WezTerm GX and GX Zsh, run "herdr server stop", then retry. No processes will be terminated. In-use or unsafe file: %1
chinesesimplified.BusyFiles=请关闭 WezTerm GX 和 GX Zsh 并运行 herdr server stop 后重试，安装程序不会结束任何进程。被占用或不安全的文件：%1
english.HerdrConflictSilent=An existing herdr command conflicts: %1. Resolve it before unattended installation.
chinesesimplified.HerdrConflictSilent=已有的 herdr 命令存在冲突：%1。请先处理后再静默安装。
english.HerdrConflict=An existing herdr command was found:%n%1%nGX Shell will not replace it or prepend PATH, so it may still resolve first. Continue?
chinesesimplified.HerdrConflict=检测到已有的 herdr 命令：%n%1%nGX Shell 不会替换它，也不会把自身放到 PATH 最前，它可能仍被优先使用。是否继续？
english.HerdrCancelled=Installation cancelled because of the existing herdr command.
chinesesimplified.HerdrCancelled=因已有的 herdr 命令，安装已取消。
english.HerdrResolution=PATH does not resolve herdr to GX Shell: %1%nUse the GX Zsh shortcut or the full path and resolve the conflict yourself. Nothing else was modified.
chinesesimplified.HerdrResolution=PATH 中的 herdr 没有指向 GX Shell：%1%n请使用 GX Zsh 快捷方式或完整路径，并自行处理冲突；其他内容未被修改。
english.UninstallBusy=Close WezTerm GX and GX Zsh, run "herdr server stop", then retry. No processes will be terminated. In-use or unsafe file: %1
chinesesimplified.UninstallBusy=请关闭 WezTerm GX 和 GX Zsh 并运行 herdr server stop 后重试，卸载程序不会结束任何进程。被占用或不安全的文件：%1

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[InstallDelete]
; 0.1.0 shipped the base snapshot's msys2-runtime 3.6.10-5; the payload now carries 3.6.10-6, so drop the stale
; pacman record on upgrade instead of leaving two installed versions in the local database.
Type: filesandordirs; Name: "{app}\runtime\msys64\var\lib\pacman\local\msys2-runtime-3.6.10-5"

[Files]
Source: "{#GxPayload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; GX Zsh opens in WezTerm GX: the console host lacks the Nerd Font glyphs of the prompt. --domain local keeps it
; local when the default shell is a WSL domain; --attach skips gui-startup, which would open a second window.
Name: "{autoprograms}\WezTerm GX"; Filename: "{app}\wezterm\wezterm-gx.exe"; IconFilename: "{app}\wezterm\wezterm-gui.exe"
Name: "{autoprograms}\GX Zsh"; Filename: "{app}\wezterm\wezterm-gx.exe"; Parameters: "start --domain local --attach -- ""{app}\bin\gx-zsh.exe"""; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\bin\gx-zsh.exe"
Name: "{autodesktop}\WezTerm GX"; Filename: "{app}\wezterm\wezterm-gx.exe"; IconFilename: "{app}\wezterm\wezterm-gui.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\wezterm\wezterm-gx.exe"; Description: "{cm:LaunchProgram,WezTerm GX}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\wezterm-gx.exe"; ValueType: string; ValueData: "{app}\wezterm\wezterm-gx.exe"; Flags: uninsdeletekey

[Code]
const
  OwnerKey = 'Software\GX Shell';
  FontKey = 'Software\Microsoft\Windows NT\CurrentVersion\Fonts';
  EnvironmentKey = 'Environment';
  UninstallRoot = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\';
  FontPrefix = 'GXShell ';
  LegacyCount = 3;
  WM_FONTCHANGE = $001D;
var
  Conflict, PreviousPath, WrittenPath, PreviousOwner, PreviousInstall, LegacyWezTermDir: String;
  HadPath, HadOwner, HadInstall, PathWritten: Boolean;
  NewFonts: TArrayOfString;

function CreateFileW(Name: String; Access, Sharing: LongWord; Security: Integer;
  Creation, Attributes: LongWord; Template: Integer): Integer;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseHandle(Handle: Integer): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';
function AddFontResourceExW(Name: String; Flags: LongWord; Reserved: Integer): Integer;
  external 'AddFontResourceExW@gdi32.dll stdcall';
function RemoveFontResourceExW(Name: String; Flags: LongWord; Reserved: Integer): Boolean;
  external 'RemoveFontResourceExW@gdi32.dll stdcall';
function ExpandEnvironmentStringsW(Source: String; Destination: String; Size: LongWord): LongWord;
  external 'ExpandEnvironmentStringsW@kernel32.dll stdcall';

function ExpandEnvironment(const Value: String): String;
var N: LongWord;
begin
  SetLength(Result, 32768);
  N := ExpandEnvironmentStringsW(Value, Result, 32768);
  if (N > 0) and (N <= 32768) then SetLength(Result, N - 1)
  else Result := Value;
end;

function NormalizeEntry(Value: String): String;
begin
  Value := Trim(Value);
  if (Length(Value) >= 2) and (Value[1] = '"') and (Value[Length(Value)] = '"') then
    Value := Copy(Value, 2, Length(Value) - 2);
  Result := Lowercase(RemoveBackslashUnlessRoot(ExpandEnvironment(Value)));
end;

function NextEntry(var Value: String): String;
var P: Integer;
begin
  P := Pos(';', Value);
  if P = 0 then begin Result := Value; Value := ''; end
  else begin Result := Copy(Value, 1, P - 1); Delete(Value, 1, P); end;
end;

function EntryCount(Value, Entry: String): Integer;
begin
  Result := 0;
  while Value <> '' do
    if NormalizeEntry(NextEntry(Value)) = NormalizeEntry(Entry) then Result := Result + 1;
end;

{ Separately released components replaced by GX Shell: WezTerm GX, Oh My Zsh GX, Herdr GX. }
function LegacyName(Index: Integer): String;
begin
  case Index of
    0: Result := 'WezTerm GX';
    1: Result := 'Oh My Zsh GX';
  else Result := 'Herdr GX';
  end;
end;

function LegacyKey(Index: Integer): String;
begin
  case Index of
    0: Result := UninstallRoot + '{734DC47D-4799-46A6-A286-4A64B802370A}_is1';
    1: Result := UninstallRoot + '{DBB81CDE-31BB-487C-9D03-36C19031CC5D}_is1';
  else Result := UninstallRoot + '{532CEFC3-E286-41A4-B097-631BD705DB76}_is1';
  end;
end;

function UninstallLegacy(Index: Integer): Boolean;
var Command: String; Code, Waited: Integer;
begin
  Result := False;
  if not RegQueryStringValue(HKCU, LegacyKey(Index), 'UninstallString', Command) then exit;
  Command := RemoveQuotes(Trim(Command));
  Log('Uninstalling ' + LegacyName(Index) + ' with ' + Command);
  if not FileExists(Command) then exit;
  if not Exec(Command, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Code) then exit;
  if Code <> 0 then begin Log('Legacy uninstaller exit code: ' + IntToStr(Code)); exit; end;
  { The Inno uninstaller finishes in a relaunched temporary copy; wait for its record to disappear. }
  Waited := 0;
  while RegKeyExists(HKCU, LegacyKey(Index)) and (Waited < 120000) do begin
    Sleep(500);
    Waited := Waited + 500;
  end;
  Result := not RegKeyExists(HKCU, LegacyKey(Index));
end;

function RemoveLegacyInstallations: String;
var Found: String; I: Integer;
begin
  Result := '';
  if not RegQueryStringValue(HKCU, LegacyKey(0), 'InstallLocation', LegacyWezTermDir) or (LegacyWezTermDir = '') then
    LegacyWezTermDir := ExpandConstant('{localappdata}\Programs\WezTerm GX\');
  if RegKeyExists(HKLM, LegacyKey(0)) or (IsWin64 and RegKeyExists(HKLM64, LegacyKey(0))) then begin
    Log('All-users WezTerm GX installation detected; it cannot be removed per-user.');
    if not WizardSilent then MsgBox(CustomMessage('LegacyMachine'), mbInformation, MB_OK);
  end;
  Found := '';
  for I := 0 to LegacyCount - 1 do
    if RegKeyExists(HKCU, LegacyKey(I)) then Found := Found + '  ' + LegacyName(I) + #13#10;
  if Found = '' then exit;
  if not WizardSilent and
     (MsgBox(FmtMessage(CustomMessage('LegacyPrompt'), [Found]), mbConfirmation, MB_YESNO) <> IDYES) then begin
    Result := CustomMessage('LegacyDeclined'); exit;
  end;
  for I := 0 to LegacyCount - 1 do
    if RegKeyExists(HKCU, LegacyKey(I)) and not UninstallLegacy(I) then begin
      Result := FmtMessage(CustomMessage('LegacyFailed'), [LegacyName(I)]); exit;
    end;
end;

function ResolvedHerdr: String;
var MachinePath, UserPath, Search, Entry: String;
begin
  Result := '';
  RegQueryStringValue(HKLM, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', MachinePath);
  RegQueryStringValue(HKCU, EnvironmentKey, 'Path', UserPath);
  Search := MachinePath + ';' + UserPath;
  while Search <> '' do begin
    Entry := ExpandEnvironment(Trim(NextEntry(Search)));
    if (Length(Entry) >= 2) and (Entry[1] = '"') and (Entry[Length(Entry)] = '"') then
      Entry := Copy(Entry, 2, Length(Entry) - 2);
    if (Entry <> '') and FileExists(AddBackslash(Entry) + 'herdr.exe') then begin
      Result := AddBackslash(Entry) + 'herdr.exe'; exit;
    end;
    if (Entry <> '') and (FileExists(AddBackslash(Entry) + 'herdr.cmd') or FileExists(AddBackslash(Entry) + 'herdr.bat')) then begin
      Result := Entry + '\herdr (script)'; exit;
    end;
  end;
end;

function BusyFile(const Directory: String): String;
var Item: TFindRec; Path, Extension: String; Handle: Integer;
begin
  Result := '';
  if not DirExists(Directory) then exit;
  if FindFirst(AddBackslash(Directory) + '*', Item) then begin
    try
      repeat
        if (Item.Name <> '.') and (Item.Name <> '..') then begin
          Path := AddBackslash(Directory) + Item.Name;
          if (Item.Attributes and FILE_ATTRIBUTE_REPARSE_POINT) <> 0 then begin
            Result := 'Unsupported reparse point: ' + Path; exit;
          end;
          if (Item.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then begin
            Result := BusyFile(Path);
            if Result <> '' then exit;
          end else begin
            Extension := Lowercase(ExtractFileExt(Path));
            if ((Extension = '.exe') or (Extension = '.dll')) and
               (NormalizeEntry(Path) <> NormalizeEntry(ExpandConstant('{uninstallexe}'))) then begin
              Handle := CreateFileW(Path, $80000000 or $40000000, 0, 0, 3, 0, 0);
              if Handle = -1 then begin Result := Path; exit; end;
              CloseHandle(Handle);
            end;
          end;
        end;
      until not FindNext(Item);
    finally
      FindClose(Item);
    end;
  end;
end;

function SupportedDirectory(const Directory: String): Boolean;
begin
  Result := (Length(Directory) >= 4) and (Length(Directory) <= 100) and
    (Copy(Directory, 1, 2) <> '\\') and (Pos(';', Directory) = 0) and
    (Pos(#13, Directory) = 0) and (Pos(#10, Directory) = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Busy, ExistingOwner: String; HasOwner: Boolean; Item: TFindRec;
begin
  Result := '';
  if not SupportedDirectory(ExpandConstant('{app}')) then begin Result := CustomMessage('UnsupportedPath'); exit; end;
  HasOwner := RegQueryStringValue(HKCU, OwnerKey, 'InstallDir', ExistingOwner);
  if HasOwner and (NormalizeEntry(ExistingOwner) <> NormalizeEntry(ExpandConstant('{app}'))) then begin
    Result := CustomMessage('OwnedElsewhere'); exit;
  end;
  if not HasOwner and FindFirst(ExpandConstant('{app}\*'), Item) then begin
    try
      repeat
        if (Item.Name <> '.') and (Item.Name <> '..') then begin
          Result := CustomMessage('UnownedDirectory'); exit;
        end;
      until not FindNext(Item);
    finally
      FindClose(Item);
    end;
  end;
  Busy := BusyFile(ExpandConstant('{app}'));
  if Busy <> '' then begin
    Result := FmtMessage(CustomMessage('BusyFiles'), [Busy]); exit;
  end;
  Result := RemoveLegacyInstallations;
  if Result <> '' then exit;
  Conflict := ResolvedHerdr;
  if (Conflict <> '') and (NormalizeEntry(Conflict) <> NormalizeEntry(ExpandConstant('{app}\bin\herdr.exe'))) then begin
    if WizardSilent then begin
      Result := FmtMessage(CustomMessage('HerdrConflictSilent'), [Conflict]); exit;
    end;
    if MsgBox(FmtMessage(CustomMessage('HerdrConflict'), [Conflict]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) <> IDYES then
      Result := CustomMessage('HerdrCancelled');
  end;
end;

procedure AddOwnedPath;
var Value, Entry: String;
begin
  Entry := ExpandConstant('{app}\bin');
  HadPath := RegQueryStringValue(HKCU, EnvironmentKey, 'Path', PreviousPath);
  HadOwner := RegQueryStringValue(HKCU, OwnerKey, 'PathEntry', PreviousOwner);
  HadInstall := RegQueryStringValue(HKCU, OwnerKey, 'InstallDir', PreviousInstall);
  if HadOwner and (NormalizeEntry(PreviousOwner) <> NormalizeEntry(Entry)) then
    RaiseException('PATH ownership belongs to a different installation.');
  if EntryCount(PreviousPath, Entry) = 0 then begin
    Value := PreviousPath;
    if (Value <> '') and (Copy(Value, Length(Value), 1) <> ';') then Value := Value + ';';
    WrittenPath := Value + Entry;
    if not RegWriteStringValue(HKCU, OwnerKey, 'PathEntry', Entry) then
      RaiseException('Cannot persist PATH ownership.');
    if not RegWriteExpandStringValue(HKCU, EnvironmentKey, 'Path', WrittenPath) then
      RaiseException('Cannot update user PATH.');
    PathWritten := True;
  end;
  if not RegWriteStringValue(HKCU, OwnerKey, 'InstallDir', ExpandConstant('{app}')) then
    RaiseException('Cannot persist installation ownership.');
end;

procedure RemoveOwnedPath;
var Owned, Value, Remaining, Entry: String;
begin
  if not RegQueryStringValue(HKCU, OwnerKey, 'PathEntry', Owned) then exit;
  if NormalizeEntry(Owned) <> NormalizeEntry(ExpandConstant('{app}\bin')) then exit;
  RegQueryStringValue(HKCU, EnvironmentKey, 'Path', Value);
  if EntryCount(Value, Owned) = 1 then begin
    Remaining := '';
    while Value <> '' do begin
      Entry := NextEntry(Value);
      if NormalizeEntry(Entry) <> NormalizeEntry(Owned) then begin
        if Remaining <> '' then Remaining := Remaining + ';';
        Remaining := Remaining + Entry;
      end;
    end;
    if not RegWriteExpandStringValue(HKCU, EnvironmentKey, 'Path', Remaining) then
      RaiseException('Cannot remove the owned user PATH entry.');
  end else Log('PATH entry was removed or duplicated externally; preserving the current PATH.');
  RegDeleteValue(HKCU, OwnerKey, 'PathEntry');
end;

procedure FontsMatching(Installing: Boolean; const Mask: String);
var Item: TFindRec; Path, Key, Existing: String; N: Integer;
begin
  if FindFirst(ExpandConstant('{app}\fonts\') + Mask, Item) then begin
    try
      repeat
        Path := ExpandConstant('{app}\fonts\') + Item.Name;
        Key := FontPrefix + Item.Name + ' (TrueType)';
        if Installing then begin
          if not RegQueryStringValue(HKCU, FontKey, Key, Existing) then begin
            N := GetArrayLength(NewFonts);
            SetArrayLength(NewFonts, N + 1);
            NewFonts[N] := Item.Name;
            if not RegWriteStringValue(HKCU, OwnerKey + '\Fonts', Key, Path) then RaiseException('Cannot persist font ownership.');
            if not RegWriteStringValue(HKCU, FontKey, Key, Path) then RaiseException('Cannot register user font.');
            if AddFontResourceExW(Path, 0, 0) = 0 then RaiseException('Cannot load user font.');
          end;
        end else if RegQueryStringValue(HKCU, OwnerKey + '\Fonts', Key, Existing) and (Existing = Path) then begin
          if RegQueryStringValue(HKCU, FontKey, Key, Existing) and (Existing = Path) then begin
            RemoveFontResourceExW(Path, 0, 0);
            RegDeleteValue(HKCU, FontKey, Key);
          end;
          RegDeleteValue(HKCU, OwnerKey + '\Fonts', Key);
        end;
      until not FindNext(Item);
    finally
      FindClose(Item);
    end;
  end;
end;

procedure Fonts(Installing: Boolean);
begin
  FontsMatching(Installing, '*.ttf');
  FontsMatching(Installing, '*.ttc');
  SendBroadcastNotifyMessage(WM_FONTCHANGE, 0, 0);
end;

procedure RollbackRegistration;
var Current, Key, Path: String; I: Integer;
begin
  for I := 0 to GetArrayLength(NewFonts) - 1 do begin
    Key := FontPrefix + NewFonts[I] + ' (TrueType)';
    Path := ExpandConstant('{app}\fonts\') + NewFonts[I];
    if RegQueryStringValue(HKCU, FontKey, Key, Current) and (Current = Path) then begin
      RemoveFontResourceExW(Path, 0, 0);
      RegDeleteValue(HKCU, FontKey, Key);
    end;
    if RegQueryStringValue(HKCU, OwnerKey + '\Fonts', Key, Current) and (Current = Path) then
      RegDeleteValue(HKCU, OwnerKey + '\Fonts', Key);
  end;
  if PathWritten then begin
    RegQueryStringValue(HKCU, EnvironmentKey, 'Path', Current);
    if Current = WrittenPath then begin
      if HadPath then RegWriteExpandStringValue(HKCU, EnvironmentKey, 'Path', PreviousPath)
      else RegDeleteValue(HKCU, EnvironmentKey, 'Path');
    end else begin
      Log('Concurrent PATH edit detected during rollback; preserving it and the ownership record.');
      exit;
    end;
  end;
  if HadOwner then RegWriteStringValue(HKCU, OwnerKey, 'PathEntry', PreviousOwner)
  else RegDeleteValue(HKCU, OwnerKey, 'PathEntry');
  if HadInstall then RegWriteStringValue(HKCU, OwnerKey, 'InstallDir', PreviousInstall)
  else RegDeleteValue(HKCU, OwnerKey, 'InstallDir');
end;

{ Retarget the shortcut created by the older dotfiles/install.ps1 chain, whether it still points
  there or into the directory of the replaced WezTerm GX 0.3.0, whose installer had moved it. }
procedure MigrateLegacyShortcut;
var LinkPath, TargetPath, TargetName, LegacyRoot: String; Shell, Shortcut: Variant;
begin
  LinkPath := ExpandConstant('{userprograms}\WezTerm (gx).lnk');
  if not FileExists(LinkPath) then exit;
  try
    Shell := CreateOleObject('WScript.Shell');
    Shortcut := Shell.CreateShortcut(LinkPath);
    TargetPath := Shortcut.TargetPath;
    TargetPath := Lowercase(TargetPath);
    TargetName := ExtractFileName(TargetPath);
    LegacyRoot := Lowercase(ExpandConstant('{localappdata}\Programs\wezterm-gx\'));
    if ((Pos(LegacyRoot, TargetPath) = 1) and (TargetName = 'wezterm-gui.exe')) or
       ((NormalizeEntry(ExtractFilePath(TargetPath)) = NormalizeEntry(LegacyWezTermDir)) and
        ((TargetName = 'wezterm-gx.exe') or (TargetName = 'wezterm-gui.exe'))) then begin
      Shortcut.TargetPath := ExpandConstant('{app}\wezterm\wezterm-gx.exe');
      Shortcut.IconLocation := ExpandConstant('{app}\wezterm\wezterm-gui.exe') + ',0';
      Shortcut.Save();
    end;
  except
    Log('Legacy shortcut was not changed: ' + GetExceptionMessage);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Failure: String;
begin
  if CurStep = ssPostInstall then begin
    try
      AddOwnedPath;
      Fonts(True);
    except
      Failure := GetExceptionMessage;
      RollbackRegistration;
      RaiseException(Failure);
    end;
    MigrateLegacyShortcut;
    Conflict := ResolvedHerdr;
    Log('Persistent PATH resolves herdr to: ' + Conflict);
    if (NormalizeEntry(Conflict) <> NormalizeEntry(ExpandConstant('{app}\bin\herdr.exe'))) and not WizardSilent then
      MsgBox(FmtMessage(CustomMessage('HerdrResolution'), [Conflict]), mbInformation, MB_OK);
  end;
end;

function InitializeUninstall: Boolean;
var Busy: String;
begin
  Busy := BusyFile(ExpandConstant('{app}'));
  Result := Busy = '';
  if not Result then begin
    Log('InitializeUninstall refused: ' + Busy);
    if not UninstallSilent then
      SuppressibleMsgBox(FmtMessage(CustomMessage('UninstallBusy'), [Busy]), mbError, MB_OK, IDOK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then begin
    RemoveOwnedPath;
    Fonts(False);
    RegDeleteValue(HKCU, OwnerKey, 'InstallDir');
    RegDeleteKeyIfEmpty(HKCU, OwnerKey + '\Fonts');
    RegDeleteKeyIfEmpty(HKCU, OwnerKey);
  end;
end;
