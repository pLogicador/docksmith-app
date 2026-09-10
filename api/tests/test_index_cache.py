"""Testes unitários de api/index_cache.py (Fase E, 2026-09-10) -- puro,
sem FastAPI/sessions envolvidos, só o dict e as funções."""

from api import index_cache


def _entry(mb: float, chunks: int, last_used: float) -> dict:
    return {"rag_service": object(), "estimated_mb": mb, "chunk_count": chunks, "last_used": last_used}


def test_total_indexed_mb_and_chunks_sum_all_entries():
    loaded = {
        ("a",): _entry(100.0, 500, 1.0),
        ("b",): _entry(50.0, 200, 2.0),
    }
    assert index_cache.total_indexed_mb(loaded) == 150.0
    assert index_cache.total_indexed_chunks(loaded) == 700


def test_evict_to_fit_does_nothing_when_everything_already_fits():
    loaded = {("a",): _entry(100.0, 500, 1.0)}
    evicted = index_cache.evict_to_fit(loaded, incoming_mb=50.0, max_mb=800, max_entries=3)
    assert evicted == []
    assert ("a",) in loaded


def test_evict_to_fit_removes_least_recently_used_when_memory_teto_estoura():
    loaded = {
        ("velha",): _entry(300.0, 100, last_used=1.0),  # menos usada recentemente
        ("nova",): _entry(300.0, 100, last_used=5.0),
    }
    # 600MB residentes + 300MB novos = 900MB > 800MB de teto -- precisa evictar 1.
    evicted = index_cache.evict_to_fit(loaded, incoming_mb=300.0, max_mb=800, max_entries=10)
    assert evicted == [("velha",)]
    assert ("velha",) not in loaded
    assert ("nova",) in loaded


def test_evict_to_fit_removes_by_count_even_when_memory_has_room():
    """Achado do usuário ("AJUSTES FINAIS"): teto de QUANTIDADE é
    independente do de memória -- mesmo com memória de sobra, nunca
    ultrapassa `max_entries`."""
    loaded = {
        ("a",): _entry(1.0, 10, last_used=1.0),
        ("b",): _entry(1.0, 10, last_used=2.0),
        ("c",): _entry(1.0, 10, last_used=3.0),
    }
    # Memória sobra à vontade (800MB de teto, só 3MB residentes) -- mas
    # max_entries=3 já está no limite, adicionar mais 1 estoura por
    # quantidade.
    evicted = index_cache.evict_to_fit(loaded, incoming_mb=1.0, max_mb=800, max_entries=3)
    assert evicted == [("a",)]  # a mais antiga por last_used
    assert len(loaded) == 2


def test_evict_to_fit_can_evict_multiple_entries_to_fit_a_big_incoming_one():
    loaded = {
        ("a",): _entry(100.0, 10, last_used=1.0),
        ("b",): _entry(100.0, 10, last_used=2.0),
        ("c",): _entry(100.0, 10, last_used=3.0),
    }
    evicted = index_cache.evict_to_fit(loaded, incoming_mb=750.0, max_mb=800, max_entries=10)
    # 300MB residentes + 750MB novo = 1050MB -- precisa evictar a e b (LRU
    # primeiro) até caber: depois de evictar "a" (200+750=950>800, ainda
    # não cabe), depois "b" (100+750=850>800, ainda não cabe), depois "c"
    # (0+750=750<=800, cabe).
    assert evicted == [("a",), ("b",), ("c",)]
    assert loaded == {}


def test_evict_to_fit_never_raises_even_when_incoming_alone_exceeds_the_cap():
    """Nunca bloqueia -- na pior hipótese, esvazia o cache inteiro e
    segue em frente (quem decide bloquear ou não é o bloqueio de
    resource_estimate, uma camada acima, não este módulo)."""
    loaded = {("a",): _entry(50.0, 10, last_used=1.0)}
    evicted = index_cache.evict_to_fit(loaded, incoming_mb=900.0, max_mb=800, max_entries=10)
    assert evicted == [("a",)]
    assert loaded == {}


def test_evict_to_fit_uses_config_defaults_when_not_overridden():
    from api import config

    loaded = {}
    # incoming bem pequeno, dentro dos defaults reais -- não deve evictar
    # nada (defaults: 800MB / 3 coleções).
    evicted = index_cache.evict_to_fit(loaded, incoming_mb=1.0)
    assert evicted == []
    assert config.DOCSMITH_MAX_SESSION_INDEX_MB > 0
    assert config.DOCSMITH_MAX_CACHED_COLLECTIONS > 0


def test_invalidate_collection_removes_every_entry_for_that_single_collection_name():
    loaded = {
        ("manual", "groq", None, False, "equilibrada"): _entry(10.0, 5, 1.0),
        ("manual", "openai", None, True, "profunda"): _entry(10.0, 5, 2.0),
        ("outra", "groq", None, False, "equilibrada"): _entry(10.0, 5, 3.0),
    }
    removed = index_cache.invalidate_collection(loaded, "manual")
    assert len(removed) == 2
    assert list(loaded.keys()) == [("outra", "groq", None, False, "equilibrada")]


def test_invalidate_collection_matches_inside_a_multicontext_tuple_key():
    """Fase H (multicontexto): a signature-key pode ter uma TUPLA de
    nomes de coleção como 1º elemento -- invalidar 1 delas precisa
    invalidar a entrada combinada inteira também."""
    loaded = {
        (("manual", "guia"), "groq", None, False, "equilibrada"): _entry(20.0, 10, 1.0),
        (("outra",), "groq", None, False, "equilibrada"): _entry(5.0, 5, 2.0),
    }
    removed = index_cache.invalidate_collection(loaded, "guia")
    assert removed == [(("manual", "guia"), "groq", None, False, "equilibrada")]
    assert (("outra",), "groq", None, False, "equilibrada") in loaded


def test_invalidate_collection_is_a_no_op_when_nothing_matches():
    loaded = {("a",): _entry(1.0, 1, 1.0)}
    removed = index_cache.invalidate_collection(loaded, "b")
    assert removed == []
    assert loaded == {("a",): loaded[("a",)]}
