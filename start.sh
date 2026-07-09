#!/bin/bash
# NexusLocal — script de inicialização

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🌀 NexusLocal — Iniciando..."

# ── Backend ───────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "📦 Criando ambiente virtual Python..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "📦 Instalando dependências Python..."
pip install -q -r requirements.txt

echo "🚀 Iniciando backend (porta 8000)..."
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# ── Frontend ───────────────────────────────────────────
if [ ! -d "frontend/node_modules" ]; then
  echo "📦 Instalando dependências Node..."
  cd frontend && npm install && cd ..
fi

echo "⚡ Iniciando frontend Vite (porta 5173)..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ NexusLocal rodando!"
echo "   → Interface:  http://localhost:5173"
echo "   → API:        http://localhost:8000"
echo "   → Docs API:   http://localhost:8000/docs"
echo ""
echo "   Pressione Ctrl+C para parar tudo."

# Cleanup on exit
cleanup() {
  echo ""
  echo "🛑 Encerrando NexusLocal..."
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM

wait
