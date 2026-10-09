; GX Shell: Ghostty GX + Oh My Zsh GX (GX Zsh) + herdr in one per-user installer.
; Payload is assembled by scripts/gx_shell_package.py; component launchers locate
; their resources relative to their own executables, so the layout below is fixed:
; Ghostty GX in {app}\ghostty finds GX Zsh and herdr in {app}\bin (<exe dir>\..\bin).
; GxFontNames lists the font files the payload ships ("|"-separated); fonts registered by an
; earlier version that it no longer ships are unregistered before their files are removed.
#if VER < EncodeVer(7, 1, 0) || VER >= EncodeVer(8, 0, 0)
  #error Inno Setup 7.1 is required
#endif
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
#ifndef GxFontNames
  #error GxFontNames is required
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
UninstallDisplayIcon={app}\ghostty\ghostty.exe
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
english.UnsupportedPath=Choose a local installation path of 4 to 100 characters without semicolons or line breaks.
chinesesimplified.UnsupportedPath=请选择 4 到 100 个字符、不含分号和换行的本地安装路径。
english.OwnedElsewhere=Uninstall the existing GX Shell before changing its directory. User profile data will be preserved.
chinesesimplified.OwnedElsewhere=请先卸载现有的 GX Shell 再更换安装目录，用户配置会保留。
english.UnownedDirectory=Refusing to install over a non-empty directory that GX Shell does not own.
chinesesimplified.UnownedDirectory=目标目录非空且不属于 GX Shell，已拒绝安装。
english.BusyFiles=Close Ghostty GX (and the WezTerm GX of an earlier GX Shell) and GX Zsh, run "herdr server stop", then retry. No processes will be terminated. In-use or unsafe file: %1
chinesesimplified.BusyFiles=请关闭 Ghostty GX（以及旧版 GX Shell 自带的 WezTerm GX）和 GX Zsh 并运行 herdr server stop 后重试，安装程序不会结束任何进程。被占用或不安全的文件：%1
english.HerdrConflictSilent=An existing herdr command conflicts: %1. Resolve it before unattended installation.
chinesesimplified.HerdrConflictSilent=已有的 herdr 命令存在冲突：%1。请先处理后再静默安装。
english.HerdrConflict=An existing herdr command was found:%n%1%nGX Shell will not replace it or prepend PATH, so it may still resolve first. Continue?
chinesesimplified.HerdrConflict=检测到已有的 herdr 命令：%n%1%nGX Shell 不会替换它，也不会把自身放到 PATH 最前，它可能仍被优先使用。是否继续？
english.HerdrCancelled=Installation cancelled because of the existing herdr command.
chinesesimplified.HerdrCancelled=因已有的 herdr 命令，安装已取消。
english.HerdrResolution=PATH does not resolve herdr to GX Shell: %1%nUse the GX Zsh shortcut or the full path and resolve the conflict yourself. Nothing else was modified.
chinesesimplified.HerdrResolution=PATH 中的 herdr 没有指向 GX Shell：%1%n请使用 GX Zsh 快捷方式或完整路径，并自行处理冲突；其他内容未被修改。
english.UninstallBusy=Close Ghostty GX and GX Zsh, run "herdr server stop", then retry. No processes will be terminated. In-use or unsafe file: %1
chinesesimplified.UninstallBusy=请关闭 Ghostty GX 和 GX Zsh 并运行 herdr server stop 后重试，卸载程序不会结束任何进程。被占用或不安全的文件：%1

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[InstallDelete]
; 0.1.0 shipped the base snapshot's msys2-runtime 3.6.10-5; the payload now carries 3.6.10-6, so drop the stale
; pacman record on upgrade instead of leaving two installed versions in the local database.
Type: filesandordirs; Name: "{app}\runtime\msys64\var\lib\pacman\local\msys2-runtime-3.6.10-5"
; GX Shell 0.3.0 and earlier bundled WezTerm GX here. Only the program directory goes: the WezTerm
; configuration (%USERPROFILE%\.config\wezterm) and its plugins, backups and logs are user data.
Type: filesandordirs; Name: "{app}\wezterm"

[Files]
Source: "{#GxPayload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Ghostty GX starts GX Zsh by default because {app}\bin\gx-zsh.exe sits next to its directory. The GX Zsh
; shortcut runs GX Zsh in the first tab even when another default shell is configured: -e takes the quoted
; path as one argument without shell parsing, so a profile path with spaces still works.
Name: "{autoprograms}\Ghostty GX"; Filename: "{app}\ghostty\ghostty.exe"; WorkingDir: "{%USERPROFILE}"
Name: "{autoprograms}\GX Zsh"; Filename: "{app}\ghostty\ghostty.exe"; Parameters: "-e ""{app}\bin\gx-zsh.exe"""; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\bin\gx-zsh.exe"
Name: "{autodesktop}\Ghostty GX"; Filename: "{app}\ghostty\ghostty.exe"; WorkingDir: "{%USERPROFILE}"; Tasks: desktopicon

[Run]
Filename: "{app}\ghostty\ghostty.exe"; Description: "{cm:LaunchProgram,Ghostty GX}"; WorkingDir: "{%USERPROFILE}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
const
  OwnerKey = 'Software\GX Shell';
  FontKey = 'Software\Microsoft\Windows NT\CurrentVersion\Fonts';
  EnvironmentKey = 'Environment';
  UninstallRoot = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\';
  AppPathsKey = 'Software\Microsoft\Windows\CurrentVersion\App Paths\';
  FontPrefix = 'GXShell ';
  FontSuffix = ' (TrueType)';
  ShippedFonts = '|{#GxFontNames}|';
  LegacyCount = 2;
  WezTermLinkCount = 3;
  WM_FONTCHANGE = $001D;
var
  Conflict, PreviousPath, WrittenPath, PreviousOwner, PreviousInstall: String;
  HadPath, HadOwner, HadInstall, PathWritten, AppPathWritten: Boolean;
  NewFonts: TArrayOfString;
  KeptLinks: array [0..1] of AnsiString;
  KeptLinkFound: array [0..1] of Boolean;
  KeptAppPathNames, KeptAppPathValues: TArrayOfString;
  KeptAppPath: Boolean;

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

{ Separately released components replaced by GX Shell: Oh My Zsh GX and Herdr GX. A separately
  installed WezTerm GX is no longer part of GX Shell and is left alone. }
function LegacyName(Index: Integer): String;
begin
  case Index of
    0: Result := 'Oh My Zsh GX';
  else Result := 'Herdr GX';
  end;
end;

function LegacyKey(Index: Integer): String;
begin
  case Index of
    0: Result := UninstallRoot + '{DBB81CDE-31BB-487C-9D03-36C19031CC5D}_is1';
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

function ShipsFont(const Name: String): Boolean;
begin
  Result := Pos('|' + Lowercase(Name) + '|', Lowercase(ShippedFonts)) > 0;
end;

procedure FontsMatching(Installing: Boolean; const Mask: String);
var Item: TFindRec; Path, Key, Existing: String; N: Integer;
begin
  if FindFirst(ExpandConstant('{app}\fonts\') + Mask, Item) then begin
    try
      repeat
        Path := ExpandConstant('{app}\fonts\') + Item.Name;
        Key := FontPrefix + Item.Name + FontSuffix;
        if Installing then begin
          if ShipsFont(Item.Name) and not RegQueryStringValue(HKCU, FontKey, Key, Existing) then begin
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

{ Before the new payload is copied: unregister every font that an earlier version registered and this
  payload no longer ships, then delete its file so that it is not registered again. }
procedure RemoveUnshippedFonts;
var Names: TArrayOfString; I: Integer; Key, Name, Path, Current: String; Changed: Boolean;
begin
  Changed := False;
  if not RegGetValueNames(HKCU, OwnerKey + '\Fonts', Names) then exit;
  for I := 0 to GetArrayLength(Names) - 1 do begin
    Key := Names[I];
    if (Length(Key) <= Length(FontPrefix) + Length(FontSuffix)) or (Copy(Key, 1, Length(FontPrefix)) <> FontPrefix) or
       (Copy(Key, Length(Key) - Length(FontSuffix) + 1, Length(FontSuffix)) <> FontSuffix) then continue;
    Name := Copy(Key, Length(FontPrefix) + 1, Length(Key) - Length(FontPrefix) - Length(FontSuffix));
    if ShipsFont(Name) or not RegQueryStringValue(HKCU, OwnerKey + '\Fonts', Key, Path) then continue;
    if NormalizeEntry(Path) <> NormalizeEntry(ExpandConstant('{app}\fonts\') + Name) then continue;
    if RegQueryStringValue(HKCU, FontKey, Key, Current) and (Current = Path) then begin
      RemoveFontResourceExW(Path, 0, 0);
      RegDeleteValue(HKCU, FontKey, Key);
    end;
    RegDeleteValue(HKCU, OwnerKey + '\Fonts', Key);
    if FileExists(Path) and not DeleteFile(Path) then Log('Unshipped font file was not deleted: ' + Path);
    Log('Unregistered the font no longer shipped: ' + Name);
    Changed := True;
  end;
  if Changed then SendBroadcastNotifyMessage(WM_FONTCHANGE, 0, 0);
end;

function GhosttyPath: String;
begin
  Result := ExpandConstant('{app}\ghostty\ghostty.exe');
end;

{ App Paths\ghostty.exe is shared with a separately installed Ghostty GX: write it only when it is absent
  or already ours, and remove it only while it still points to this installation. }
procedure RegisterAppPath;
var Current: String;
begin
  if RegQueryStringValue(HKCU, AppPathsKey + 'ghostty.exe', '', Current) then begin
    if NormalizeEntry(Current) <> NormalizeEntry(GhosttyPath) then begin
      Log('App Paths\ghostty.exe belongs to another installation: ' + Current);
      exit;
    end;
  end else AppPathWritten := True;
  if not RegWriteStringValue(HKCU, AppPathsKey + 'ghostty.exe', '', GhosttyPath) then
    RaiseException('Cannot register App Paths\ghostty.exe.');
end;

procedure UnregisterAppPath;
var Current: String;
begin
  if RegQueryStringValue(HKCU, AppPathsKey + 'ghostty.exe', '', Current) and
     (NormalizeEntry(Current) = NormalizeEntry(GhosttyPath)) then
    RegDeleteKeyIncludingSubkeys(HKCU, AppPathsKey + 'ghostty.exe');
end;

procedure RollbackRegistration;
var Current, Key, Path: String; I: Integer;
begin
  for I := 0 to GetArrayLength(NewFonts) - 1 do begin
    Key := FontPrefix + NewFonts[I] + FontSuffix;
    Path := ExpandConstant('{app}\fonts\') + NewFonts[I];
    if RegQueryStringValue(HKCU, FontKey, Key, Current) and (Current = Path) then begin
      RemoveFontResourceExW(Path, 0, 0);
      RegDeleteValue(HKCU, FontKey, Key);
    end;
    if RegQueryStringValue(HKCU, OwnerKey + '\Fonts', Key, Current) and (Current = Path) then
      RegDeleteValue(HKCU, OwnerKey + '\Fonts', Key);
  end;
  if AppPathWritten then UnregisterAppPath;
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

{ What GX Shell 0.3.0 and earlier created for the bundled WezTerm GX: two shortcuts, the older
  "WezTerm (gx)" shortcut it retargeted, and App Paths\wezterm-gx.exe. They are ours only while they
  point into the wezterm directory of this installation; a separately installed WezTerm GX uses the
  same names. }
function WezTermLink(Index: Integer): String;
begin
  case Index of
    0: Result := ExpandConstant('{autoprograms}\WezTerm GX.lnk');
    1: Result := ExpandConstant('{autodesktop}\WezTerm GX.lnk');
  else Result := ExpandConstant('{userprograms}\WezTerm (gx).lnk');
  end;
end;

function InOldWezTerm(const Path: String): Boolean;
begin
  Result := Pos(NormalizeEntry(ExpandConstant('{app}\wezterm')) + '\', NormalizeEntry(Path)) = 1;
end;

function LinkTarget(const Path: String): String;
var Shell, Shortcut: Variant;
begin
  Result := '';
  try
    Shell := CreateOleObject('WScript.Shell');
    Shortcut := Shell.CreateShortcut(Path);
    Result := Shortcut.TargetPath;
  except
    Log('Cannot read shortcut ' + Path + ': ' + GetExceptionMessage);
  end;
end;

procedure RemoveOldWezTerm;
var I: Integer; Path, Current: String;
begin
  for I := 0 to WezTermLinkCount - 1 do begin
    Path := WezTermLink(I);
    if FileExists(Path) and InOldWezTerm(LinkTarget(Path)) then begin
      if DeleteFile(Path) then Log('Removed the WezTerm GX shortcut of an earlier GX Shell: ' + Path)
      else Log('Could not remove ' + Path);
    end;
  end;
  if RegQueryStringValue(HKCU, AppPathsKey + 'wezterm-gx.exe', '', Current) and InOldWezTerm(Current) then
    RegDeleteKeyIncludingSubkeys(HKCU, AppPathsKey + 'wezterm-gx.exe');
end;

{ The uninstall log of an upgraded 0.3.0 installation still deletes its WezTerm GX shortcuts and
  App Paths\wezterm-gx.exe. Keep what a separately installed WezTerm GX created since then. }
procedure KeepForeignWezTerm;
var I: Integer; Path, Target: String;
begin
  for I := 0 to 1 do begin
    KeptLinkFound[I] := False;
    Path := WezTermLink(I);
    if FileExists(Path) then begin
      Target := LinkTarget(Path);
      if not InOldWezTerm(Target) then KeptLinkFound[I] := LoadStringFromFile(Path, KeptLinks[I]);
    end;
  end;
  KeptAppPath := False;
  if RegQueryStringValue(HKCU, AppPathsKey + 'wezterm-gx.exe', '', Target) then
    if not InOldWezTerm(Target) then
      if RegGetValueNames(HKCU, AppPathsKey + 'wezterm-gx.exe', KeptAppPathNames) then begin
        SetArrayLength(KeptAppPathValues, GetArrayLength(KeptAppPathNames));
        for I := 0 to GetArrayLength(KeptAppPathNames) - 1 do
          RegQueryStringValue(HKCU, AppPathsKey + 'wezterm-gx.exe', KeptAppPathNames[I], KeptAppPathValues[I]);
        KeptAppPath := True;
      end;
end;

procedure RestoreForeignWezTerm;
var I: Integer;
begin
  for I := 0 to 1 do
    if KeptLinkFound[I] and not FileExists(WezTermLink(I)) then begin
      SaveStringToFile(WezTermLink(I), KeptLinks[I], False);
      Log('Restored the shortcut of a separately installed WezTerm GX: ' + WezTermLink(I));
    end;
  if KeptAppPath and not RegKeyExists(HKCU, AppPathsKey + 'wezterm-gx.exe') then
    for I := 0 to GetArrayLength(KeptAppPathNames) - 1 do
      RegWriteStringValue(HKCU, AppPathsKey + 'wezterm-gx.exe', KeptAppPathNames[I], KeptAppPathValues[I]);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Failure: String;
begin
  if CurStep = ssInstall then
    RemoveUnshippedFonts;
  if CurStep = ssPostInstall then begin
    try
      AddOwnedPath;
      Fonts(True);
      RegisterAppPath;
    except
      Failure := GetExceptionMessage;
      RollbackRegistration;
      RaiseException(Failure);
    end;
    RemoveOldWezTerm;
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
    KeepForeignWezTerm;
    RemoveOwnedPath;
    Fonts(False);
    UnregisterAppPath;
    RegDeleteValue(HKCU, OwnerKey, 'InstallDir');
    RegDeleteKeyIfEmpty(HKCU, OwnerKey + '\Fonts');
    RegDeleteKeyIfEmpty(HKCU, OwnerKey);
  end;
  if CurUninstallStep = usPostUninstall then
    RestoreForeignWezTerm;
end;
