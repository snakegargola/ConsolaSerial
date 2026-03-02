$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
Set-Location $RootDir

$pythonBin = $env:PYTHON_BIN
if ([string]::IsNullOrWhiteSpace($pythonBin)) {
    $pythonBin = Join-Path $RootDir ".venv\Scripts\python.exe"
}
if (-not (Test-Path $pythonBin)) {
    $pythonBin = Join-Path $RootDir "GuisSerial\Scripts\python.exe"
}
if (-not (Test-Path $pythonBin)) {
    $pythonBin = Join-Path $RootDir "GuisSerial\bin\python.exe"
}
if (-not (Test-Path $pythonBin)) {
    throw "No se encontró Python del entorno virtual. Define PYTHON_BIN o activa tu entorno virtual."
}

& $pythonBin -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name SerialMonitor `
  --icon "$RootDir\assets\serial.ico" `
  "$RootDir\main.py"

New-Item -Path "$RootDir\dist\windows" -ItemType Directory -Force | Out-Null
Copy-Item "$RootDir\dist\SerialMonitor.exe" "$RootDir\dist\windows\SerialMonitor.exe" -Force
Copy-Item "$RootDir\config.json" "$RootDir\dist\windows\config.json" -Force
Copy-Item "$RootDir\assets\serial.ico" "$RootDir\dist\windows\serial.ico" -Force

Write-Host "Build Windows listo en: $RootDir\dist\windows"
