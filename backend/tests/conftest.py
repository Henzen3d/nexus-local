"""Configuração global dos testes.

Regra do projeto (AGENTS.md): NUNCA rodar testes contra o banco real
``backend/nexuslocal.db``. Este conftest é importado pelo pytest antes de
qualquer módulo de teste, então conseguimos apontar ``DB_PATH`` para um
arquivo temporário ANTES de ``backend.database`` ser importado.

Também garante ``JWT_SECRET`` (``backend.auth`` recusa iniciar sem ele).
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="nexuslocal-tests-"))

os.environ.setdefault("JWT_SECRET", "test-only-secret-not-for-production-0123456789")
os.environ["DB_PATH"] = str(_TMP_ROOT / "nexuslocal-test.db")
os.environ.setdefault("ATTACHMENTS_SIGNING_SECRET", "test-only-attachment-signing-secret")

# Importa só depois de definir o ambiente acima.
from backend import database as dbmod  # noqa: E402

assert dbmod.DB_PATH == Path(os.environ["DB_PATH"]), (
    "DB_PATH não foi redirecionado para o diretório temporário — "
    "backend.database foi importado antes do conftest?"
)


@pytest.fixture(autouse=True)
def _isolated_db_path(monkeypatch):
    """Garante que cada teste veja o DB_PATH temporário mesmo se outro teste
    tiver trocado ``dbmod.DB_PATH`` e esquecido de restaurar."""
    monkeypatch.setattr(dbmod, "DB_PATH", Path(os.environ["DB_PATH"]), raising=True)
    yield


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)
