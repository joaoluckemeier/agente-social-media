"""Fluxo completo da fila de aprovação, via casca HTTP, sem LLM real."""

from __future__ import annotations

from tests.conftest import (
    aprovar_ate_terminar,
    esperar,
    estado_execucao,
    pendentes,
    proxima_pendencia,
)


def test_disparo_suspende_em_cada_aprovacao_e_finaliza(client):
    r = client.post("/execucoes", json={"entrada": "post sobre demora no whatsapp", "formato": "reel"})
    assert r.status_code == 202, r.text
    eid = r.json()["execucao_id"]
    decididas: set[str] = set()

    # suspende na aprovação do ROTEIRO
    p = proxima_pendencia(client, decididas)
    assert p["etapa"] == "roteiro" and p["execucao_id"] == eid
    assert estado_execucao(client, eid) == "suspensa"

    # trava: novo disparo enquanto há execução suspensa -> 409
    assert client.post("/execucoes", json={}).status_code == 409

    client.post(f"/aprovacoes/{p['id']}/decidir", json={"aprovado": True})
    decididas.add(p["id"])

    # decidir a MESMA aprovação de novo -> 409
    assert client.post(f"/aprovacoes/{p['id']}/decidir", json={"aprovado": True}).status_code == 409

    # VISUAL
    p = proxima_pendencia(client, decididas)
    assert p["etapa"] == "visual"
    client.post(f"/aprovacoes/{p['id']}/decidir", json={"aprovado": True})
    decididas.add(p["id"])

    # PUBLICACAO (acao_sensivel)
    p = proxima_pendencia(client, decididas)
    assert p["etapa"] == "publicacao"
    client.post(f"/aprovacoes/{p['id']}/decidir", json={"aprovado": True})
    decididas.add(p["id"])

    esperar(lambda: estado_execucao(client, eid), "finalizada")
    ex = client.get(f"/execucoes/{eid}").json()
    assert ex["motivo_parada"] == "objetivo_alcancado"
    assert ex["segundos_ativos"] < 60  # relógio pausou nas esperas humanas

    posts = client.get("/posts").json()["posts"]
    assert len(posts) == 1 and posts[0]["status_publicacao"] == "publicado"

    # trava liberada
    assert client.post("/execucoes", json={}).status_code == 202


def test_reprovar_roteiro_gera_nova_pendencia(client):
    eid = client.post("/execucoes", json={"entrada": "tema x", "formato": "reel"}).json()["execucao_id"]
    decididas: set[str] = set()

    p1 = proxima_pendencia(client, decididas)
    assert p1["etapa"] == "roteiro"
    client.post(f"/aprovacoes/{p1['id']}/decidir",
                json={"aprovado": False, "feedback": "deixa o gancho mais direto"})
    decididas.add(p1["id"])

    p2 = proxima_pendencia(client, decididas)
    assert p2["etapa"] == "roteiro"
    assert p2["id"] != p1["id"]
    assert p2["peca"]["slides"][0]["corpo"] != p1["peca"]["slides"][0]["corpo"]


def test_rate_limit_local(client, monkeypatch):
    from api.config import carregar_config

    monkeypatch.setenv("EXEC_MAX_POR_HORA", "1")
    carregar_config.cache_clear()

    eid = client.post("/execucoes", json={}).json()["execucao_id"]
    assert aprovar_ate_terminar(client, eid) == "finalizada"

    # 2º disparo na mesma hora -> 429 (1 disparo já contado)
    r = client.post("/execucoes", json={})
    assert r.status_code == 429
    assert r.json()["detail"]["janela"] == "hora"


def test_memoria_curta_nao_incha_com_retomadas(client):
    """3 suspensões/retomadas não devem estourar memory.md:max_registros (40),
    e nunca podam `resultado_de_ferramenta` (limites cumulativos dependem
    dessas linhas)."""
    import sqlite3

    from api.config import carregar_config

    eid = client.post("/execucoes", json={"entrada": "tema y"}).json()["execucao_id"]
    assert aprovar_ate_terminar(client, eid) == "finalizada"

    con = sqlite3.connect(carregar_config().db_path)
    linhas = con.execute(
        "SELECT tipo, COUNT(*) FROM memoria_curta WHERE execucao_id=? GROUP BY tipo", (eid,)
    ).fetchall()
    con.close()
    por_tipo = dict(linhas)
    total = sum(por_tipo.values())
    assert total <= 40, por_tipo
    # roteiro_aprovado: 2 checkpoints (roteiro, visual), não 1 por retomada
    assert por_tipo.get("roteiro_aprovado", 0) == 2, por_tipo
    # todas as chamadas de ferramenta continuam contabilizadas
    assert por_tipo.get("resultado_de_ferramenta", 0) >= 7, por_tipo


def test_execucao_desconhecida_404(client):
    assert client.get("/execucoes/nao-existe").status_code == 404


def test_pendentes_exige_api_key(client):
    r = client.get("/aprovacoes/pendentes", headers={"X-API-Key": "errada"})
    assert r.status_code == 401
