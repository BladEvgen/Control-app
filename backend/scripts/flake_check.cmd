@echo off

setlocal
set "ROOT=%~dp0..\.."
set "RUFF=%ROOT%\venv\Scripts\ruff.exe"

if not exist "%RUFF%" (
    echo Не найден %RUFF%. Установите зависимости: pip install -r backend\requirements\base-win.txt 1>&2
    exit /b 1
)

if "%~1"=="--fix" (
    "%RUFF%" check "%ROOT%" --fix
    "%ROOT%\venv\Scripts\isort.exe" --profile black "%ROOT%\backend"
    "%ROOT%\venv\Scripts\black.exe" "%ROOT%\backend"
) else if "%~1"=="--complexity" (
    "%RUFF%" check "%ROOT%\backend" --select C901 --statistics
) else (
    "%RUFF%" check "%ROOT%"
)

endlocal
