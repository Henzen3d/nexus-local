"""Lock global para operações estruturais de memória.

Impede colisões entre:
- Extração ociosa de fatos (run_memory_idle_extraction_job)
- Consolidação do sonho (run_dream_consolidation_job)
- Disparos manuais via API (dream_run_now, dream_preview)
"""

import asyncio

# Lock global do pipeline de memória (impede colisões entre extração idle e consolidação dream)
memory_pipeline_lock = asyncio.Lock()
