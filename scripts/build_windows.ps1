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
  --collect-all libusb_package `
  --icon "$RootDir\assets\serial.ico" `
  "$RootDir\main.py"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller no pudo crear SerialMonitor.exe."
}

$selfTestReport = Join-Path $RootDir "dist\windows-self-test.json"
$executablePath = Join-Path $RootDir "dist\SerialMonitor.exe"
# SerialMonitor.exe uses the Windows GUI subsystem (--windowed). PowerShell
# does not reliably wait for GUI executables invoked with ``&``, so the report
# could be copied before the self-test had written it. Start-Process makes the
# build wait and gives us the executable's actual exit code.
$selfTestProcess = Start-Process `
  -FilePath $executablePath `
  -ArgumentList @("--self-test", $selfTestReport) `
  -Wait `
  -PassThru
if ($selfTestProcess.ExitCode -ne 0) {
    if (Test-Path $selfTestReport) {
        Get-Content $selfTestReport
    }
    throw "El ejecutable Windows no pasó la autoprueba de dependencias."
}
if (-not (Test-Path $selfTestReport)) {
    throw "La autoprueba terminó sin generar el reporte: $selfTestReport"
}

New-Item -Path "$RootDir\dist\windows" -ItemType Directory -Force | Out-Null
Copy-Item "$RootDir\dist\SerialMonitor.exe" "$RootDir\dist\windows\SerialMonitor.exe" -Force
Copy-Item "$RootDir\config.example.json" "$RootDir\dist\windows\config.json" -Force
Copy-Item "$RootDir\assets\serial.ico" "$RootDir\dist\windows\serial.ico" -Force
Copy-Item "$RootDir\docs\WINDOWS.md" "$RootDir\dist\windows\LEEME-WINDOWS.md" -Force
Copy-Item $selfTestReport "$RootDir\dist\windows\runtime-self-test.json" -Force

Write-Host "Build Windows listo en: $RootDir\dist\windows"
