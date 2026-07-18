"""NexusLocal Projects module — persistent context workspaces with RAG."""

from backend.projects.context_builder import build_project_context, ProjectContextResult
from backend.projects.indexer import index_project_file, index_chat_turn, retrieve_related_chats

__all__ = [
    "build_project_context",
    "ProjectContextResult",
    "index_project_file",
    "index_chat_turn",
    "retrieve_related_chats",
]
