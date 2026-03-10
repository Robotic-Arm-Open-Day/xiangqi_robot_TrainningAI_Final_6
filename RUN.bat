@echo off
title Xiangqi Robot
color 0A

echo.
echo  *** XIANGQI ROBOT - Khoi dong he thong... ***
echo.

REM Di den thu muc chua file bat nay
cd /d "%~dp0"

REM Duong dan Python. Dung 'py' de qua mat he thong App Execution Aliases cua Windows
set "PYTHON=py"

REM Kiem tra main.py
if not exist "%~dp0main.py" (
    echo [LOI] Khong tim thay main.py!
    pause
    exit /b 1
)

REM Kiem tra Pikafish
if not exist "%~dp0pikafish\Windows\pikafish-avx2.exe" (
    echo [CANH BAO] Khong tim thay pikafish-avx2.exe!
    echo  - He thong se tu dong su dung Cloud Engine API thay the.
    echo  - Neu muon choi Offline, hay tai ve tu:
    echo    https://github.com/official-pikafish/Pikafish/releases
    echo.
)

echo  [OK] Dang khoi dong main.py...
echo  [OK] De thoat: dong cua so hoac bam Q tren cua so camera.
echo.

REM Chay chuong trinh chinh
"%PYTHON%" main.py

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
