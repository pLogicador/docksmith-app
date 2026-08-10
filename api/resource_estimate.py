"""Estimativa de recursos (RAM) necessários para indexar uma coleção — avisa
o usuário ANTES/DURANTE a preparação da indexação (FAISS + embeddings), sem
criar nenhuma persistência nova. Puramente informativo/defensivo: continua
sendo sessão → memória RAM → processamento → descarte ao final da sessão.

Premissas usadas (nenhum número "chutado"):
- Tamanho de chunk/overlap: os MESMOS do RAGService real
  (docksmith/service/rag.py CHUNK_SIZE/CHUNK_OVERLAP) — não duplicamos um
  valor separado que poderia desalinhar com o splitter de verdade.
- Custo de memória por chunk e overhead fixo de indexação: calibrados por
  medição real do processo rodando localmente (ver docs/10-preparacao-
  producao.md, seção "Calibração da estimativa de memória de indexação") —
  não são estimativas teóricas.
- Memória disponível/em uso: lida em tempo real via `psutil` (processo atual
  + memória livre do host/container), nunca um limite fixo inventado — os
  limiares (%) são relativos a esse valor real, então se adaptam sozinhos a
  qualquer tamanho de instância.
"""

import os
import sys
from pathlib import Path
from typing import Literal

import psutil

DOCKSMITH_DIR = Path(__file__).resolve().parent.parent / "docksmith"
if str(DOCKSMITH_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKSMITH_DIR))

from service.rag import CHUNK_SIZE, CHUNK_OVERLAP  # noqa: E402

# --- Constantes calibradas por medição real (docs/10) ---------------------
# Medição feita ao vivo no processo real (Windows, ver docs/10-preparacao-
# producao.md, seção "Calibração da estimativa de memória de indexação"):
# indexar uma coleção real de 875 chunks (docs.python.org/collections.html,
# max_depth=1) custou +133.8MB de RSS. Resolvendo custo_fixo + 875*custo_chunk
# = 133.8MB com um custo fixo conservador de 60MB (nova instância de
# RAGService/HuggingFaceEmbeddings/índice FAISS vazio) dá ~85KB/chunk.
#
# Ressalva documentada (não escondida): a PRIMEIRA indexação real depois do
# processo subir paga também um custo de "aquecimento" do torch (observado
# ~180-200MB, medido isoladamente) que não é proporcional ao tamanho da
# coleção — é por processo, não por coleção. Essa estimativa cobre o custo
# por-coleção; não tenta prever esse aquecimento único de processo.
BYTES_PER_CHUNK = 85_000

# Overhead fixo de instanciar um RAGService novo (HuggingFaceEmbeddings +
# índice FAISS vazio + buffers do langchain), independente do nº de chunks.
FIXED_INDEXING_OVERHEAD_BYTES = 60 * 1024 * 1024

# Limiares como fração da memória DISPONÍVEL no momento (não um valor fixo
# tipo "500MB") — se adaptam automaticamente a qualquer tamanho de instância.
THRESHOLD_ATENCAO = 0.25
THRESHOLD_MUITO_GRANDE = 0.55
THRESHOLD_BLOQUEADO = 0.85

Status = Literal["ok", "atencao", "muito_grande", "bloqueado"]


def estimate_chunk_count(total_chars: int) -> int:
    """Mesma lógica de passo do RecursiveCharacterTextSplitter real (chunks
    de CHUNK_SIZE caracteres, avançando CHUNK_SIZE - CHUNK_OVERLAP por vez)."""
    if total_chars <= 0:
        return 0
    step = max(CHUNK_SIZE - CHUNK_OVERLAP, 1)
    return max(1, -(-total_chars // step))  # ceil division


def resource_estimate(documents: list[str]) -> dict:
    document_count = len(documents)
    total_chars = sum(len(doc) for doc in documents)
    estimated_chunks = estimate_chunk_count(total_chars)
    estimated_indexing_bytes = FIXED_INDEXING_OVERHEAD_BYTES + estimated_chunks * BYTES_PER_CHUNK

    process = psutil.Process(os.getpid())
    current_process_bytes = process.memory_info().rss
    available_memory_bytes = psutil.virtual_memory().available

    ratio = estimated_indexing_bytes / available_memory_bytes if available_memory_bytes > 0 else 1.0
    if ratio < THRESHOLD_ATENCAO:
        status: Status = "ok"
    elif ratio < THRESHOLD_MUITO_GRANDE:
        status = "atencao"
    elif ratio < THRESHOLD_BLOQUEADO:
        status = "muito_grande"
    else:
        status = "bloqueado"

    return {
        "document_count": document_count,
        "total_chars": total_chars,
        "total_mb": round(total_chars / (1024 * 1024), 2),
        "estimated_chunks": estimated_chunks,
        "estimated_indexing_mb": round(estimated_indexing_bytes / (1024 * 1024), 1),
        "current_process_mb": round(current_process_bytes / (1024 * 1024), 1),
        "available_memory_mb": round(available_memory_bytes / (1024 * 1024), 1),
        "status": status,
    }
