"""Abstração `DocumentLoader` (prompt-mestre "Docksmith" §6/§8/§10) --
2ª rodada da fatia fundacional da Fase I, depois do retriever híbrido
(rag.py). Adiciona ingestão de PDF/DOCX ao lado da URL já existente
(`docksmith/service/scraping.py`, não tocado aqui), sem espalhar lógica
específica de formato pelos endpoints.

Regra central deste módulo (§8): "Não utilizar LLM para extrair texto" --
cada loader é 100% determinístico, biblioteca especializada por formato
(PyMuPDF pra PDF, python-docx pra DOCX), zero chamada de IA.

Escopo desta rodada: PDFs textuais (extração direta) e DOCX. PDF
ESCANEADO (sem texto extraível) é detectado e reportado com um erro claro
em vez de silenciosamente devolver documentos vazios -- OCR em si (§9)
fica fora do escopo desta rodada: o próprio prompt exige que OCR rode em
fila/worker, nunca na thread principal, e este backend ainda não tem
fila/worker (ver docs/AUDITORIA_E_MIGRACAO_RAG.md, Fase 10, também não
implementada nesta rodada) -- implementar OCR síncrono contrariaria
diretamente essa regra, então foi deliberadamente adiado junto com a fila.

3ª rodada (2026-09-02, prompt-mestre §13 "CHUNKING INTELIGENTE" + §16
"BUSCA ESTRUTURAL"): cada `LoadedDocument` agora carrega `chapter`/
`section`/`page_start`/`page_end` reais, não só um rótulo de exibição —
é isso que permite `query_engine.py` responder "qual o título do
capítulo 7?"/"resuma a página 124" filtrando por metadado, sem embeddings
e sem LLM, exatamente como o prompt pede. Continua 100% determinístico
(zero chamada de IA): DOCX já tinha os headings reais do próprio formato
(`paragraph.style.name`, "Heading 1"/"Heading 2"); PDF ganhou uma
detecção real de título/capítulo por tamanho de fonte (PyMuPDF expõe o
tamanho de cada linha via `get_text("dict")`) — uma técnica padrão de
extração de estrutura, não um LLM adivinhando.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import fitz  # PyMuPDF
from docx import Document as DocxDocument


@dataclass
class LoadedDocument:
    """Uma unidade de conteúdo já extraída, com proveniência real (§11:
    "o sistema precisa saber de onde cada trecho veio"). `source_label` é
    reaproveitado tal qual pelo parâmetro `source_labels` que
    `RAGService.load_collection` já aceita desde a 1ª rodada da Fase I --
    zero mudança de assinatura necessária ali.

    `chapter`/`section`/`page_start`/`page_end` (3ª rodada, §13/§16): a
    estrutura REAL do documento, quando determinável sem IA -- `None`
    quando o formato/conteúdo não oferece essa informação (ex.: DOCX não
    tem página real antes de renderizar; um PDF sem nenhum título
    detectável por fonte maior não tem capítulo/seção). `query_engine.py`
    trata ausência como "essa busca estrutural não se aplica aqui", nunca
    como erro."""

    text: str
    source_label: str
    chapter: str | None = None
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None


class UnsupportedDocumentError(Exception):
    """Erro claro (não uma lista vazia silenciosa) quando o documento não
    pode ser processado com os meios determinísticos disponíveis hoje."""


class PageLimitExceededError(UnsupportedDocumentError):
    """Documento excede `max_pages` e o chamador não pediu truncamento
    (`truncate=False`, o padrão). Carrega os números reais como atributos
    -- não só uma mensagem formatada -- pra que a camada de API (api/
    routers/documents.py) consiga devolver uma resposta estruturada, e o
    frontend consiga oferecer "processar só as primeiras N páginas" em vez
    de só mostrar um erro sem nenhuma saída (2026-09-10, pedido explícito
    do usuário testando o upload de um livro real de 446 páginas)."""

    def __init__(self, actual_count: int, max_pages: int, *, unit: str):
        self.actual_count = actual_count
        self.max_pages = max_pages
        self.unit = unit
        super().__init__(f"O documento tem {actual_count} {unit}, acima do limite de {max_pages} por envio.")


# Limite de tamanho de linha para ser candidata a título/heading (títulos
# reais raramente passam disso; evita marcar um parágrafo grande com fonte
# levemente maior -- ex. uma citação em destaque -- como capítulo).
_MAX_HEADING_CHARS = 120
# Uma linha só é candidata a heading se a fonte dela for pelo menos essa
# proporção maior que a fonte "de corpo" (a mais comum) da página inteira
# -- filtra negrito/itálico do próprio corpo do texto, que não aumenta o
# tamanho da fonte, só o peso/estilo.
_HEADING_SIZE_RATIO = 1.15


def _extract_pdf_page_lines_with_font_size(page) -> list[tuple[str, float]]:
    """Uma linha de texto + o tamanho de fonte real dela (PyMuPDF's
    `get_text("dict")`, sem nenhuma chamada de IA -- é assim que
    extratores de estrutura de PDF de verdade funcionam: título real
    geralmente usa fonte maior que o corpo do texto)."""
    lines: list[tuple[str, float]] = []
    raw = page.get_text("dict")
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            # Tamanho de fonte dominante da linha (a maior entre os spans
            # que a compõem -- uma linha quase sempre é uniforme, mas usar
            # o máximo é seguro contra qualquer span residual menor).
            size = max(span.get("size", 0.0) for span in spans)
            lines.append((text, size))
    return lines


def _detect_pdf_headings(pdf) -> dict[int, list[tuple[str, float]]]:
    """Para cada página, as linhas candidatas a heading (texto curto, fonte
    visivelmente maior que o corpo do documento inteiro). Calcula o
    tamanho de fonte "de corpo" a partir da MEDIANA de todas as linhas do
    PDF inteiro (mais robusto que usar só a página atual, que pode ter
    pouco texto de corpo pra comparar)."""
    all_lines_by_page: dict[int, list[tuple[str, float]]] = {}
    all_sizes: list[float] = []
    for page_index in range(pdf.page_count):
        page = pdf.load_page(page_index)
        lines = _extract_pdf_page_lines_with_font_size(page)
        all_lines_by_page[page_index] = lines
        all_sizes.extend(size for _, size in lines)

    if not all_sizes:
        return {}
    sorted_sizes = sorted(all_sizes)
    body_size = sorted_sizes[len(sorted_sizes) // 2]  # mediana

    headings_by_page: dict[int, list[tuple[str, float]]] = {}
    for page_index, lines in all_lines_by_page.items():
        candidates = [
            (text, size)
            for text, size in lines
            if size >= body_size * _HEADING_SIZE_RATIO and len(text) <= _MAX_HEADING_CHARS
        ]
        if candidates:
            headings_by_page[page_index] = candidates
    return headings_by_page


# Marcador de capítulo real (não "contém um dígito em algum lugar" -- isso
# achou candidato demais na prática, ver docstring de `_pick_chapter_size`
# abaixo): o texto INTEIRO é essencialmente só o rótulo + número, como um
# heading de verdade escreve capítulo ("CHAPTER 7", "Capítulo 7", "Cap. 7"),
# nunca uma frase de conteúdo que só incidentalmente cita um número (ex.
# "Principle 1: Choose Common Components Wisely", que também tem `\d` mas
# não é, de forma nenhuma, um marcador de capítulo).
_CHAPTER_HEADING_LABEL_RE = re.compile(r"^(chapter|cap[íi]tulo|cap\.?)\s*\d+\.?\s*$", re.IGNORECASE)

# Nº mínimo de páginas distintas pra um tamanho de fonte ser elegível a
# "nível de capítulo/seção" -- descarta algo que aparece só na capa/folha
# de rosto (1 página só), que nunca é um heading estrutural de verdade.
_MIN_DISTINCT_PAGES_FOR_HEADING_LEVEL = 2


def _pages_per_heading_size(headings_by_page: dict[int, list[tuple[str, float]]]) -> dict[float, set[int]]:
    pages_per_size: dict[float, set[int]] = {}
    for page_index, headings in headings_by_page.items():
        for _, size in headings:
            pages_per_size.setdefault(size, set()).add(page_index)
    return pages_per_size


def _pick_chapter_size(headings_by_page: dict[int, list[tuple[str, float]]]) -> float | None:
    """Qual tamanho de fonte representa "capítulo" de verdade.

    Bug real corrigido (2026-09-10, achado testando um livro real pelo
    Hub, não hipotético): a versão original escolhia "capítulo = o MAIOR
    tamanho de fonte do documento inteiro" -- quebra em qualquer livro
    real com capa (o título da capa quase sempre é a maior fonte do PDF,
    mas nunca se repete depois da página 1; um livro real testado tinha
    capa em fonte 67 contra "CHAPTER N" em fonte 16.8 -- `current_chapter`
    ficava travado no texto da capa nas 280 páginas seguintes inteiras).
    Uma 1ª correção trocou "maior tamanho" por "tamanho mais frequente
    entre páginas distintas" -- também errada, na direção oposta: no
    mesmo livro real, subtítulos de CONTEÚDO (ex. "Data Engineering
    Defined") apareceram em 128 páginas -- muito mais frequentes que o
    próprio "CHAPTER N" (7 páginas, uma por capítulo), porque cada
    capítulo tem várias subseções. "Mais frequente" tende a escolher o
    nível mais RASO da hierarquia (seção), não capítulo.

    O sinal real e específico de "isto é um marcador de capítulo, não
    seção nem capa": o TEXTO INTEIRO da linha casa com um rótulo de
    capítulo de verdade ("CHAPTER 7", "Capítulo 7", "Cap. 7" -- ver
    `_CHAPTER_HEADING_LABEL_RE`), E se repete em 2+ páginas distintas
    (descarta a capa, que nunca se repete).

    Achado real no meio desta própria correção, não hipotético: uma
    tentativa anterior usava só "o texto CONTÉM um dígito em algum lugar"
    -- no mesmo livro real, isso capturou também headings de conteúdo
    tipo "Principle 1: Choose Common Components Wisely" (a fonte de
    "Principle N" tinha 128 ocorrências, contra 7 de "CHAPTER N" -- o
    critério fraco escolhia o candidato errado de novo, pelo mesmo motivo
    da 1ª correção). Exigir que o texto INTEIRO seja essencialmente só o
    marcador (não uma frase de conteúdo que só incidentalmente cita um
    número) resolve isso.

    Entre os candidatos que batem o padrão de rótulo, escolhe o que
    aparece no MAIOR nº de páginas (mais headings numerados = sinal mais
    forte de que é o padrão real de capítulo do documento).

    Fallback (livro sem nenhum heading numerado detectável nesse formato,
    ex. capítulos só com título, sem "Capítulo N"/"Chapter N"): volta pro
    tamanho mais frequente entre páginas distintas -- pior sinal (a busca
    estrutural por número de capítulo nunca vai achar nada de qualquer
    forma, já que o PDF não tem essa numeração), mas ainda melhor que
    travar na capa."""
    pages_per_size = _pages_per_heading_size(headings_by_page)
    numbered_candidates = _numbered_chapter_candidates(headings_by_page)
    if numbered_candidates:
        return max(numbered_candidates, key=lambda size: len(pages_per_size[size]))

    eligible = [size for size, pages in pages_per_size.items() if len(pages) >= _MIN_DISTINCT_PAGES_FOR_HEADING_LEVEL]
    if eligible:
        return max(eligible, key=lambda size: (len(pages_per_size[size]), size))
    return max(pages_per_size, key=lambda size: size) if pages_per_size else None


def _numbered_chapter_candidates(headings_by_page: dict[int, list[tuple[str, float]]]) -> list[float]:
    """Tamanhos de fonte cujo texto casa com um rótulo de capítulo REAL
    (`_CHAPTER_HEADING_LABEL_RE`) em 2+ páginas distintas -- o mesmo sinal
    forte que `_pick_chapter_size` usa pra decidir se confia no capítulo
    detectado ou cai no fallback fraco de frequência (ver docstring
    acima). Extraído como função própria (Fase A, divisão por capítulo)
    pra ser reaproveitado por `split_pdf_into_parts`: dividir um livro em
    partes só deve confiar nesse sinal FORTE -- o fallback de frequência
    pode escolher um nível de SEÇÃO em vez de capítulo, o que cortaria as
    partes no lugar errado, não só exibiria um metadado impreciso."""
    pages_per_size = _pages_per_heading_size(headings_by_page)
    return [
        size
        for size, pages in pages_per_size.items()
        if len(pages) >= _MIN_DISTINCT_PAGES_FOR_HEADING_LEVEL
        and any(
            _CHAPTER_HEADING_LABEL_RE.match(text)
            for page_index in pages
            for text, s in headings_by_page[page_index]
            if s == size
        )
    ]


def _has_reliable_chapter_labels(headings_by_page: dict[int, list[tuple[str, float]]]) -> bool:
    """`True` só quando `_pick_chapter_size` está confiando num rótulo de
    capítulo real (ex. "CHAPTER 7"), não no fallback de frequência. Usado
    por `split_pdf_into_parts` (Fase A) pra decidir entre agrupar por
    capítulo ou cair pra janela de página pura -- ver docstring de
    `_numbered_chapter_candidates`."""
    return bool(_numbered_chapter_candidates(headings_by_page))


def _assign_chapter_and_section(headings_by_page: dict[int, list[tuple[str, float]]], page_count: int) -> tuple[list[str | None], list[str | None]]:
    """Dado os headings detectados por página, decide qual tamanho de
    fonte representa "capítulo" e qual representa "seção" -- só 2 níveis,
    igual à hierarquia DOCX (Heading 1/Heading 2), suficiente pro que
    §16/§17 realmente precisam (filtrar por capítulo). Cada página herda
    o heading mais recente visto até ela (inclusive), na ordem natural do
    documento -- mesmo princípio já usado por load_docx abaixo.

    `chapter_size` é escolhido por `_pick_chapter_size` (ver docstring lá
    pro bug real que essa lógica corrige). `section_size`: dentre os
    tamanhos restantes (excluindo o já escolhido como capítulo), o mais
    frequente entre páginas distintas -- é o padrão real observado
    (subtítulos de conteúdo se repetem muito mais que capítulos)."""
    chapter_size = _pick_chapter_size(headings_by_page)
    pages_per_size = _pages_per_heading_size(headings_by_page)
    remaining = {size: pages for size, pages in pages_per_size.items() if size != chapter_size}
    section_size = max(remaining, key=lambda size: (len(remaining[size]), size)) if remaining else None

    chapters: list[str | None] = [None] * page_count
    sections: list[str | None] = [None] * page_count
    current_chapter: str | None = None
    current_section: str | None = None
    for page_index in range(page_count):
        for text, size in headings_by_page.get(page_index, []):
            if chapter_size is not None and size == chapter_size:
                current_chapter = text
                current_section = None  # um capítulo novo reseta a seção atual
            elif section_size is not None and size == section_size:
                current_section = text
        chapters[page_index] = current_chapter
        sections[page_index] = current_section
    return chapters, sections


def load_pdf(
    file_bytes: bytes, filename: str, *, max_pages: int, truncate: bool = False
) -> list[LoadedDocument]:
    """Extração direta de texto, uma `LoadedDocument` por página (§8:
    "preservar páginas; preservar ordem"). PyMuPDF localiza texto real
    embutido no PDF -- não faz OCR (isso é `load_pdf`'s trabalho apenas
    quando o PDF já É textual).

    Detecção de PDF escaneado (§9): se NENHUMA página tiver texto
    extraível, o PDF quase certamente é só imagem (scan) -- levanta
    `UnsupportedDocumentError` com uma mensagem clara em vez de devolver
    uma coleção vazia que pareceria "extraiu com sucesso, mas sem
    conteúdo" pro usuário.

    `truncate` (2026-09-10, pedido explícito do usuário): quando o
    documento excede `max_pages`, o padrão (`truncate=False`) continua
    sendo recusar com `PageLimitExceededError` -- mas com `truncate=True`,
    processa só as primeiras `max_pages` páginas em vez de recusar por
    completo, dando ao usuário um resultado parcial útil em vez de nada.
    O router decide quando usar cada modo (ver api/routers/documents.py).
    """
    try:
        pdf = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 -- qualquer PDF corrompido/inválido vira um erro claro
        raise UnsupportedDocumentError(f"Não foi possível abrir o PDF: {exc}") from exc

    try:
        if pdf.page_count == 0:
            raise UnsupportedDocumentError("O PDF não tem nenhuma página.")
        if pdf.page_count > max_pages and not truncate:
            raise PageLimitExceededError(pdf.page_count, max_pages, unit="páginas")
        pages_to_process = min(pdf.page_count, max_pages)

        # Detecção real de capítulo/seção por tamanho de fonte (§13/§16) --
        # feita ANTES do loop principal porque precisa ver o documento
        # inteiro (a mediana de tamanho de fonte é calculada sobre todas as
        # páginas, não só a atual).
        headings_by_page = _detect_pdf_headings(pdf)
        chapters, sections = _assign_chapter_and_section(headings_by_page, pdf.page_count)

        documents: list[LoadedDocument] = []
        for page_index in range(pages_to_process):
            page = pdf.load_page(page_index)
            text = page.get_text("text").strip()
            if text:
                documents.append(
                    LoadedDocument(
                        text=text,
                        source_label=f"{filename} - página {page_index + 1}",
                        chapter=chapters[page_index],
                        section=sections[page_index],
                        page_start=page_index + 1,
                        page_end=page_index + 1,
                    )
                )

        if not documents:
            raise UnsupportedDocumentError(
                "Este PDF não tem texto extraível em nenhuma página -- parece ser um documento "
                "escaneado (só imagem). OCR ainda não é suportado."
            )
        return documents
    finally:
        pdf.close()


@dataclass
class PdfPart:
    """Uma parte de um PDF grande, produzida por `split_pdf_into_parts`
    (Fase A, "OBSERVAÇÕES FINAIS" §2: divisão consciente de estrutura, não
    janela fixa quando dá pra evitar). `documents` já está pronto pra
    indexar -- dividir em partes não muda o que cada `LoadedDocument`
    carrega, só agrupa o resultado em fatias menores que `max_pages`.

    `chapters`: lista ORDENADA e sem repetição dos capítulos cobertos por
    esta parte -- vazia quando o PDF não tem nenhum capítulo com rótulo
    confiável (fallback por janela de página pura, ver
    `split_pdf_into_parts`). Diferente de `load_pdf` (que sempre preenche
    `LoadedDocument.chapter` com o melhor palpite disponível, mesmo vindo
    do fallback de frequência): aqui o capítulo está sendo usado pra
    DECIDIR onde cortar, não só pra exibição -- por isso o padrão exigido
    é mais rígido, e fica `None`/vazio em vez de reportar um palpite não
    confirmado como se fosse capítulo real."""

    name: str
    documents: list[LoadedDocument]
    page_start: int | None
    page_end: int | None
    chapters: list[str]

    @property
    def page_count(self) -> int:
        return len(self.documents)

    @property
    def total_chars(self) -> int:
        return sum(len(doc.text) for doc in self.documents)


def _group_documents_by_chapter_within_limit(
    all_documents: list[LoadedDocument], max_pages: int
) -> list[tuple[list[LoadedDocument], list[str]]]:
    """Núcleo do agrupamento por capítulo (Fase A) -- reaproveitado tanto
    por PDF (unidade = página) quanto por DOCX (unidade = seção), já que a
    REGRA é idêntica nos dois formatos: agrupa sequencialmente até que o
    PRÓXIMO capítulo inteiro ultrapasse `max_pages`, fechando a parte ali
    (nunca corta um capítulo no meio quando dá pra evitar). Um capítulo
    que sozinho já excede `max_pages` cai pra janela fixa só pra ELE --
    os demais capítulos continuam intactos, cada um em sua própria parte.

    Quando nenhum documento tem `chapter` (ex.: PDF sem rótulo confiável,
    ver `_has_reliable_chapter_labels`), todos os docs caem num único
    grupo com `chapter=None` -- que, por ser maior que `max_pages` em
    qualquer documento que precisasse ser dividido, aciona sozinho o
    branch de janela fixa acima: o fallback "documento sem capítulo
    confiável = janela de página pura" emerge do mesmo algoritmo, sem
    precisar de um caminho de código separado.

    Devolve uma lista de `(documentos_da_parte, capítulos_cobertos)` --
    quem chama decide como rotular a posição da parte (página real pro
    PDF, índice de seção pro DOCX)."""
    chapter_groups: list[tuple[str | None, list[LoadedDocument]]] = []
    for doc in all_documents:
        if chapter_groups and chapter_groups[-1][0] == doc.chapter:
            chapter_groups[-1][1].append(doc)
        else:
            chapter_groups.append((doc.chapter, [doc]))

    result: list[tuple[list[LoadedDocument], list[str]]] = []
    current_docs: list[LoadedDocument] = []
    current_chapters: list[str] = []

    def flush() -> None:
        nonlocal current_docs, current_chapters
        if current_docs:
            result.append((current_docs, current_chapters))
        current_docs, current_chapters = [], []

    for chapter_name, docs in chapter_groups:
        if len(docs) > max_pages:
            # Este capítulo sozinho é maior que o teto -- fecha o que já
            # tinha acumulado, depois divide SÓ este capítulo por janela
            # de página fixa (honesto: não há como preservar "capítulo
            # inteiro numa parte só" quando ele sozinho já excede o teto).
            flush()
            for window_start in range(0, len(docs), max_pages):
                window = docs[window_start : window_start + max_pages]
                result.append((window, [chapter_name] if chapter_name else []))
            continue

        if len(current_docs) + len(docs) > max_pages:
            flush()

        current_docs = current_docs + docs
        if chapter_name and chapter_name not in current_chapters:
            current_chapters = current_chapters + [chapter_name]

    flush()
    return result


def split_pdf_into_parts(file_bytes: bytes, filename: str, *, max_pages: int) -> list[PdfPart]:
    """Divide um PDF grande em partes menores que `max_pages`, cada uma
    fechando ao final de um capítulo inteiro sempre que possível (Fase A
    -- substitui truncamento como único caminho pra documento grande).

    Zero custo de extração extra: reaproveita a MESMA extração de
    estrutura que `load_pdf` já faz (detecção de heading por tamanho de
    fonte), rodada uma vez só sobre o documento inteiro -- e o mesmo bug
    de detecção de capítulo já corrigido nesta sessão (`_pick_chapter_size`
    / `_has_reliable_chapter_labels`).

    Cai pra divisão pura por janela de página (sem agrupar por capítulo)
    quando nenhum padrão de capítulo NUMERADO e confiável foi detectado em
    lugar nenhum do documento -- nunca finge uma consciência de estrutura
    que a extração não conseguiu confirmar (ver `PdfPart.chapters`)."""
    try:
        pdf = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 -- qualquer PDF corrompido/inválido vira um erro claro
        raise UnsupportedDocumentError(f"Não foi possível abrir o PDF: {exc}") from exc

    try:
        if pdf.page_count == 0:
            raise UnsupportedDocumentError("O PDF não tem nenhuma página.")

        headings_by_page = _detect_pdf_headings(pdf)
        chapters, sections = _assign_chapter_and_section(headings_by_page, pdf.page_count)
        has_reliable_chapters = _has_reliable_chapter_labels(headings_by_page)

        all_documents: list[LoadedDocument] = []
        for page_index in range(pdf.page_count):
            page = pdf.load_page(page_index)
            text = page.get_text("text").strip()
            if text:
                all_documents.append(
                    LoadedDocument(
                        text=text,
                        source_label=f"{filename} - página {page_index + 1}",
                        chapter=chapters[page_index] if has_reliable_chapters else None,
                        section=sections[page_index],
                        page_start=page_index + 1,
                        page_end=page_index + 1,
                    )
                )

        if not all_documents:
            raise UnsupportedDocumentError(
                "Este PDF não tem texto extraível em nenhuma página -- parece ser um documento "
                "escaneado (só imagem). OCR ainda não é suportado."
            )

        groups = _group_documents_by_chapter_within_limit(all_documents, max_pages)
        parts: list[PdfPart] = []
        for docs, part_chapters in groups:
            parts.append(
                PdfPart(
                    name=f"{filename} - parte {len(parts) + 1}",
                    documents=docs,
                    page_start=docs[0].page_start,
                    page_end=docs[-1].page_end,
                    chapters=part_chapters,
                )
            )
        return parts
    finally:
        pdf.close()


_HEADING_LEVEL_RE = re.compile(r"heading\s*(\d+)", re.IGNORECASE)


def _docx_heading_level(style_name: str) -> int | None:
    """Nível real do heading a partir do nome do estilo do Word ("Heading
    1"/"Heading 2"/"Title") -- `None` se o parágrafo não for um heading.
    "Title" conta como nível 1 (mesmo papel estrutural de um Heading 1: um
    marcador de topo do documento)."""
    normalized = style_name.strip().lower()
    if normalized == "title":
        return 1
    match = _HEADING_LEVEL_RE.match(normalized)
    return int(match.group(1)) if match else None


def _parse_docx_sections(doc: DocxDocument) -> tuple[list[tuple[str, str | None, str | None, list[str]]], list[str]]:
    """Extração bruta de estrutura de um DOCX já aberto -- compartilhada
    por `load_docx` (documento inteiro, respeitando `max_pages`/
    `truncate`) e `split_docx_into_parts` (Fase A, divide em partes por
    capítulo). Zero duplicação do parsing em si; só o que cada chamador
    faz com o resultado difere.

    Hierarquia real de capítulo/seção (§13/§16): "Heading 1" (ou "Title")
    vira `chapter`; "Heading 2" (ou mais fundo) vira `section`, aninhado
    sob o `chapter` mais recente -- um novo capítulo zera a seção atual,
    a mesma regra usada pra PDF em `_assign_chapter_and_section` acima."""
    # (heading, chapter, section, [parágrafos])
    sections: list[tuple[str, str | None, str | None, list[str]]] = [("Documento", None, None, [])]
    current_chapter: str | None = None
    current_section: str | None = None
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style_name = (paragraph.style.name if paragraph.style else "") or ""
        level = _docx_heading_level(style_name)
        if level is not None:
            if level <= 1:
                current_chapter = text
                current_section = None
            else:
                current_section = text
            sections.append((text, current_chapter, current_section, []))
        else:
            sections[-1][3].append(text)

    # Tabelas (§10: "tabelas quando possível") viram um bloco de texto
    # próprio ao final, já que python-docx não amarra uma tabela a um
    # heading específico de forma confiável -- melhor um bloco extra e
    # honesto do que tentar adivinhar a seção errada.
    table_blocks: list[str] = []
    for table_index, table in enumerate(doc.tables):
        rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        rows = [row for row in rows if row.strip(" |")]
        if rows:
            table_blocks.append(f"Tabela {table_index + 1}:\n" + "\n".join(rows))

    return sections, table_blocks


def _docx_sections_to_documents(
    sections: list[tuple[str, str | None, str | None, list[str]]], table_blocks: list[str], filename: str
) -> list[LoadedDocument]:
    documents: list[LoadedDocument] = []
    for heading, chapter, section, paragraphs in sections:
        body = "\n\n".join(paragraphs).strip()
        if body:
            documents.append(
                LoadedDocument(
                    text=f"{heading}\n\n{body}" if heading != "Documento" else body,
                    source_label=f"{filename} - {heading}",
                    chapter=chapter,
                    section=section,
                )
            )
    if table_blocks:
        documents.append(LoadedDocument(text="\n\n".join(table_blocks), source_label=f"{filename} - Tabelas"))
    return documents


def load_docx(
    file_bytes: bytes, filename: str, *, max_pages: int, truncate: bool = False
) -> list[LoadedDocument]:
    """DOCX não tem conceito de "página" no próprio arquivo (paginação é
    calculada na hora de renderizar/imprimir, não armazenada no XML) --
    §10 pede "preservar títulos/headings/parágrafos/tabelas/ordem", então
    o agrupamento aqui é por SEÇÃO (o texto entre um heading e o
    próximo), que é a unidade estrutural real que o formato de fato
    guarda. `max_pages` é reaproveitado como um teto de nº de seções, pela
    mesma razão de segurança (§12: limites configuráveis, nunca
    hardcoded) -- documentos com centenas de headings são igualmente caros
    de indexar quanto um PDF de centenas de páginas.

    `truncate` (2026-09-10): mesmo contrato de `load_pdf` -- com
    `truncate=True`, mantém só as primeiras `max_pages` seções em vez de
    recusar o documento inteiro.
    """
    try:
        doc = DocxDocument(io.BytesIO(file_bytes))
    except Exception as exc:  # noqa: BLE001 -- .docx corrompido/inválido
        raise UnsupportedDocumentError(f"Não foi possível abrir o DOCX: {exc}") from exc

    sections, table_blocks = _parse_docx_sections(doc)
    documents = _docx_sections_to_documents(sections, table_blocks, filename)

    if not documents:
        raise UnsupportedDocumentError("Este DOCX não tem nenhum texto extraível (parágrafos ou tabelas).")
    if len(documents) > max_pages:
        if not truncate:
            raise PageLimitExceededError(len(documents), max_pages, unit="seções")
        documents = documents[:max_pages]
    return documents


@dataclass
class DocxPart:
    """Equivalente de `PdfPart` pro DOCX (Fase A) -- a unidade real do
    formato é SEÇÃO (heading), não página (DOCX não guarda paginação no
    próprio arquivo), então `section_start`/`section_end` são índices
    1-based de posição entre as seções extraídas, não números de página.
    Ao contrário do PDF, DOCX nunca tem ambiguidade de "isto é mesmo um
    capítulo?" -- o heading é dado real do formato -- então `chapters`
    reflete o capítulo real sempre que existir (nunca um palpite)."""

    name: str
    documents: list[LoadedDocument]
    section_start: int
    section_end: int
    chapters: list[str]

    @property
    def page_count(self) -> int:
        return len(self.documents)

    @property
    def total_chars(self) -> int:
        return sum(len(doc.text) for doc in self.documents)


def split_docx_into_parts(file_bytes: bytes, filename: str, *, max_pages: int) -> list[DocxPart]:
    """Mesmo princípio de `split_pdf_into_parts` (Fase A), mas agrupando
    por SEÇÃO real do Word (heading nível 1/"Title") em vez de página --
    é a unidade estrutural que o próprio formato DOCX guarda (§10).

    Reaproveita o mesmo núcleo de agrupamento
    (`_group_documents_by_chapter_within_limit`) que PDF usa: um DOCX sem
    nenhum heading cai naturalmente no mesmo fallback de janela fixa (todo
    documento vira 1 grupo só com `chapter=None`, que -- se maior que
    `max_pages` -- aciona o branch de janela dentro da própria função de
    agrupamento, sem precisar de um caminho de código separado aqui)."""
    try:
        doc = DocxDocument(io.BytesIO(file_bytes))
    except Exception as exc:  # noqa: BLE001 -- .docx corrompido/inválido
        raise UnsupportedDocumentError(f"Não foi possível abrir o DOCX: {exc}") from exc

    sections, table_blocks = _parse_docx_sections(doc)
    all_documents = _docx_sections_to_documents(sections, table_blocks, filename)

    if not all_documents:
        raise UnsupportedDocumentError("Este DOCX não tem nenhum texto extraível (parágrafos ou tabelas).")

    groups = _group_documents_by_chapter_within_limit(all_documents, max_pages)
    parts: list[DocxPart] = []
    cursor = 1
    for docs, part_chapters in groups:
        section_start = cursor
        section_end = cursor + len(docs) - 1
        cursor = section_end + 1
        parts.append(
            DocxPart(
                name=f"{filename} - parte {len(parts) + 1}",
                documents=docs,
                section_start=section_start,
                section_end=section_end,
                chapters=part_chapters,
            )
        )
    return parts


SUPPORTED_EXTENSIONS = {".pdf": load_pdf, ".docx": load_docx}
SUPPORTED_SPLIT_EXTENSIONS = {".pdf": split_pdf_into_parts, ".docx": split_docx_into_parts}


def load_document(
    file_bytes: bytes, filename: str, *, max_pages: int, truncate: bool = False
) -> list[LoadedDocument]:
    """Dispatcher único usado pelo endpoint de upload -- a lógica
    específica de formato fica só nos loaders acima, nunca no router
    (§6: "a lógica específica de cada formato não deve ficar espalhada
    pelos endpoints")."""
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    loader = SUPPORTED_EXTENSIONS.get(extension)
    if loader is None:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedDocumentError(f"Formato '{extension or filename}' não suportado. Formatos aceitos: {supported}.")
    return loader(file_bytes, filename, max_pages=max_pages, truncate=truncate)


def split_document_into_parts(file_bytes: bytes, filename: str, *, max_pages: int) -> list[PdfPart] | list[DocxPart]:
    """Dispatcher de divisão em partes (Fase A) -- mesmo papel de
    `load_document`, mas pro caminho de "documento grande dividido de
    forma consciente de estrutura" em vez de truncar/recusar; mesma regra
    (§6) de manter a lógica específica de formato fora do router."""
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    splitter = SUPPORTED_SPLIT_EXTENSIONS.get(extension)
    if splitter is None:
        supported = ", ".join(sorted(SUPPORTED_SPLIT_EXTENSIONS))
        raise UnsupportedDocumentError(f"Formato '{extension or filename}' não suportado. Formatos aceitos: {supported}.")
    return splitter(file_bytes, filename, max_pages=max_pages)
