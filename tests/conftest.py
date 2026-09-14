"""Fixtures dos testes da casca HTTP / fila de aprovação.

Estes testes NÃO chamam LLM/Veo: substituem o REGISTRY de ferramentas por
stubs que devolvem dados canônicos na hora. O que está sob teste é o
encanamento — gateway de fila, suspender/retomar, trava e rate limit — não
a qualidade do conteúdo.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

_BASE_TMP = tempfile.mkdtemp(prefix="agente-fila-test-")
os.environ.setdefault("AGENTE_API_KEY", "chave-de-teste-0123456789")
os.environ.setdefault("OPENAI_API_KEY", "sk-teste")           # stubs não usam, mas evita ErroConfig
os.environ.setdefault("OPENAI_MODEL_ROTEIRO", "modelo-teste")


def _perfil_tmp() -> str:
    destino = Path(_BASE_TMP) / "perfil.md"
    shutil.copy(RAIZ / "config-exemplo" / "perfil-marca.md", destino)
    return str(destino)


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    """Config isolada por teste (DB e perfil próprios) + REGISTRY stubado."""
    db = tmp_path / "agente.db"
    perfil = _perfil_tmp()
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("PERFIL_PATH", perfil)
    monkeypatch.setenv("EXEC_MAX_POR_HORA", "5")
    monkeypatch.setenv("EXEC_MAX_POR_DIA", "20")

    from api.config import carregar_config

    carregar_config.cache_clear()

    # -- stubs de ferramentas (mantém solicitar_aprovacao_humana real) --
    from runtime import executor

    stubs = {
        "buscar_insights_recentes": lambda **_: {"insights": []},
        "pesquisar_tendencias_nicho": lambda **_: {
            "tendencias": [], "temas_sugeridos": ["demora no atendimento do whatsapp"]
        },
        # varia o corpo conforme os ajustes recebidos (nº de insights) — assim
        # uma reprovação com feedback gera slides diferentes, como o modelo
        # real faria, e o hash da peça muda (nova pendência).
        "gerar_roteiro": lambda **kw: {
            "slides": [{"ordem": 1, "tipo_layout": "capa", "titulo": "gancho",
                        "corpo": f"{kw.get('tema', '')} | v{len(kw.get('insights_anteriores') or [])}"}],
            "formato": kw.get("formato", "reel"),
        },
        "autocritica_conteudo": lambda **_: {
            "aprovado_internamente": True, "ajustes_sugeridos": []
        },
        "gerar_peca_visual": lambda **kw: {
            "pecas_urls": [f"dados/pecas/{kw.get('post_id','p')}_slide1.png"]
        },
        "publicar_conteudo": lambda **_: {
            "post_id": "pub", "status": "publicado", "publicado_em": "2026-09-04T00:00:00+00:00"
        },
    }
    for nome, fn in stubs.items():
        monkeypatch.setitem(executor.REGISTRY, nome, fn)

    yield carregar_config()
    carregar_config.cache_clear()


@pytest.fixture()
def client(ambiente):
    from fastapi.testclient import TestClient

    from api.app import app

    with TestClient(app) as c:
        c.headers.update({"X-API-Key": os.environ["AGENTE_API_KEY"], "X-Chamador": "teste"})
        yield c


def esperar(fn, alvo, *, timeout=10.0, intervalo=0.05):
    """Espera fn() == alvo (ou fn() in alvo se for set/tuple)."""
    fim = time.monotonic() + timeout
    ok = (lambda v: v in alvo) if isinstance(alvo, (set, tuple, list)) else (lambda v: v == alvo)
    while time.monotonic() < fim:
        v = fn()
        if ok(v):
            return v
        time.sleep(intervalo)
    raise AssertionError(f"timeout esperando {alvo!r}; último valor: {fn()!r}")


def esperar_ate(fn, *, timeout=10.0, intervalo=0.05):
    """Espera fn() virar truthy e devolve o valor."""
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        v = fn()
        if v:
            return v
        time.sleep(intervalo)
    raise AssertionError("timeout esperando condição virar verdadeira")


def estado_execucao(client, eid):
    return client.get(f"/execucoes/{eid}").json()["estado"]


def pendentes(client):
    return client.get("/aprovacoes/pendentes").json()["pendentes"]


def proxima_pendencia(client, ja_decididas):
    """A pendência atual que ainda não foi decidida por este teste."""
    return esperar_ate(
        lambda: next((p for p in pendentes(client) if p["id"] not in ja_decididas), None)
    )


def aprovar_ate_terminar(client, eid, *, aprovado=True, feedback=""):
    ja: set[str] = set()
    for _ in range(15):
        est = esperar(lambda: estado_execucao(client, eid), {"suspensa", "finalizada", "erro"})
        if est != "suspensa":
            return est
        novos = [p for p in pendentes(client) if p["id"] not in ja]
        if not novos:
            time.sleep(0.1)
            continue
        p = novos[0]
        ja.add(p["id"])
        client.post(f"/aprovacoes/{p['id']}/decidir",
                    json={"aprovado": aprovado, "feedback": feedback})
    raise AssertionError(f"não terminou; estado={estado_execucao(client, eid)}")
