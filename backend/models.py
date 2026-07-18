from pydantic import BaseModel, ConfigDict
from typing import Optional, List


class MessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    conversation_id: Optional[str] = None
    message: str
    model_id: str
    provider_id: str
    system_prompt: Optional[str] = None


class ConversationCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    title: Optional[str] = "Nova conversa"
    model_id: Optional[str] = None
    provider_id: Optional[str] = None
    project_id: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    project_tag: Optional[str] = None
    project_id: Optional[str] = None


class ProviderUpdate(BaseModel):
    api_key: Optional[str] = None
    enabled: Optional[bool] = None
    base_url: Optional[str] = None
    # Compartilhar chave de admin deste provedor com outros usuários
    share_admin_key: Optional[bool] = None


class ModelToggle(BaseModel):
    enabled: bool


class ModelUpdate(BaseModel):
    enabled: Optional[bool] = None
    context_length: Optional[int] = None


class ArtifactCreate(BaseModel):
    id: Optional[str] = None
    conv_id: str
    msg_id: Optional[str] = None
    type: str
    title: str
    content: str
    version: Optional[int] = 1
    artifact_group_id: Optional[str] = None


class FreeRegistryConfigUpdate(BaseModel):
    threshold: Optional[int] = None
    hide_unconfirmed: Optional[bool] = None

