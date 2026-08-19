$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$VenvDir = Join-Path $RootDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Assert-CommandSucceeded([string]$Message) {
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

Set-Location $RootDir

if (-not (Test-Path $VenvPython)) {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $PyLauncher) {
        & $PyLauncher.Source -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
        Assert-CommandSucceeded "Se requiere Python 3.12 o posterior."
        & $PyLauncher.Source -3 -m venv $VenvDir
    } else {
        $Python = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $Python) {
            throw "No se encontró Python. Instala Python 3.12+ de 64 bits y vuelve a ejecutar este script."
        }
        & $Python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
        Assert-CommandSucceeded "Se requiere Python 3.12 o posterior."
        & $Python.Source -m venv $VenvDir
    }
    Assert-CommandSucceeded "No se pudo crear el entorno virtual de Windows."
}

& $VenvPython -m pip install --upgrade pip
Assert-CommandSucceeded "No se pudo actualizar pip."
& $VenvPython -m pip install -r "$RootDir\requirements.txt"
Assert-CommandSucceeded "No se pudieron instalar las dependencias de ejecución."
& $VenvPython -m pip install -r "$RootDir\requirements-build.txt"
Assert-CommandSucceeded "No se pudieron instalar las dependencias de compilación."

$env:QT_QPA_PLATFORM = "offscreen"
& $VenvPython -m unittest discover -s "$RootDir\tests"
Assert-CommandSucceeded "Las pruebas automáticas fallaron; no se generará el ejecutable."

$env:PYTHON_BIN = $VenvPython
& "$RootDir\scripts\build_windows.ps1"
Assert-CommandSucceeded "Falló la creación del paquete Windows."

Write-Host ""
Write-Host "Paquete validado: $RootDir\dist\windows"
Write-Host "Antes de usar I2C/SPI, revisa dist\windows\LEEME-WINDOWS.md"
