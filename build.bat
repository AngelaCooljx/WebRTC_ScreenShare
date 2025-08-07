@echo off
echo Installing PyInstaller...
pip install pyinstaller

echo Building WebRTC ScreenShare...
pyinstaller --onefile --windowed --icon=icon.ico --name="WebRTC_ScreenShare" --add-data="icon.ico;." --optimize=2 --strip --exclude-module=tkinter.test --exclude-module=test --exclude-module=unittest --exclude-module=pydoc --exclude-module=doctest --exclude-module=difflib main.py

echo Build completed! Executable file is in dist directory
echo Filename: WebRTC_ScreenShare.exe
pause