"""api/r2_storage.py -- armazenamento durável opcional em Cloudflare R2
(2026-09-02, 4ª rodada, resolve "documentos ainda somem a cada reinício do
servidor"). Testado contra um client S3 falso com estado real em memória
(`_FakeR2Client` abaixo), não uma sequência engessada de `MagicMock`
retornos -- mesma filosofia de teste já usada no projeto pra dependências
externas (`_FakeLLM` em docksmith/tests/test_query_engine.py): as 5
operações reais (put/list/head/get/delete) se comportam de verdade dentro
do teste, então um bug real de lógica (ex.: prefixo errado, metadado não
decodificado) se manifesta como uma asserção falhando, não como "o mock
foi chamado com os argumentos certos" sozinho.
"""

from __future__ import annotations

import io

import pytest

from api import config, r2_storage

# `_reset_r2_env` (autouse, isola esta suíte do `.env` real do
# desenvolvedor) vive em api/tests/conftest.py -- compartilhada com
# test_documents_endpoint.py, que tem o mesmo padrão de testes "R2 não
# configurado". Ver o docstring da fixture lá pro achado real que motivou.


class _FakeR2Client:
    """Emula só as 5 operações que api/r2_storage.py usa, com estado real
    em memória do processo de teste."""

    def __init__(self):
        self.objects: dict[str, dict] = {}

    def put_object(self, *, Bucket, Key, Body, Metadata=None):
        self.objects[Key] = {"Body": Body, "Metadata": Metadata or {}}

    def list_objects_v2(self, *, Bucket, Prefix=""):
        matching = [k for k in self.objects if k.startswith(Prefix)]
        return {"Contents": [{"Key": k, "Size": len(self.objects[k]["Body"])} for k in matching]}

    def head_object(self, *, Bucket, Key):
        return {"Metadata": self.objects[Key]["Metadata"]}

    def get_object(self, *, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key]["Body"])}

    def delete_objects(self, *, Bucket, Delete):
        for item in Delete["Objects"]:
            self.objects.pop(item["Key"], None)


class _FailingR2Client:
    """Simula qualquer chamada de rede falhando (credencial errada, R2
    fora do ar, timeout) -- toda função pública de r2_storage.py precisa
    engolir isso e devolver um valor "vazio", nunca propagar."""

    def __getattr__(self, name):
        def _raise(*args, **kwargs):
            raise RuntimeError("falha simulada de rede/credencial")

        return _raise


@pytest.fixture
def configured(monkeypatch):
    """R2 'configurado' -- as 4 variáveis presentes -- com um client falso
    injetado no lugar do boto3 real."""
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "acc123")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "docksmith-bucket")
    fake = _FakeR2Client()
    monkeypatch.setattr(r2_storage, "_get_client", lambda: fake)
    return fake


# ===== is_configured =====


def test_is_configured_is_false_by_default(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", None)
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", None)
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", None)
    monkeypatch.setattr(config, "R2_BUCKET_NAME", None)
    assert r2_storage.is_configured() is False


def test_is_configured_is_false_when_only_some_variables_are_set(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "acc123")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", None)
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", None)
    monkeypatch.setattr(config, "R2_BUCKET_NAME", None)
    assert r2_storage.is_configured() is False


def test_is_configured_is_true_with_all_four_variables(configured):
    assert r2_storage.is_configured() is True


# ===== provedor alternativo via R2_ENDPOINT_URL (2026-09-03 -- Backblaze B2
# ou qualquer outro S3-compatível, sem exigir R2_ACCOUNT_ID) =====


def test_is_configured_is_true_with_endpoint_url_instead_of_account_id(monkeypatch):
    """Backblaze B2 (e provedores S3-compatíveis em geral) não têm um
    "account id" que vira parte do endpoint como o R2 -- o endpoint já vem
    pronto (ex.: https://s3.us-west-004.backblazeb2.com). R2_ENDPOINT_URL
    cobre esse caso sem precisar de R2_ACCOUNT_ID."""
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", None)
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "b2-key-id")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "b2-app-key")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "docksmith-bucket")
    monkeypatch.setattr(config, "R2_ENDPOINT_URL", "https://s3.us-west-004.backblazeb2.com")
    assert r2_storage.is_configured() is True


def test_is_configured_is_false_without_either_account_id_or_endpoint_url(monkeypatch):
    """Credencial+bucket sozinhos não bastam -- sem R2_ACCOUNT_ID nem
    R2_ENDPOINT_URL não há como saber pra qual host boto3 deve conectar."""
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", None)
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "bucket")
    monkeypatch.setattr(config, "R2_ENDPOINT_URL", None)
    assert r2_storage.is_configured() is False


def test_get_client_prefers_endpoint_url_over_account_id_derived_endpoint(monkeypatch):
    """Com os 2 presentes, R2_ENDPOINT_URL sempre vence -- é o que permite
    trocar de provedor sem precisar apagar R2_ACCOUNT_ID."""
    monkeypatch.setattr(r2_storage, "_client", None)
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "conta-cloudflare")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "bucket")
    monkeypatch.setattr(config, "R2_ENDPOINT_URL", "https://s3.us-west-004.backblazeb2.com")
    monkeypatch.setattr(config, "R2_REGION", "us-west-004")

    captured = {}

    class _FakeBoto3Module:
        @staticmethod
        def client(_service, **kwargs):
            captured.update(kwargs)
            return object()

    monkeypatch.setitem(__import__("sys").modules, "boto3", _FakeBoto3Module())
    r2_storage._get_client()
    assert captured["endpoint_url"] == "https://s3.us-west-004.backblazeb2.com"
    assert captured["region_name"] == "us-west-004"


# ===== graceful no-op quando não configurado (comportamento sem custo/risco) =====


def test_upload_is_a_safe_no_op_when_not_configured(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", None)
    result = r2_storage.upload_raw_bytes(
        user_id="u1", session_id="s1", collection_name="c1", filename="a.pdf", raw_bytes=b"conteudo"
    )
    assert result is None


def test_list_is_empty_when_not_configured(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", None)
    assert r2_storage.list_session_objects(user_id="u1", session_id="s1") == []


def test_download_is_none_when_not_configured(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", None)
    assert r2_storage.download_raw_bytes("qualquer-chave") is None


def test_delete_is_zero_when_not_configured(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", None)
    assert r2_storage.delete_session_objects(user_id="u1", session_id="s1") == 0


# ===== fluxo real: upload -> list -> download -> delete =====


def test_upload_then_list_then_download_round_trip(configured):
    key = r2_storage.upload_raw_bytes(
        user_id="user-1", session_id="sess-1", collection_name="manual", filename="manual.pdf",
        raw_bytes=b"pdf de verdade aqui",
    )
    assert key is not None

    objects = r2_storage.list_session_objects(user_id="user-1", session_id="sess-1")
    assert len(objects) == 1
    assert objects[0]["collection_name"] == "manual"
    assert objects[0]["filename"] == "manual.pdf"

    downloaded = r2_storage.download_raw_bytes(objects[0]["key"])
    assert downloaded == b"pdf de verdade aqui"


def test_upload_preserves_special_characters_in_filename_and_collection(configured):
    """Metadado passa por `quote`/`unquote` (ver r2_storage.py) -- confirma
    que nome de arquivo/coleção com espaço/acento sobrevive ao round-trip
    (S3/R2 metadata só aceita ASCII nos headers HTTP reais)."""
    r2_storage.upload_raw_bytes(
        user_id="user-1", session_id="sess-1", collection_name="relatório final",
        filename="relatório 2026 (v2).pdf", raw_bytes=b"x",
    )
    objects = r2_storage.list_session_objects(user_id="user-1", session_id="sess-1")
    assert objects[0]["collection_name"] == "relatório final"
    assert objects[0]["filename"] == "relatório 2026 (v2).pdf"


def test_list_is_empty_for_a_session_with_no_uploads(configured):
    assert r2_storage.list_session_objects(user_id="user-1", session_id="sess-nunca-usada") == []


def test_delete_removes_only_the_target_sessions_objects(configured):
    r2_storage.upload_raw_bytes(
        user_id="user-1", session_id="sess-a", collection_name="c", filename="a.pdf", raw_bytes=b"a"
    )
    r2_storage.upload_raw_bytes(
        user_id="user-1", session_id="sess-b", collection_name="c", filename="b.pdf", raw_bytes=b"b"
    )
    deleted = r2_storage.delete_session_objects(user_id="user-1", session_id="sess-a")
    assert deleted == 1
    assert r2_storage.list_session_objects(user_id="user-1", session_id="sess-a") == []
    # sessão irmã (sess-b) intocada -- a faxina de uma sessão nunca apaga
    # objetos de outra.
    assert len(r2_storage.list_session_objects(user_id="user-1", session_id="sess-b")) == 1


def test_delete_returns_zero_when_nothing_exists(configured):
    assert r2_storage.delete_session_objects(user_id="user-1", session_id="sess-vazia") == 0


# ===== isolamento real entre usuários (segurança: session_id reaproveitado) =====


def test_a_different_user_id_never_sees_another_users_session_objects(configured):
    """O mesmo `session_id` (ex.: reaproveitado/adivinhado) nunca dá acesso
    aos documentos de outra pessoa -- o prefixo do objeto inclui o hash do
    `user_id` de quem UPLOADOU, e a listagem usa o hash do `user_id` de
    quem está PERGUNTANDO agora. Se forem pessoas diferentes, os hashes
    nunca coincidem."""
    r2_storage.upload_raw_bytes(
        user_id="dono-real", session_id="sess-compartilhada", collection_name="c",
        filename="confidencial.pdf", raw_bytes=b"segredo",
    )
    # mesmo session_id, user_id diferente
    objects_as_attacker = r2_storage.list_session_objects(user_id="outra-pessoa", session_id="sess-compartilhada")
    assert objects_as_attacker == []

    # o dono de verdade continua enxergando normalmente
    objects_as_owner = r2_storage.list_session_objects(user_id="dono-real", session_id="sess-compartilhada")
    assert len(objects_as_owner) == 1


# ===== tolerância a falha de rede/credencial (nunca propaga exceção) =====


def test_upload_never_raises_when_the_network_call_fails(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "acc")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "bucket")
    monkeypatch.setattr(r2_storage, "_get_client", lambda: _FailingR2Client())

    result = r2_storage.upload_raw_bytes(
        user_id="u1", session_id="s1", collection_name="c1", filename="a.pdf", raw_bytes=b"x"
    )
    assert result is None  # nunca levanta, mesmo com a "rede" falhando


def test_list_never_raises_when_the_network_call_fails(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "acc")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "bucket")
    monkeypatch.setattr(r2_storage, "_get_client", lambda: _FailingR2Client())

    assert r2_storage.list_session_objects(user_id="u1", session_id="s1") == []


def test_delete_never_raises_when_the_network_call_fails(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "acc")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "bucket")
    monkeypatch.setattr(r2_storage, "_get_client", lambda: _FailingR2Client())

    assert r2_storage.delete_session_objects(user_id="u1", session_id="s1") == 0


# ===== cotas de segurança (2026-09-02, 5ª rodada -- "nunca mandar 10GB pro
# R2"): por usuário e global do bucket, checadas ANTES de cada upload. As
# 2 nunca bloqueiam o upload do documento em si -- só pulam a cópia de
# segurança daquela vez, sem quebrar nada. =====


def test_upload_within_the_per_user_quota_succeeds(configured, monkeypatch):
    monkeypatch.setattr(config, "R2_MAX_BYTES_PER_USER", 1000)
    key = r2_storage.upload_raw_bytes(
        user_id="user-1", session_id="s1", collection_name="c", filename="a.pdf", raw_bytes=b"x" * 500,
    )
    assert key is not None


def test_upload_that_would_exceed_the_per_user_quota_is_skipped(configured, monkeypatch):
    monkeypatch.setattr(config, "R2_MAX_BYTES_PER_USER", 1000)
    # já usa 800 de 1000 -- o próximo arquivo (500) estouraria a cota
    r2_storage.upload_raw_bytes(
        user_id="user-1", session_id="s1", collection_name="c", filename="a.pdf", raw_bytes=b"x" * 800,
    )
    key = r2_storage.upload_raw_bytes(
        user_id="user-1", session_id="s2", collection_name="c", filename="b.pdf", raw_bytes=b"y" * 500,
    )
    assert key is None
    # o 1º upload (dentro da cota) continua lá -- só o 2º foi pulado
    assert len(r2_storage.list_session_objects(user_id="user-1", session_id="s1")) == 1
    assert r2_storage.list_session_objects(user_id="user-1", session_id="s2") == []


def test_per_user_quota_counts_across_multiple_sessions_of_the_same_user(configured, monkeypatch):
    """A cota é por USUÁRIO, não por sessão -- a mesma pessoa não consegue
    contornar o limite abrindo várias sessões."""
    monkeypatch.setattr(config, "R2_MAX_BYTES_PER_USER", 1000)
    r2_storage.upload_raw_bytes(
        user_id="user-1", session_id="sessao-a", collection_name="c", filename="a.pdf", raw_bytes=b"x" * 600,
    )
    key = r2_storage.upload_raw_bytes(
        user_id="user-1", session_id="sessao-b", collection_name="c", filename="b.pdf", raw_bytes=b"y" * 600,
    )
    assert key is None  # 600 + 600 = 1200, estoura os 1000 da cota da mesma conta


def test_per_user_quota_never_affects_a_different_user(configured, monkeypatch):
    monkeypatch.setattr(config, "R2_MAX_BYTES_PER_USER", 1000)
    r2_storage.upload_raw_bytes(
        user_id="user-cheio", session_id="s1", collection_name="c", filename="a.pdf", raw_bytes=b"x" * 900,
    )
    # user-vazio nunca usou nada -- a cota de outra conta não afeta a dele
    key = r2_storage.upload_raw_bytes(
        user_id="user-vazio", session_id="s1", collection_name="c", filename="b.pdf", raw_bytes=b"y" * 900,
    )
    assert key is not None


def test_upload_that_would_exceed_the_global_bucket_quota_is_skipped_even_within_the_user_quota(
    configured, monkeypatch
):
    """A cota global é a rede de segurança final -- mesmo uma conta bem
    dentro da SUA PRÓPRIA cota individual pode ser barrada se o bucket
    inteiro (somando todos os usuários) já estiver perto do limite."""
    monkeypatch.setattr(config, "R2_MAX_BYTES_PER_USER", 10_000)  # bem folgado, não é o gargalo deste teste
    monkeypatch.setattr(config, "R2_MAX_TOTAL_BUCKET_BYTES", 1000)

    r2_storage.upload_raw_bytes(
        user_id="user-a", session_id="s1", collection_name="c", filename="a.pdf", raw_bytes=b"x" * 900,
    )
    key = r2_storage.upload_raw_bytes(
        user_id="user-b", session_id="s1", collection_name="c", filename="b.pdf", raw_bytes=b"y" * 500,
    )
    assert key is None  # 900 (user-a) + 500 (user-b) estouraria os 1000 globais


def test_skipping_a_backup_for_quota_never_raises(configured, monkeypatch):
    """Estourar a cota é um resultado normal e esperado (`None`), não uma
    falha -- nunca levanta exceção, mesmo checagem de quota tendo suas
    próprias chamadas de rede (list_objects_v2) que também poderiam, em
    teoria, falhar."""
    monkeypatch.setattr(config, "R2_MAX_BYTES_PER_USER", 1)
    key = r2_storage.upload_raw_bytes(
        user_id="user-1", session_id="s1", collection_name="c", filename="a.pdf", raw_bytes=b"x" * 100,
    )
    assert key is None
