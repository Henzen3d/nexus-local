"""Testes para o sanitizador de segredos e credenciais (PII Redactor)."""

from backend.memory_sanitize import sanitize_memory_text


def test_sanitize_plain_text():
    text = "Gosta de programar em Python e FastAPI aos fins de semana."
    clean, drop = sanitize_memory_text(text)
    assert drop is False
    assert clean == text


def test_sanitize_openai_key():
    text = "Minha chave é sk-proj-1234567890abcdef1234567890 para testes."
    clean, drop = sanitize_memory_text(text)
    assert drop is False
    assert "[REDACTED_CREDENTIAL]" in clean
    assert "sk-proj-" not in clean


def test_sanitize_pure_credential_dropped():
    text = "sk-ant-api03-abcdef1234567890abcdef123456"
    clean, drop = sanitize_memory_text(text)
    assert drop is True
    assert clean == ""


def test_sanitize_database_url_password():
    text = "Conecta no banco postgres://admin:SuperSecretPass123@db.prod.internal:5432/main"
    clean, drop = sanitize_memory_text(text)
    assert drop is False
    assert "SuperSecretPass123" not in clean
    assert "[REDACTED_CREDENTIAL]" in clean


def test_sanitize_github_token():
    text = "Utiliza o token ghp_123456789012345678901234567890123456 para deploys."
    clean, drop = sanitize_memory_text(text)
    assert drop is False
    assert "ghp_" not in clean
    assert "[REDACTED_CREDENTIAL]" in clean
