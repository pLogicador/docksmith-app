from typing import Literal

from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    url: str
    collection_name: str
    session_id: str | None = None
    max_depth: int = Field(default=1, ge=0, le=3)
    concurrency: int = Field(default=5, ge=1, le=20)


class ResourceEstimate(BaseModel):
    """Estimativa de RAM pra indexar a coleção — puramente informativa, não
    persiste nada. Ver api/resource_estimate.py."""

    document_count: int
    total_chars: int
    total_mb: float
    estimated_chunks: int
    estimated_indexing_mb: float
    current_process_mb: float
    available_memory_mb: float
    status: Literal["ok", "atencao", "muito_grande", "bloqueado"]


class ScrapeResponse(BaseModel):
    session_id: str
    collection_name: str
    document_count: int
    preview: list[str]
    resource_estimate: ResourceEstimate


class SourceExcerpt(BaseModel):
    index: int
    excerpt: str


class ChatRequest(BaseModel):
    session_id: str
    collection_name: str
    question: str
    provider: str = "groq"
    model: str | None = None
    api_key: str | None = None
    depth: str = "equilibrada"
    # Necessário só quando a estimativa de recursos da coleção está no nível
    # "bloqueado" — usuário confirma explicitamente que quer indexar mesmo
    # assim (ver api/resource_estimate.py).
    confirm_large_collection: bool = False


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceExcerpt]
    collection_name: str
    provider: str
    model: str


class TestConnectionRequest(BaseModel):
    provider: str
    model: str | None = None
    api_key: str | None = None


class TestConnectionResponse(BaseModel):
    ok: bool
    error: str | None = None


class SessionCollectionInfo(BaseModel):
    name: str
    document_count: int


class SessionStatusResponse(BaseModel):
    session_id: str
    collections: list[SessionCollectionInfo]
