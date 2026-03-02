@echo off
setlocal enabledelayedexpansion

set ROOT_DIR=%~dp0\..
pushd %ROOT_DIR%

if "%PYTHON_BIN%"=="" set PYTHON_BIN=%ROOT_DIR%\.venv\Scripts\python.exe
if not exist "%PYTHON_BIN%" (
  set PYTHON_BIN=%ROOT_DIR%\GuisSerial\Scripts\python.exe
)

if not exist "%PYTHON_BIN%" (
  set PYTHON_BIN=%ROOT_DIR%\GuisSerial\bin\python.exe
)

if not exist "%PYTHON_BIN%" (
  echo No se encontro Python del entorno virtual.
  echo Define PYTHON_BIN o activa tu entorno virtual y vuelve a intentar.
  exit /b 1
)

"%PYTHON_BIN%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name SerialMonitor ^
  --icon "%ROOT_DIR%\assets\serial.ico" ^
  "%ROOT_DIR%\main.py"

if not exist "%ROOT_DIR%\dist\windows" mkdir "%ROOT_DIR%\dist\windows"
copy /Y "%ROOT_DIR%\dist\SerialMonitor.exe" "%ROOT_DIR%\dist\windows\SerialMonitor.exe" >nul
copy /Y "%ROOT_DIR%\config.json" "%ROOT_DIR%\dist\windows\config.json" >nul
copy /Y "%ROOT_DIR%\assets\serial.ico" "%ROOT_DIR%\dist\windows\serial.ico" >nul

echo Build Windows listo en: %ROOT_DIR%\dist\windows
popd
