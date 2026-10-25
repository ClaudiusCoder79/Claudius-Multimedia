; Claudius Multimedia installer - build with Inno Setup 6.3 or newer (free, jrsoftware.org)
; Needs the folder dist\Claudius Multimedia (run build_exe.bat first) and claudius.ico / README.txt next to this file.
;
; Software guidelines covered here:
;   - install folder C:\Program Files (x86)\Claudius Multimedia
;   - Start Menu folder "Claudius Multimedia" with the program, Uninstall, Freeware notice and Readme
;   - uninstaller (also listed in Windows Settings > Apps > Installed apps)
;   - installer in English, Polish, German, French, Italian and Spanish; the chosen language is passed to the program

#define MyAppName "Claudius Multimedia"
#define MyAppVersion "1.0.0"
#define MyAppExe "Claudius Multimedia.exe"
#define MyAppURL "https://github.com/ClaudiusCoder79/Claudius-Multimedia"
#if FileExists("dist\Claudius Multimedia\Claudius Multimedia.exe")
  #define ExeSource "dist\Claudius Multimedia"
#elif FileExists("Claudius Multimedia\Claudius Multimedia.exe")
  #define ExeSource "Claudius Multimedia"
#else
  #error The program folder was not found. Run build_exe.bat first (it makes dist\Claudius Multimedia) and compile again.
#endif

[Setup]
AppId={{4F7C2A91-6B3E-4D58-9A1F-C1A0D5E8B276}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Michal Czapla & Claude AI
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
AppCopyright=Copyright (C) 2026 Michal Czapla
VersionInfoVersion={#MyAppVersion}.0
VersionInfoDescription={#MyAppName} Setup
; C:\Program Files (x86)\Claudius Multimedia - as the software guidelines ask ({commonpf32} is that folder on 64-bit Windows)
DefaultDirName={commonpf32}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
AllowNoIcons=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExe}
PrivilegesRequired=admin
OutputDir=installer
OutputBaseFilename=Claudius-Multimedia-Setup-{#MyAppVersion}
LicenseFile=FREEWARE.txt
SetupIconFile=claudius.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes
ShowLanguageDialog=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
english.Assoc=File integration:
english.AssocAudio=Open music files with Claudius Multimedia (MP3, FLAC, M4A, OGG, Opus, WAV, WMA, AIFF, APE)
english.AssocVideo=Open video files with Claudius Multimedia (MP4, MKV, AVI, MOV, WMV, WebM, MPG, TS)
english.AssocList=Open playlists (M3U, M3U8, PLS)
english.Freeware=Freeware notice
english.Readme=Read me
english.DefaultApps=Open Windows Default apps to choose Claudius Multimedia
polish.Assoc=Integracja z plikami:
polish.AssocAudio=Otwieraj pliki muzyczne w Claudius Multimedia (MP3, FLAC, M4A, OGG, Opus, WAV, WMA, AIFF, APE)
polish.AssocVideo=Otwieraj pliki wideo w Claudius Multimedia (MP4, MKV, AVI, MOV, WMV, WebM, MPG, TS)
polish.AssocList=Otwieraj playlisty (M3U, M3U8, PLS)
polish.Freeware=Informacja freeware
polish.Readme=Przeczytaj
polish.DefaultApps=Otwórz Aplikacje domyślne Windows, aby wybrać Claudius Multimedia
german.Assoc=Dateizuordnung:
german.AssocAudio=Musikdateien mit Claudius Multimedia öffnen (MP3, FLAC, M4A, OGG, Opus, WAV, WMA, AIFF, APE)
german.AssocVideo=Videodateien mit Claudius Multimedia öffnen (MP4, MKV, AVI, MOV, WMV, WebM, MPG, TS)
german.AssocList=Playlists öffnen (M3U, M3U8, PLS)
german.Freeware=Freeware-Hinweis
german.Readme=Liesmich
german.DefaultApps=Windows-Standard-Apps öffnen, um Claudius Multimedia zu wählen
french.Assoc=Association de fichiers :
french.AssocAudio=Ouvrir la musique avec Claudius Multimedia (MP3, FLAC, M4A, OGG, Opus, WAV, WMA, AIFF, APE)
french.AssocVideo=Ouvrir les vidéos avec Claudius Multimedia (MP4, MKV, AVI, MOV, WMV, WebM, MPG, TS)
french.AssocList=Ouvrir les playlists (M3U, M3U8, PLS)
french.Freeware=Avis gratuiciel
french.Readme=Lisez-moi
french.DefaultApps=Ouvrir Applications par défaut de Windows pour choisir Claudius Multimedia
italian.Assoc=Associazione file:
italian.AssocAudio=Apri i file musicali con Claudius Multimedia (MP3, FLAC, M4A, OGG, Opus, WAV, WMA, AIFF, APE)
italian.AssocVideo=Apri i file video con Claudius Multimedia (MP4, MKV, AVI, MOV, WMV, WebM, MPG, TS)
italian.AssocList=Apri le playlist (M3U, M3U8, PLS)
italian.Freeware=Nota freeware
italian.Readme=Leggimi
italian.DefaultApps=Apri App predefinite di Windows per scegliere Claudius Multimedia
spanish.Assoc=Asociación de archivos:
spanish.AssocAudio=Abrir música con Claudius Multimedia (MP3, FLAC, M4A, OGG, Opus, WAV, WMA, AIFF, APE)
spanish.AssocVideo=Abrir vídeos con Claudius Multimedia (MP4, MKV, AVI, MOV, WMV, WebM, MPG, TS)
spanish.AssocList=Abrir listas de reproducción (M3U, M3U8, PLS)
spanish.Freeware=Aviso freeware
spanish.Readme=Léame
spanish.DefaultApps=Abrir Aplicaciones predeterminadas de Windows para elegir Claudius Multimedia

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assocaudio"; Description: "{cm:AssocAudio}"; GroupDescription: "{cm:Assoc}"
Name: "assocvideo"; Description: "{cm:AssocVideo}"; GroupDescription: "{cm:Assoc}"
Name: "assoclist"; Description: "{cm:AssocList}"; GroupDescription: "{cm:Assoc}"

[Files]
Source: "{#ExeSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "claudius.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "FREEWARE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
; Start Menu folder: Start > All apps > Claudius Multimedia
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\claudius.ico"; Comment: "Music & video player"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{group}\{cm:Freeware}"; Filename: "{app}\FREEWARE.txt"
Name: "{group}\{cm:Readme}"; Filename: "{app}\README.txt"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\claudius.ico"; Tasks: desktopicon

[Registry]
; the program's own file types ("Open with" + Default apps). Windows keeps the user's choice of default player,
; so after setup the user confirms Claudius Multimedia in Settings > Apps > Default apps (the last page offers to open it).
Root: HKA; Subkey: "Software\Classes\Claudius.Audio"; ValueType: string; ValueName: ""; ValueData: "Audio file (Claudius Multimedia)"; Flags: uninsdeletekey; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\Claudius.Audio\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\claudius.ico"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\Claudius.Audio\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\Claudius.Video"; ValueType: string; ValueName: ""; ValueData: "Video file (Claudius Multimedia)"; Flags: uninsdeletekey; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\Claudius.Video\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\claudius.ico"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\Claudius.Video\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\Claudius.Playlist"; ValueType: string; ValueName: ""; ValueData: "Playlist (Claudius Multimedia)"; Flags: uninsdeletekey; Tasks: assoclist
Root: HKA; Subkey: "Software\Classes\Claudius.Playlist\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\claudius.ico"; Tasks: assoclist
Root: HKA; Subkey: "Software\Classes\Claudius.Playlist\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: assoclist
; folders: right-click > "Play with Claudius Multimedia"
Root: HKA; Subkey: "Software\Classes\Directory\shell\ClaudiusMultimedia"; ValueType: string; ValueName: ""; ValueData: "Play with Claudius Multimedia"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Directory\shell\ClaudiusMultimedia"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\claudius.ico"
Root: HKA; Subkey: "Software\Classes\Directory\shell\ClaudiusMultimedia\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""
; "Open with" list and Default apps entry for every extension
Root: HKA; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mp3"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".flac"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.m4a\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m4a"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.aac\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aac"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.ogg\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ogg"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.oga\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".oga"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.opus\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".opus"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wav"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.wma\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wma"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.aiff\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aiff"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.aif\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".aif"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.ape\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ape"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.wv\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wv"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.mka\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mka"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.m4b\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Audio"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocaudio
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m4b"; ValueData: "Claudius.Audio"; Tasks: assocaudio
Root: HKA; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mp4"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.mkv\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mkv"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.avi\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".avi"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.mov\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mov"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.wmv\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".wmv"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.webm\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".webm"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.m4v\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m4v"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.mpg\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mpg"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.mpeg\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mpeg"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.ts\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ts"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.m2ts\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m2ts"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.mts\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".mts"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.flv\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".flv"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.3gp\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".3gp"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.ogv\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Video"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocvideo
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ogv"; ValueData: "Claudius.Video"; Tasks: assocvideo
Root: HKA; Subkey: "Software\Classes\.m3u\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Playlist"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoclist
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m3u"; ValueData: "Claudius.Playlist"; Tasks: assoclist
Root: HKA; Subkey: "Software\Classes\.m3u8\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Playlist"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoclist
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".m3u8"; ValueData: "Claudius.Playlist"; Tasks: assoclist
Root: HKA; Subkey: "Software\Classes\.pls\OpenWithProgids"; ValueType: string; ValueName: "Claudius.Playlist"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoclist
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pls"; ValueData: "Claudius.Playlist"; Tasks: assoclist
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Music and video player"
Root: HKA; Subkey: "Software\ClaudiusMultimedia\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\claudius.ico"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "ClaudiusMultimedia"; ValueData: "Software\ClaudiusMultimedia\Capabilities"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExe}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExe}"; Flags: uninsdeletekey

[Run]
Filename: "ms-settings:defaultapps?registeredAppMachine=ClaudiusMultimedia"; Description: "{cm:DefaultApps}"; Flags: shellexec nowait postinstall skipifsilent unchecked; Tasks: assocaudio assocvideo
Filename: "{app}\{#MyAppExe}"; Parameters: "--lang={code:LangCode}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Code]
// Hand the language chosen in setup to the program on its first start.
function LangCode(Param: String): String;
begin
  case ActiveLanguage() of
    'polish': Result := 'pl';
    'german': Result := 'de';
    'french': Result := 'fr';
    'italian': Result := 'it';
    'spanish': Result := 'es';
  else
    Result := 'en';
  end;
end;

// Ask whether to keep the library, playlists and settings (in %APPDATA%\Claudius Multimedia).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\Claudius Multimedia');
    if DirExists(DataDir) and not UninstallSilent() then
      if MsgBox('Also delete your Claudius Multimedia library, playlists and settings?' + #13#10 +
                '(Your music and video files are never deleted.)', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
