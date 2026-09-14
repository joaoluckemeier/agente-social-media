"""Etapa 3: descartar execução (libera a trava) e perguntas abertas
(PERGUNTAR_USUARIO no modo fila)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import esperar, estado_execucao, pendentes, proxima_pendencia


def test_descartar_execucao_suspensa_libera_trava(client):
    eid = client.post("/execucoes", json={"entrada": "tema x"}).json()["execucao_id"]
    p = proxima_pendencia(client, set())
    assert p["etapa"] == "roteiro"
    assert estado_execucao(client, eid) == "suspensa"

    # trava ainda ativa
    assert client.post("/execucoes", json={}).status_code == 409

    d = client.post(f"/execucoes/{eid}/descartar")
    assert d.status_code == 200, d.text
    assert d.json()["estado"] == "descartada"

    # a pendência órfã some da fila
    assert pendentes(client) == []

    # trava liberada — novo disparo passa na hora
    r2 = client.post("/execucoes", json={})
    assert r2.status_code == 202


def test_trace_da_execucao_mais_recente(client):
    eid = client.post("/execucoes", json={"entrada": "tema x"}).json()["execucao_id"]
    proxima_pendencia(client, set())  # espera suspender
    r = client.get(f"/execucoes/{eid}/trace")
    assert r.status_code == 200
    body = r.json()
    assert body["execucao_id"] == eid
    assert len(body["eventos"]) > 0


def test_trace_execucao_antiga_404(client):
    client.post("/execucoes", json={"entrada": "tema x"}).json()["execucao_id"]
    proxima_pendencia(client, set())
    r = client.get("/execucoes/nao-e-a-mais-recente/trace")
    assert r.status_code == 404


def test_descartar_execucao_inexistente_404(client):
    r = client.post("/execucoes/nao-existe/descartar")
    assert r.status_code == 404


def test_descartar_duas_vezes_409(client):
    eid = client.post("/execucoes", json={}).json()["execucao_id"]
    esperar(lambda: estado_execucao(client, eid), "suspensa")
    assert client.post(f"/execucoes/{eid}/descartar").status_code == 200
    r2 = client.post(f"/execucoes/{eid}/descartar")
    assert r2.status_code == 409


def test_aguardando_intervencao_por_perfil_incompleto(client, ambiente):
    # perfil sem a seção obrigatória "Oferta" -> primeira decisão do
    # planejador já é PERGUNTAR_USUARIO, antes de qualquer ferramenta.
    Path(ambiente.perfil_path).write_text(
        "---\nnicho: n\nrede: instagram\ntom: t\n---\n\n"
        "## ICP\n\ntexto\n\n## Marca\n\ntexto\n",
        encoding="utf-8",
    )

    eid = client.post("/execucoes", json={}).json()["execucao_id"]
    esperar(lambda: estado_execucao(client, eid), "aguardando_intervencao")

    ex = client.get(f"/execucoes/{eid}").json()
    assert ex["motivo_parada"] == "aguardando_intervencao_operador"
    assert "Oferta" in (ex["pergunta_aberta"] or "")

    ag = client.get("/execucoes/aguardando").json()["execucoes"]
    assert any(e["execucao_id"] == eid for e in ag)

    # aguardando_intervencao TAMBÉM segura a trava — sem isso o cliente
    # ficaria disparando execuções contra o mesmo perfil quebrado.
    assert client.post("/execucoes", json={}).status_code == 409

    # descartar libera; sem corrigir o perfil, a próxima cai no mesmo lugar
    assert client.post(f"/execucoes/{eid}/descartar").status_code == 200
    r2 = client.post("/execucoes", json={})
    assert r2.status_code == 202
