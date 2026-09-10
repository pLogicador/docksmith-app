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
from api import config, rate_limit, sessions  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_r2_env(monkeypatch):
    """Isola toda a suíte do `.env` real do desenvolvedor -- sem isso, os
    testes que simulam "R2 não configurado" (patchando só 1-2 variáveis,
    ex. só `R2_ACCOUNT_ID`) quebram silenciosamente assim que credenciais
    reais existem no `.env` local (ex.: Backblaze B2, ver
    docs/CONFIGURAR_ARMAZENAMENTO.md), porque `r2_storage.is_configured()`
    passa a enxergar as OUTRAS variáveis reais que ninguém pediu pra
    apagar. Achado real, 2026-09-10: 3 testes (test_r2_storage.py +
    test_documents_endpoint.py) quebraram exatamente assim depois que
    credenciais reais do Backblaze foram configuradas nesta mesma sessão
    de trabalho -- não um cenário hipotético. Roda ANTES de qualquer
    fixture/monkeypatch que o próprio teste peça explicitamente (autouse
    sempre precede fixtures não-autouse requisitadas pela função), então
    os testes que precisam de R2 "configurado" continuam livres pra setar
    o que precisarem por cima disto."""
    for var in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_ENDPOINT_URL"):
        monkeypatch.setattr(config, var, None)
    monkeypatch.setattr(config, "R2_REGION", "auto")


@pytest.fixture(autouse=True)
def _isolate_state():
    """Cada teste começa com sessões em memória limpas, contadores de rate
    limit zerados, e sem overrides de dependência vazando pro próximo
    teste."""
    sessions._sessions.clear()
    rate_limit.reset_all()
    app.dependency_overrides.clear()
    yield
    sessions._sessions.clear()
    rate_limit.reset_all()
    app.dependency_overrides.clear()
