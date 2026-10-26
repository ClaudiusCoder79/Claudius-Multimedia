@echo off
cd /d "%~dp0"
for %%f in (claudius_multimedia.py cm_core.py cm_icons.py cm_theme.py cm_tags.py cm_parse.py cm_online.py cm_library.py cm_player.py cm_widgets.py cm_dialogs.py cm_main.py cm_smart.py cm_duplicates.py splash.png claudius.ico FREEWARE.txt LICENSE version_info.txt lang\en.json lang\pl.json lang\de.json lang\fr.json lang\it.json lang\es.json) do if not exist "%%f" (echo MISSING FILE: %%f - copy ALL files of the program folder, including the lang folder & pause & exit /b 1)
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean --noconsole --onedir --name "Claudius Multimedia" --icon claudius.ico --version-file version_info.txt --splash splash.png --add-data "lang;lang" --add-data "splash.png;." --add-data "FREEWARE.txt;." --add-data "claudius.ico;." --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtPdf claudius_multimedia.py
echo.
echo Done. Your program is in the "dist" folder: dist\Claudius Multimedia\Claudius Multimedia.exe
pause
