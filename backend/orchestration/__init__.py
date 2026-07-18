"""Orquestração de turnos de chat — lógica extraída do controller WebSocket.

Módulos:
- artifacts: detecção e persistência de artifacts (compartilhado com Fusion)
- persist_turn: criação de conversa, persistência de mensagens, web search, indexing
- handle_attachments: carregamento de histórico, injeção de docs, vision relay
- build_context: memória/perfil, project RAG, assembly do system prompt
- resolve_request: cache lookup, streaming LLM com failover cascade
"""
