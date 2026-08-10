"""Configuração compartilhada dos testes da api/.

Escopo desta suíte: só os fluxos críticos antes do primeiro deploy —
autenticação, isolamento entre sessões/usuários, e os endpoints principais
com as dependências pesadas (scraping real, chamadas a provedores de IA)
mockadas. Não é uma suíte de cobertura ampla — ver docs/10 pra critério.
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Garante que `from api import ...` resolve independente de onde o pytest
# for invocado (rootdir de teste vs raiz do projeto).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Precisa ser setado ANTES do primeiro `import api...` (api/config.py lê a
# env var na importação). Usado só pelo teste específico de bypass — os
# demais testes de auth mockam a validação normal via subscription_access_api.
os.environ.setdefault("DOCKSMITH_API_DEV_BYPASS_AUTH", "true")

from api.main import app  # noqa: E402
from api import sessions  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_state():
    """Cada teste começa com sessões em memória limpas e sem overrides de
    dependência vazando pro próximo teste."""
    sessions._sessions.clear()
    app.dependency_overrides.clear()
    yield
    sessions._sessions.clear()
    app.dependency_overrides.clear()
