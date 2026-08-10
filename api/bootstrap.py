"""Ponto único de reaproveitamento da lógica existente em docksmith/service/*.

O Streamlit (docksmith/app.py) importa esses módulos como pacotes de topo
(`from service.rag import RAGService`) porque o próprio Streamlit insere o
diretório do script (docksmith/) em sys.path. A API faz a mesma coisa aqui,
manualmente, para reaproveitar exatamente o mesmo código sem duplicá-lo.
"""

import sys
from pathlib import Path

DOCKSMITH_DIR = Path(__file__).resolve().parent.parent / "docksmith"
if str(DOCKSMITH_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKSMITH_DIR))

from service.scraping import ScrapingService  # noqa: E402
from service.rag import RAGService, build_chat_llm, DEFAULT_MODELS  # noqa: E402

__all__ = ["ScrapingService", "RAGService", "build_chat_llm", "DEFAULT_MODELS"]
