"""Fase I (2026-09-10) -- fachada neutra sobre api/r2_storage.py. Cada
método é um repasse direto: confirma isso chamando os 2 caminhos
(`StorageService.X` e `r2_storage.X`) e comparando o resultado, sem
reimplementar nenhuma lógica de armazenamento aqui (já coberta a fundo
em test_r2_storage.py)."""

from __future__ import annotations

from api import config, r2_storage
from api.storage_service import StorageService
from api.tests.test_r2_storage import _FakeR2Client


def _configure_r2(monkeypatch) -> _FakeR2Client:
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "acc123")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "docksmith-bucket")
    fake = _FakeR2Client()
    monkeypatch.setattr(r2_storage, "_get_client", lambda: fake)
    return fake


def test_is_configured_matches_the_real_module():
    assert StorageService.is_configured() == r2_storage.is_configured()


def test_is_configured_reflects_real_configuration_state(monkeypatch):
    _configure_r2(monkeypatch)
    assert StorageService.is_configured() is True


def test_upload_and_download_round_trip_through_the_facade(monkeypatch):
    _configure_r2(monkeypatch)

    key = StorageService.upload_raw_bytes(
        user_id="user-1", session_id="sess-1", collection_name="c", filename="a.pdf", raw_bytes=b"conteudo real",
    )
    assert key is not None

    downloaded = StorageService.download_raw_bytes(key)
    assert downloaded == b"conteudo real"

    objects = StorageService.list_session_objects(user_id="user-1", session_id="sess-1")
    assert len(objects) == 1
    assert objects[0]["filename"] == "a.pdf"

    deleted = StorageService.delete_session_objects(user_id="user-1", session_id="sess-1")
    assert deleted == 1
    assert StorageService.list_session_objects(user_id="user-1", session_id="sess-1") == []


def test_facade_is_a_no_op_when_storage_is_not_configured(monkeypatch):
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", None)
    monkeypatch.setattr(config, "R2_ENDPOINT_URL", None)

    assert StorageService.is_configured() is False
    assert StorageService.upload_raw_bytes(
        user_id="u", session_id="s", collection_name="c", filename="f.pdf", raw_bytes=b"x",
    ) is None
    assert StorageService.list_session_objects(user_id="u", session_id="s") == []
    assert StorageService.download_raw_bytes("qualquer-chave") is None
    assert StorageService.delete_session_objects(user_id="u", session_id="s") == 0
