"""Testes de api/config.py que precisam de um processo Python isolado --
`DOCSMITH_MAX_FILE_SIZE_MB` é lido e travado no teto de uma vez, na
importação do módulo (`os.getenv(...)` roda 1x, no import). Testar isso
dentro do mesmo processo do pytest exigiria `importlib.reload(config)`,
que muta o MESMO objeto de módulo já importado por todo o resto da
suíte (`from api import config` em vários arquivos) -- arriscando
contaminar outros testes que rodam depois, na mesma sessão. Um
subprocesso isolado evita esse risco por completo: nada aqui pode vazar
pro resto da suíte.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_config_value_in_a_fresh_process(env_overrides: dict[str, str] | None = None) -> str:
    env = os.environ.copy()
    # Garante que nenhum valor ambiente do processo do pytest vaze pro
    # subprocesso por acidente -- cada teste controla explicitamente o
    # que está (ou não) definido.
    env.pop("DOCSMITH_MAX_FILE_SIZE_MB", None)
    env.update(env_overrides or {})
    result = subprocess.run(
        [sys.executable, "-c", "from api import config; print(config.DOCSMITH_MAX_FILE_SIZE_MB)"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"processo falhou: {result.stderr}"
    return result.stdout.strip()


def test_max_file_size_defaults_to_20mb_without_any_configuration():
    assert _read_config_value_in_a_fresh_process() == "20"


def test_max_file_size_respects_a_reasonable_configured_value():
    value = _read_config_value_in_a_fresh_process({"DOCSMITH_MAX_FILE_SIZE_MB": "200"})
    assert value == "200"


def test_max_file_size_is_clamped_to_the_300mb_hard_cap_even_if_misconfigured():
    """2026-09-02, 5ª rodada: nenhum valor de env var, por maior que seja,
    passa do teto de 300MB por arquivo (reduzido de 1GB nesta rodada,
    pensando na capacidade real do R2 -- ver as cotas por usuário/bucket
    abaixo) -- protege memória do processo e o nível gratuito do R2 de
    uma sessão maliciosa/erroneamente configurada."""
    value = _read_config_value_in_a_fresh_process({"DOCSMITH_MAX_FILE_SIZE_MB": "999999"})
    assert value == "300"


def _read_r2_quota_bytes(var_name: str, env_overrides: dict[str, str] | None = None) -> str:
    env = os.environ.copy()
    env.pop("DOCSMITH_R2_MAX_MB_PER_USER", None)
    env.pop("DOCSMITH_R2_MAX_MB_TOTAL_BUCKET", None)
    env.update(env_overrides or {})
    result = subprocess.run(
        [sys.executable, "-c", f"from api import config; print(config.{var_name})"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"processo falhou: {result.stderr}"
    return result.stdout.strip()


def test_r2_per_user_quota_defaults_to_1gb_in_bytes():
    assert _read_r2_quota_bytes("R2_MAX_BYTES_PER_USER") == str(1024 * 1024 * 1024)


def test_r2_total_bucket_quota_defaults_to_6gb_in_bytes():
    assert _read_r2_quota_bytes("R2_MAX_TOTAL_BUCKET_BYTES") == str(6144 * 1024 * 1024)


def test_r2_quotas_are_configurable():
    value = _read_r2_quota_bytes(
        "R2_MAX_BYTES_PER_USER", {"DOCSMITH_R2_MAX_MB_PER_USER": "50"}
    )
    assert value == str(50 * 1024 * 1024)
