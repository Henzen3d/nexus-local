#!/usr/bin/env bash
# judge.sh — portão de qualidade do NexusLocal
# Nada é commitado sem verde.
#
# Ordem de execução:
#   1. pytest backend (container nexus_backend)
#   2. node tests frontend
#   3. tsc --noEmit
#   4. build Vite
#   5. streaming-paint-probe.mjs
#   6. message-actions-after-stream.mjs
#   7. Playwright smoke contra vite dev server (5173) — se disponível
#
# Saída: zero = verde, não-zero = primeira falha para o caller.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; total=0; failed_tests=""

check() {
  local name="$1"; shift
  total=$((total + 1))
  printf "${CYAN}[%d/7] %s...${NC}" "$total" "$name"
  if eval "$@" > /tmp/judge_$$.log 2>&1; then
    PASS=$((PASS + 1))
    printf " ${GREEN}✓${NC}\n"
  else
    FAIL=$((FAIL + 1))
    failed_tests="$failed_tests\n  - $name"
    printf " ${RED}✗${NC} (see /tmp/judge_$$.log)\n"
  fi
}

# 1. Backend pytest (dentro do container, PYTHONPATH correto)
check "pytest backend" \
  "docker exec nexus_backend bash -c 'cd /app && PYTHONPATH=/app/backend python -m pytest backend/tests/ -q --tb=line'"

# 2. Frontend node tests
check "frontend node tests" \
  "cd '$ROOT/frontend' && node --experimental-strip-types --test 'src/lib/*.test.ts' 'src/ui/*.test.ts' 'src/ui/lib/*.test.ts'"

# 3. TypeScript type-check
check "tsc --noEmit" \
  "cd '$ROOT/frontend' && npx tsc --noEmit"

# 4. Vite build (pode levar ~10s, timeout maior)
check "vite build" \
  "cd '$ROOT/frontend' && timeout 120 npm run build"

# 5. Streaming paint probe
check "streaming-paint-probe" \
  "cd '$ROOT/frontend' && node scripts/run-streaming-paint-probe.mjs"

# 6. Message actions after stream probe
check "message-actions-after-stream" \
  "cd '$ROOT/frontend' && node scripts/run-message-actions-after-stream.mjs"

# 7. Playwright smoke (só se vite dev server estiver rodando em 5173 E existir spec)
if lsof -iTCP:5173 -sTCP:LISTEN > /dev/null 2>&1 && [ -f "$ROOT/tests/e2e/smoke.spec.ts" ]; then
  check "playwright smoke (5173)" \
    "cd '$ROOT' && npx playwright test tests/e2e/smoke.spec.ts --timeout=30000"
elif [ -f "$ROOT/tests/e2e/smoke.spec.ts" ]; then
  printf "${CYAN}[%d/7] playwright smoke${NC} ⏭️ (5173 não respondendo)\n" "$((total + 1))"
else
  printf "${CYAN}[%d/7] playwright smoke${NC} ⏭️ (sem tests/e2e/smoke.spec.ts)\n" "$((total + 1))"
fi

echo ""
echo "─────────────────────────────────"
printf "Resultado: ${GREEN}%d passes${NC}, ${RED}%d fails${NC} de %d checks\n" "$PASS" "$FAIL" "$total"
if [ "$FAIL" -gt 0 ]; then
  echo "Falhas:"
  echo -e "$failed_tests"
  exit 1
fi
exit 0
