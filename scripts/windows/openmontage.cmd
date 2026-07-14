@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "OM_HOME=%OPENMONTAGE_HOME%"
if not defined OM_HOME set "OM_HOME=D:\SoftDocument\CodexProject\OpenMontage"
set "OM_PY=%OM_HOME%\.venv\Scripts\python.exe"
if not exist "%OM_PY%" (
  >&2 echo OpenMontage runtime missing: "%OM_PY%"
  >&2 echo Run scripts\windows\install-openmontage-global.ps1 from the central repository.
  exit /b 2
)
set "PYTHONUTF8=1"
pushd "%OM_HOME%" >nul || exit /b 2
"%OM_PY%" "%OM_HOME%\scripts\openmontage_global_cli.py" %*
set "OM_RC=%ERRORLEVEL%"
popd >nul
exit /b %OM_RC%
