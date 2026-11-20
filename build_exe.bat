@echo off
REM Builds dist\ShippingLabelSorter\ShippingLabelSorter.exe
REM Folder build (--onedir) on purpose: a single-file exe unpacks itself on every launch and starts
REM several seconds slower. Zip the whole dist\ShippingLabelSorter folder to move it to another PC.
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    python -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat || goto :fail
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || goto :fail

pyinstaller --noconfirm --clean --onedir --windowed --noupx ^
  --name ShippingLabelSorter ^
  --icon assets\app.ico ^
  --add-data "assets;assets" ^
  --hidden-import fitz --hidden-import pymupdf --hidden-import pytesseract ^
  --exclude-module tkinter --exclude-module unittest --exclude-module pytest ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module PySide6.Qt3DCore ^
  main.py || goto :fail

echo.
echo Done: dist\ShippingLabelSorter\ShippingLabelSorter.exe
exit /b 0

:fail
echo.
echo Build failed - see the messages above.
exit /b 1
