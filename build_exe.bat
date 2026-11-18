@echo off
REM Builds dist\ShippingLabelSorter\ShippingLabelSorter.exe (windowed: no console needed any more,
REM unclear labels are now answered inside the app).
pip install pyinstaller
pyinstaller --noconfirm --onedir --windowed --name ShippingLabelSorter ^
  --hidden-import fitz --hidden-import pymupdf --hidden-import pytesseract main.py
