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
    # True só quando este upload foi aceito com `truncate=true` E de fato
    # precisou cortar algo (2026-09-10) -- sinal de transparência pro
    # frontend mostrar "processamos só as primeiras N páginas", mesmo se
    # o cliente não for o fluxo de UI que decidiu pedir o truncamento.
    truncated: bool = False


class DocumentPartInfo(BaseModel):
    """Metadado de uma parte gerada por POST /documents/upload/split
    (Fase A, 2026-09-10 -- divisão inteligente consciente de estrutura,
    "PROMPT DE EVOLUÇÃO"/"OBSERVAÇÕES FINAIS"). Reaproveita a mesma
    estimativa de recursos que uma coleção normal usaria (api/
    resource_estimate.py), sem duplicar a fórmula -- ver
    api/routers/documents.py::upload_document_split."""

    collection_name: str
    part_number: int
    unit: Literal["páginas", "seções"]
    position_start: int | None
    position_end: int | None
    chapters: list[str]
    page_count: int
    document_count: int
    estimated_chunks: int
    estimated_size_mb: float


class SplitUploadResponse(BaseModel):
    """Resposta de POST /documents/upload/split -- N coleções consultáveis
    (uma por parte), cada uma já disponível em /chat pelo próprio
    `collection_name` reportado aqui."""

    session_id: str
    base_collection_name: str
    parts: list[DocumentPartInfo]


class SourceExcerpt(BaseModel):
    index: int
    excerpt: str
    # Achado real (2026-09-02, confirmado testando um upload de PDF real
    # ponta a ponta, não só lendo código): `RAGService.ask_question_with_
    # sources` (docksmith/service/rag.py) já calculava esses 3 campos
    # desde a 1ª rodada da Fase I (metadado real de proveniência, §11/§37
    # -- "citações reais"), mas este schema nunca os declarava. Pydantic
    # descarta silenciosamente qualquer chave que `SourceExcerpt(**s)` não
    # conhece (chat.py) -- então "arquivo.pdf - página 3" nunca chegava
    # até o frontend, mesmo já estando calculado internamente. Nenhuma
    # mudança em rag.py/chat.py foi necessária, só faltavam estes 3 campos
    # aqui.
    document_index: int | None = None
    chunk_index: int | None = None
    source_label: str | None = None
    # chapter/section/page_start/page_end (2026-09-02, 3ª rodada,
    # prompt-mestre §13/§16 -- "leitura dinâmica de busca") -- mesma
    # situação já documentada acima pros 3 campos originais: `query_engine.py`
    # já calculava isso desde que foi criado, mas o schema precisa declarar
    # os campos ou o Pydantic os descarta silenciosamente antes de chegar
    # ao frontend. `None` para qualquer coleção sem estrutura conhecida
    # (raspada por URL, ou upload de antes desta rodada).
    chapter: str | None = None
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None


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
    # assim (ver api/resource_estimate.py). Também usado pra confirmar o
    # bloqueio de orçamento cumulativo de chunks por sessão (Fase E).
    confirm_large_collection: bool = False
    # Multicontexto (Fase H, 2026-09-10, "PROMPT DE EVOLUÇÃO" -- combinar
    # até 3 fontes numa pergunta só). `None`/ausente/lista vazia = modo de
    # sempre, só `collection_name` -- ZERO mudança de comportamento pra
    # quem nunca souber que este campo existe. Quando presente (1-3 nomes),
    # tem PRECEDÊNCIA sobre `collection_name` pra decidir quais coleções
    # combinar -- `collection_name` continua obrigatório no schema (nunca
    # quebra um chamador antigo), mas em modo multicontexto só serve pra
    # validação de existência adicional/logs, não decide sozinho o que é
    # carregado. Teto de 3 é validado aqui, não só sugerido.
    collection_names: list[str] | None = Field(default=None, max_length=3)


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceExcerpt]
    collection_name: str
    provider: str
    model: str
    # intent (2026-09-02, 3ª rodada, prompt-mestre §17 "classificação de
    # intenção"): qual caminho de leitura/busca respondeu esta pergunta --
    # "structural_search"/"page_search"/"lexical_search"/"compare"/
    # "semantic_synthesis" (ver docksmith/service/query_engine.py). `None`
    # só é possível se algo muito antigo/legado chamar este schema sem
    # passar por QueryEngine -- nunca deveria acontecer no caminho real de
    # /chat, mas o default evita quebrar qualquer chamador hipotético.
    intent: str | None = None
    # notice (2026-09-02, 4ª rodada): mensagem transparente pro usuário
    # quando algum refinamento opcional não pôde ser aplicado (hoje, só o
    # reranking da comparação, quando o modelo não pôde ser baixado por
    # falta de internet nesse instante -- ver docksmith/service/
    # query_engine.py::_answer_compare). `None` na esmagadora maioria das
    # respostas -- só aparece quando há algo real pra avisar, nunca
    # decoração. Frontend deve mostrar isso como um aviso discreto (a
    # resposta em si é completa), não como um erro.
    notice: str | None = None
    # was_cached (Fase E, 2026-09-10): False quando esta pergunta precisou
    # (re)indexar a coleção agora, no cache LRU por sessão (ver
    # api/index_cache.py) -- 1ª vez ou porque tinha sido evictada. `True`
    # como default é a leitura mais segura pra qualquer chamador
    # hipotético que não passe por api/routers/chat.py (que sempre
    # calcula o valor real) -- consistente com o resto dos campos novos
    # deste schema, que usam o default menos alarmante pro frontend.
    was_cached: bool = True


class TestConnectionRequest(BaseModel):
    provider: str
    model: str | None = None
    api_key: str | None = None


class TestConnectionResponse(BaseModel):
    ok: bool
    error: str | None = None


# Fase F (2026-09-10, "PROMPT DE EVOLUÇÃO"/"OBSERVAÇÕES FINAIS" --
# checkpoints de processamento observáveis, sem reinício automático em
# falha). "uploaded": extração concluída, coleção existe mas ainda não
# foi indexada. "chunking"/"extracting" não são estados separadamente
# observáveis nesta rodada -- ver nota em api/routers/documents.py e
# api/routers/chat.py sobre por quê (extração/chunking hoje rodam dentro
# de uma única chamada síncrona, sem um worker em segundo plano que
# permita a outra requisição observar o meio do caminho -- ver "Fora de
# escopo" no plano: streaming/fila fica pra uma evolução futura).
# "embedding": RAGService.load_collection rodando (chunking+embeddings+
# FAISS+BM25, hoje uma chamada atômica). "indexed"/"ready": índice
# construído e disponível pra responder perguntas. "failed": a última
# tentativa de indexação falhou -- fica visível até a próxima pergunta
# real tentar de novo (nunca reescrito sozinho, nunca escondido).
CollectionStatus = Literal["uploaded", "extracting", "chunking", "embedding", "indexed", "ready", "failed"]


class SessionCollectionInfo(BaseModel):
    name: str
    document_count: int
    # status (Fase F): `None` só é teoricamente possível se alguém
    # inspecionar uma sessão criada antes desta migração, num processo
    # que nunca reiniciou -- sessões são só em memória, então isso nunca
    # sobrevive a um deploy; documentado, não uma lacuna real em uso normal.
    status: CollectionStatus | None = None


class SessionStatusResponse(BaseModel):
    session_id: str
    collections: list[SessionCollectionInfo]


class SessionRestoreResponse(BaseModel):
    """POST /sessions/{session_id}/restore (2026-09-02, 4ª rodada) -- ver
    api/routers/documents.py. `reason` só é preenchido quando `restored`
    é False, pra explicar por que não havia nada a restaurar (nunca um
    erro -- HTTP 200 nos 2 casos, "não havia nada" é um resultado válido,
    não uma falha)."""

    restored: bool
    collections: list[str]
    reason: Literal["session_still_alive", "nothing_to_restore", "download_failed", None] = None
