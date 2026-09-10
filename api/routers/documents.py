"""POST /documents/upload -- ingestão de PDF/DOCX (prompt-mestre "Docksmith"
§6/§8/§10, 2ª rodada da Fase I). Mesmo padrão de sessão/coleção que
/scrape (scrape.py) já usa -- um documento carregado aqui vira uma
coleção consultável do mesmo jeito que uma raspagem de URL, então
`/chat` funciona sem nenhuma mudança.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from .. import auth, config, r2_storage, rate_limit, sessions
from ..bootstrap import (
    PageLimitExceededError,
    UnsupportedDocumentError,
    load_document,
    split_document_into_parts,
)
from ..index_cache import invalidate_collection
from ..logging_config import get_logger
from ..resource_estimate import resource_estimate
from ..schemas import DocumentPartInfo, ScrapeResponse, SessionRestoreResponse, SplitUploadResponse

router = APIRouter()
logger = get_logger(__name__)

_MAX_FILE_BYTES = config.DOCSMITH_MAX_FILE_SIZE_MB * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 1024 * 1024  # 1MB por pedaço


async def _read_upload_within_limit(file: UploadFile, max_bytes: int) -> bytes:
    """Lê o upload em pedaços de 1MB, abortando assim que o total
    ultrapassa o limite -- nunca deixa o processo bufferizar mais que
    ~1MB além do limite configurado, mesmo que o arquivo enviado seja bem
    maior (2026-09-02, 4ª rodada: o teto subiu de 20MB pra até 1GB, então
    isto deixou de ser um detalhe teórico). Antes desta rodada, `await
    file.read()` sozinho bufferizava o arquivo INTEIRO antes de qualquer
    checagem de tamanho rodar -- inofensivo a 20MB, real a 1GB. Mesma
    mensagem/status HTTP de antes (413), só a forma de chegar lá mudou."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Arquivo maior que o limite de {config.DOCSMITH_MAX_FILE_SIZE_MB}MB por envio.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/documents/upload", response_model=ScrapeResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    collection_name: str = Form(...),
    session_id: str | None = Form(None),
    truncate: bool = Form(False),
    user: dict = Depends(auth.get_current_user),
) -> ScrapeResponse:
    """`truncate` (2026-09-10, pedido explícito do usuário): quando um
    documento excede DOCSMITH_MAX_PAGES, o comportamento padrão continua
    sendo recusar (422, ver o `except PageLimitExceededError` abaixo, que
    devolve um `detail` estruturado com os números reais). O frontend usa
    esse `detail` pra oferecer "processar só as primeiras N páginas" --
    se o usuário aceitar, a MESMA requisição de upload é refeita com
    `truncate=true`, e desta vez o documento é aceito parcialmente em vez
    de recusado por completo."""
    user_id = user["user"].get("id")
    rate_limit.check_rate_limit(user_id, "upload")
    filename = file.filename or "documento"

    raw = await _read_upload_within_limit(file, _MAX_FILE_BYTES)
    if not raw:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")

    # Sessão criada/recuperada ANTES da extração (Fase F, 2026-09-10 --
    # antes desta fase, a ordem era invertida: extraía primeiro, só criava
    # sessão depois de confirmar sucesso). Precisa existir primeiro por 2
    # motivos reais: (1) só assim `collection_status[collection_name]`
    # pode registrar "extracting"/"failed" de forma observável, mesmo que
    # hoje só dentro da mesma requisição síncrona (ver nota abaixo); (2)
    # permite rodar a extração em threadpool (`run_in_threadpool`, mesmo
    # padrão já usado por `restore_session` neste arquivo) em vez de
    # bloquear a event loop inteira durante o parse de um PDF grande --
    # achado real, não hipotético: antes desta fase, `load_document`
    # rodava direto na coroutine, diferente de `restore_session` (mesmo
    # arquivo) que já usava threadpool pra isso.
    session_id, session = sessions.get_or_create_session(session_id, user_id)
    status_by_collection = session.setdefault("collection_status", {})
    status_by_collection[collection_name] = "extracting"

    try:
        loaded = await run_in_threadpool(
            load_document, raw, filename, max_pages=config.DOCSMITH_MAX_PAGES, truncate=truncate
        )
    except PageLimitExceededError as exc:
        status_by_collection[collection_name] = "failed"
        logger.warning(
            "Upload de documento acima do limite de páginas: arquivo=%s total=%d limite=%d",
            filename, exc.actual_count, exc.max_pages,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "page_limit_exceeded",
                "message": str(exc),
                "actual_count": exc.actual_count,
                "max_pages": exc.max_pages,
                "unit": exc.unit,
            },
        ) from exc
    except UnsupportedDocumentError as exc:
        status_by_collection[collection_name] = "failed"
        logger.warning("Upload de documento rejeitado: arquivo=%s erro=%s", filename, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing_docs: list[str] = session["collections"].get(collection_name, [])
    session.setdefault("collection_labels", {})
    session.setdefault("collection_structure", {})
    existing_labels: list[str] = session["collection_labels"].get(collection_name, [])
    existing_structure: list[dict] = session["collection_structure"].get(collection_name, [])
    if len(existing_labels) < len(existing_docs):
        # A coleção já existia com documentos sem rótulo próprio (ex.: veio
        # de /scrape, que nunca escreve em collection_labels) -- preenche
        # com o mesmo rótulo genérico que RAGService.load_collection usaria
        # de qualquer forma, pra não desalinhar os dois índices em paralelo.
        existing_labels = existing_labels + [f"documento_{i}" for i in range(len(existing_labels), len(existing_docs))]
    if len(existing_structure) < len(existing_docs):
        # Mesmo raciocínio, pra estrutura (3ª rodada): documentos antigos
        # sem chapter/section/página conhecidos viram entradas "vazias"
        # (tudo None) -- RAGService.load_collection já trata isso como
        # "sem estrutura", idêntico a não ter recebido nada.
        existing_structure = existing_structure + [
            {"chapter": None, "section": None, "page_start": None, "page_end": None}
            for _ in range(len(existing_structure), len(existing_docs))
        ]

    new_texts = [doc.text for doc in loaded]
    new_labels = [doc.source_label for doc in loaded]
    new_structure = [
        {"chapter": doc.chapter, "section": doc.section, "page_start": doc.page_start, "page_end": doc.page_end}
        for doc in loaded
    ]
    session["collections"][collection_name] = existing_docs + new_texts
    session["collection_labels"][collection_name] = existing_labels + new_labels
    session["collection_structure"][collection_name] = existing_structure + new_structure
    status_by_collection[collection_name] = "uploaded"
    # Um upload novo invalida qualquer índice já carregado pra esta
    # coleção -- mesma lógica de sempre (chat.py só reindexa quando a
    # `signature` não está no cache; como o conteúdo mudou mas a
    # signature por si só não capturaria isso, força a reindexação na
    # próxima pergunta). Fase E: agora pode haver várias entradas de
    # cache pra esta coleção (combinações diferentes de provider/model/
    # depth) -- `invalidate_collection` varre e remove todas.
    invalidate_collection(session.setdefault("loaded_indices", {}), collection_name)

    all_docs = session["collections"][collection_name]
    logger.info(
        "Documento ingerido: arquivo=%s coleção=%s novos_documentos=%d total_documentos=%d",
        filename, collection_name, len(loaded), len(all_docs),
    )

    # Cópia de segurança no R2 (2026-09-02, 4ª rodada) -- best-effort e
    # "fire-and-forget" via BackgroundTasks (roda DEPOIS da resposta HTTP
    # já ter sido enviada, não soma latência ao upload). Se R2 não estiver
    # configurado, `upload_raw_bytes` nem chega a tentar (`is_configured()`
    # já filtra isso) -- zero custo extra em qualquer ambiente sem as
    # variáveis R2_* definidas. Isto NÃO é a fila real de processamento
    # ainda pendente (registrada em docs/CONFIGURAR_R2.md) -- a extração/
    # indexação em si continua síncrona, dentro desta mesma requisição,
    # como sempre foi; só o backup do arquivo original é adiado.
    background_tasks.add_task(
        r2_storage.upload_raw_bytes,
        user_id=user_id,
        session_id=session_id,
        collection_name=collection_name,
        filename=filename,
        raw_bytes=raw,
    )

    estimate = resource_estimate(all_docs)
    return ScrapeResponse(
        session_id=session_id,
        collection_name=collection_name,
        document_count=len(all_docs),
        preview=[doc[:400] for doc in all_docs[:2]],
        resource_estimate=estimate,
        # Aproximação deliberada, não um recálculo exato do loader (ver
        # PageLimitExceededError acima): o único cliente que manda
        # truncate=true é o próprio frontend, e só depois de já ter
        # recebido um 422 "page_limit_exceeded" para este mesmo arquivo --
        # então "pediu truncamento" já implica "o arquivo excedia o
        # limite" na prática real de uso.
        truncated=truncate,
    )


def _part_position(part) -> tuple[int | None, int | None, str]:
    """`(page_start, page_end, "páginas")` pro `PdfPart`,
    `(section_start, section_end, "seções")` pro `DocxPart` -- normaliza
    os 2 nomes de atributo diferentes (a unidade real de cada formato,
    ver docksmith/service/document_loader.py) num único par posicional +
    rótulo pra resposta da API, mesmo padrão de `unit` já usado por
    `PageLimitExceededError`."""
    if hasattr(part, "page_start"):
        return part.page_start, part.page_end, "páginas"
    return part.section_start, part.section_end, "seções"


@router.post("/documents/upload/split", response_model=SplitUploadResponse)
async def upload_document_split(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    collection_name: str = Form(...),
    session_id: str | None = Form(None),
    user: dict = Depends(auth.get_current_user),
) -> SplitUploadResponse:
    """Divisão inteligente consciente de estrutura (Fase A, 2026-09-10) --
    alternativa a `truncate=true` (POST /documents/upload) pra documento
    acima de DOCSMITH_MAX_PAGES: em vez de descartar o que excede o
    limite, divide o documento inteiro em N partes (cada uma dentro do
    limite, fechando ao final de um capítulo sempre que possível -- ver
    split_document_into_parts) e cria N coleções consultáveis, uma por
    parte, já disponíveis em /chat.

    Endpoint próprio (não reaproveita /documents/upload): a resposta tem
    um formato genuinamente diferente -- N coleções com metadado próprio
    cada, não 1 coleção só -- misturar os 2 sob o mesmo `response_model`
    exigiria um tipo União só pra acomodar 2 contratos bem diferentes; o
    endpoint existente fica 100% intocado (mesma assinatura/comportamento
    de sempre) pra qualquer chamador já em uso.

    Cada chamada recria as partes do zero (não tenta mesclar com um upload
    dividido anterior sob o mesmo `collection_name` base) -- combinar
    partes de uploads DIFERENTES sob a mesma coleção-base não faria
    sentido semântico (não são fragmentos do mesmo arquivo)."""
    user_id = user["user"].get("id")
    rate_limit.check_rate_limit(user_id, "upload")
    filename = file.filename or "documento"

    raw = await _read_upload_within_limit(file, _MAX_FILE_BYTES)
    if not raw:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")

    # Mesma reordenação de /documents/upload (Fase F, ver nota lá): sessão
    # primeiro, extração em threadpool depois -- aqui o checkpoint
    # "extracting"/"failed" fica registrado sob o nome-BASE (a coleção-base
    # em si nunca vira uma coleção consultável, só as N partes viram), já
    # que ainda não sabemos quantas partes vão existir antes de dividir.
    session_id, session = sessions.get_or_create_session(session_id, user_id)
    session.setdefault("collection_labels", {})
    session.setdefault("collection_structure", {})
    status_by_collection = session.setdefault("collection_status", {})
    status_by_collection[collection_name] = "extracting"

    try:
        parts = await run_in_threadpool(split_document_into_parts, raw, filename, max_pages=config.DOCSMITH_MAX_PAGES)
    except UnsupportedDocumentError as exc:
        status_by_collection[collection_name] = "failed"
        logger.warning("Upload dividido rejeitado: arquivo=%s erro=%s", filename, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    status_by_collection.pop(collection_name, None)  # nome-base nunca é uma coleção real; só as partes abaixo são

    part_infos: list[DocumentPartInfo] = []
    for index, part in enumerate(parts, start=1):
        part_collection_name = f"{collection_name} - parte {index}"
        texts = [doc.text for doc in part.documents]
        labels = [doc.source_label for doc in part.documents]
        structure = [
            {"chapter": doc.chapter, "section": doc.section, "page_start": doc.page_start, "page_end": doc.page_end}
            for doc in part.documents
        ]
        session["collections"][part_collection_name] = texts
        session["collection_labels"][part_collection_name] = labels
        session["collection_structure"][part_collection_name] = structure
        status_by_collection[part_collection_name] = "uploaded"
        # Mesma lógica de invalidação de índice que /documents/upload já
        # aplica -- se esta coleção já estava carregada (nome coincide
        # por acaso com uma anterior), a próxima pergunta reindexa.
        invalidate_collection(session.setdefault("loaded_indices", {}), part_collection_name)

        position_start, position_end, unit = _part_position(part)
        estimate = resource_estimate(texts)
        part_infos.append(
            DocumentPartInfo(
                collection_name=part_collection_name,
                part_number=index,
                unit=unit,
                position_start=position_start,
                position_end=position_end,
                chapters=part.chapters,
                page_count=part.page_count,
                document_count=len(texts),
                estimated_chunks=estimate["estimated_chunks"],
                estimated_size_mb=estimate["total_mb"],
            )
        )

    logger.info(
        "Documento dividido em partes: arquivo=%s coleção_base=%s partes=%d total_unidades=%d",
        filename, collection_name, len(parts), sum(p.page_count for p in parts),
    )

    # Mesmo backup best-effort que /documents/upload já faz -- 1 upload só
    # do arquivo ORIGINAL inteiro (nunca N backups, 1 por parte); Fase D
    # do plano já confirma que restauração de sessão sabe re-extrair/
    # re-dividir do zero a partir desse mesmo arquivo bruto.
    background_tasks.add_task(
        r2_storage.upload_raw_bytes,
        user_id=user_id,
        session_id=session_id,
        collection_name=collection_name,
        filename=filename,
        raw_bytes=raw,
    )

    return SplitUploadResponse(session_id=session_id, base_collection_name=collection_name, parts=part_infos)


@router.post("/sessions/{session_id}/restore", response_model=SessionRestoreResponse)
async def restore_session(
    session_id: str,
    user: dict = Depends(auth.get_current_user),
) -> SessionRestoreResponse:
    """Restaura, a partir do R2, os documentos de uma sessão que expirou
    ou sumiu (reinício/deploy do servidor no meio da sessão) -- 2026-09-02,
    4ª rodada, resolve o achado "documentos ainda somem a cada reinício do
    servidor". Chamado com o MESMO `session_id` que o cliente já tinha
    (`/chat` continua devolvendo 404 "Sessão expirada. Refaça a extração."
    exatamente como sempre devolveu -- este endpoint é aditivo, o frontend
    decide quando chamá-lo, ex.: automaticamente ao receber esse 404, ou
    numa tentativa proativa logo depois de criar/recuperar uma sessão).

    Sempre HTTP 200 -- "não havia nada pra restaurar" é um resultado
    válido (`restored=False`), não um erro; só falha alto (404/500) se a
    própria autenticação falhar antes de chegar aqui (mesmo comportamento
    de qualquer outro endpoint autenticado)."""
    user_id = user["user"].get("id")

    existing = sessions.get_session(session_id, user_id)
    if existing is not None:
        return SessionRestoreResponse(
            restored=False,
            collections=list(existing["collections"].keys()),
            reason="session_still_alive",
        )

    objects = await run_in_threadpool(r2_storage.list_session_objects, user_id=user_id, session_id=session_id)
    if not objects:
        return SessionRestoreResponse(restored=False, collections=[], reason="nothing_to_restore")

    collections: dict[str, list[str]] = {}
    collection_labels: dict[str, list[str]] = {}
    collection_structure: dict[str, list[dict]] = {}
    restored_files = 0
    for obj in objects:
        raw = await run_in_threadpool(r2_storage.download_raw_bytes, obj["key"])
        if raw is None:
            continue
        try:
            loaded = await run_in_threadpool(
                load_document, raw, obj["filename"], max_pages=config.DOCSMITH_MAX_PAGES
            )
        except UnsupportedDocumentError:
            # Um objeto individual corrompido/ilegível não derruba a
            # restauração inteira -- os outros documentos da sessão
            # continuam sendo restaurados normalmente.
            logger.warning("Objeto R2 não pôde ser re-extraído na restauração: chave=%s", obj["key"])
            continue
        cname = obj["collection_name"] or "restaurado"
        collections.setdefault(cname, []).extend(doc.text for doc in loaded)
        collection_labels.setdefault(cname, []).extend(doc.source_label for doc in loaded)
        collection_structure.setdefault(cname, []).extend(
            {"chapter": doc.chapter, "section": doc.section, "page_start": doc.page_start, "page_end": doc.page_end}
            for doc in loaded
        )
        restored_files += 1

    if restored_files == 0:
        return SessionRestoreResponse(restored=False, collections=[], reason="download_failed")

    sessions.restore_session(
        session_id,
        user_id,
        collections=collections,
        collection_labels=collection_labels,
        collection_structure=collection_structure,
    )
    logger.info(
        "Sessão restaurada via R2: sessão=%s coleções=%d arquivos=%d",
        session_id, len(collections), restored_files,
    )
    return SessionRestoreResponse(restored=True, collections=list(collections.keys()), reason=None)
