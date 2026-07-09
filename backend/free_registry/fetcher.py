import httpx

MNFST_DATA_URL = "https://github.com/mnfst/awesome-free-llm-apis/raw/refs/heads/main/data.json"

async def fetch_mnfst_registry() -> dict:
    """
    Busca o data.json do repositório awesome-free-llm-apis do mnfst no GitHub.
    """
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(MNFST_DATA_URL)
        resp.raise_for_status()
        return resp.json()

async def is_registry_stale(current_last_updated: str, db) -> bool:
    """
    Compara o lastUpdated do JSON com o que já está salvo na tabela meta.
    Retorna True se a versão local for inexistente ou diferente da recebida.
    """
    async with db.execute("SELECT value FROM meta WHERE key = 'free_registry_last_updated'") as cursor:
        row = await cursor.fetchone()
        if not row:
            return True
        return row[0] != current_last_updated
