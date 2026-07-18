#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  NexusLocal — Script de Deploy / Atualização em Produção
#  Uso: bash scripts/deploy.sh
#  Requisitos: git, docker, docker-compose
# ═══════════════════════════════════════════════════════════════

set -e

# ── Cores ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Helpers ──────────────────────────────────────────────────
info()    { echo -e "${CYAN}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERRO]${NC}  $1"; exit 1; }

# ── Navegar para a raiz do projeto ───────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║     NexusLocal — Deploy / Atualização    ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Verificar pré-requisitos ──────────────────────────────
info "Verificando pré-requisitos..."
command -v git    >/dev/null 2>&1 || error "git não encontrado. Instale com: apt install git"
command -v docker >/dev/null 2>&1 || error "docker não encontrado. Instale em: https://docs.docker.com/get-docker/"
command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 || \
  error "docker compose não encontrado. Atualize o Docker para versão recente."
success "Pré-requisitos OK."

# ── 2. Verificar arquivo .env ────────────────────────────────
info "Verificando arquivo .env..."
if [ ! -f ".env" ]; then
  warn ".env não encontrado! Copiando .env.example como base..."
  cp .env.example .env
  warn "⚠️  Edite o arquivo .env e preencha JWT_SECRET antes de continuar!"
  warn "    Use: nano .env"
  exit 1
fi

if ! grep -q "^JWT_SECRET=.\+" .env; then
  error "JWT_SECRET está vazio no .env! Gere uma chave com:\n  python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"\n  e adicione no .env."
fi
success ".env OK."

# ── 3. Pull das atualizações do GitHub ───────────────────────
info "Buscando atualizações do GitHub (branch: main)..."
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
  warn "Você está na branch '$BRANCH', não na 'main'."
  read -p "  Continuar mesmo assim? [s/N] " confirm
  [[ "$confirm" =~ ^[Ss]$ ]] || exit 0
fi

git fetch origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
  success "Já está na versão mais recente. Nenhuma atualização necessária."
  echo ""
  read -p "  Forçar rebuild dos containers mesmo assim? [s/N] " force
  [[ "$force" =~ ^[Ss]$ ]] || exit 0
else
  COMMITS=$(git log HEAD..origin/main --oneline | wc -l | tr -d ' ')
  info "Há $COMMITS novo(s) commit(s). Aplicando..."
  git pull origin main
  success "Código atualizado com sucesso."
fi

# ── 4. Rebuild e restart dos containers ─────────────────────
info "Reconstruindo containers Docker (sem derrubar o banco de dados)..."
docker compose build --no-cache backend frontend
success "Build concluído."

info "Reiniciando serviços..."
docker compose up -d --force-recreate backend frontend
success "Containers atualizados e em execução."

# ── 5. Limpeza de imagens antigas ───────────────────────────
info "Limpando imagens Docker antigas (dangling)..."
docker image prune -f >/dev/null 2>&1
success "Limpeza concluída."

# ── 6. Status final ─────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║           ✅ Deploy concluído!           ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
docker compose ps
echo ""
info "Logs em tempo real: docker compose logs -f"
info "Para parar tudo:    docker compose down"
echo ""
