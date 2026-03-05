@echo off
title Xiangqi Robot VIP
color 0A

echo.
echo  *** XIANGQI ROBOT VIP - Khoi dong he thong... ***
echo.

REM Di den thu muc chua file bat nay (thu muc VIP)
cd /d "%~dp0"

REM Duong dan Python trong venv
set "PYTHON=%~dp0..\venv\Scripts\python.exe"

REM Kiem tra Python
if not exist "%PYTHON%" (
    echo [LOI] Khong tim thay Python venv tai:
    echo       %PYTHON%
    echo.
    echo  Hay chac chan thu muc venv ton tai.
    pause
    exit /b 1
)

REM Kiem tra main_VIP.py
if not exist "%~dp0main_VIP.py" (
    echo [LOI] Khong tim thay main_VIP.py!
    pause
    exit /b 1
)

REM Kiem tra Pikafish
if not exist "%~dp0..\pikafish\pikafish-avx2.exe" (
    echo [CANH BAO] Khong tim thay pikafish-avx2.exe!
    echo  Tai ve tai: https://github.com/official-pikafish/Pikafish/releases
    echo  Dat vao thu muc: ..\pikafish\
    echo.
    echo  Nhan ENTER de tiep tuc...
    pause > nul
)

echo  [OK] Dang khoi dong main_VIP.py...
echo  [OK] De thoat: dong cua so hoac bam Q tren cua so camera.
echo.

REM Chay chuong trinh chinh
"%PYTHON%" main_VIP.py

REM Hien thi khi thoat
echo.
echo  *** Chuong trinh da ket thuc. ***
pause
