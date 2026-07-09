@echo off
title NexusLocal

echo 🌀 NexusLocal - Iniciando...

:: Backend
if not exist ".venv" (
    echo 📦 Criando ambiente virtual Python...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo 📦 Instalando dependencias Python...
pip install -q -r requirements.txt

echo 🚀 Iniciando backend (porta 8000)...
start "NexusLocal Backend" cmd /k "call .venv\Scripts\activate.bat && uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

:: Frontend
if not exist "frontend\node_modules" (
    echo 📦 Instalando dependencias Node...
    cd frontend && npm install && cd ..
)

echo ⚡ Iniciando frontend Vite (porta 5173)...
start "NexusLocal Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ✅ NexusLocal iniciado!
echo    Interface:  http://localhost:5173
echo    API:        http://localhost:8000
echo.
pause
