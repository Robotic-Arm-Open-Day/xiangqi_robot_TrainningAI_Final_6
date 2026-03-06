@echo off
title Xiangqi Robot VIP
color 0A

echo.
echo  *** XIANGQI ROBOT VIP - Khoi dong he thong... ***
echo.

REM Di den thu muc chua file bat nay (thu muc VIP)
cd /d "%~dp0"

REM Duong dan Python. Dung 'py' de qua mat he thong App Execution Aliases cua Windows
set "PYTHON=py"

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

REM Chay chuong trinh chinh (Yeu cau quay ve thu muc go'c de import dung config.py)
cd /d "%~dp0.."
"%PYTHON%" VIP\main_VIP.py

REM Dung man hinh lai de xem loi (neu co) truoc khi auto-thoat
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] Chuong trinh bi crash dot ngot! Kiem tra dong loi o tren.
    pause
)

REM Hien thi khi thoat
echo.
echo  *** Chuong trinh da ket thuc. ***
pause
