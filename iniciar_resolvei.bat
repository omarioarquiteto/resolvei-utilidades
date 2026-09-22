@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente Python do Resolvei...
  py -3.11 -m venv .venv
  if errorlevel 1 (
    echo Nao foi possivel criar o ambiente. Instale Python 3.11+ e tente novamente.
    pause
    exit /b 1
  )
)
echo Instalando/atualizando dependencias...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo Falha ao instalar dependencias.
  pause
  exit /b 1
)
echo.
echo Resolvei em: http://127.0.0.1:8080
start "" http://127.0.0.1:8080
.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8080
pause
