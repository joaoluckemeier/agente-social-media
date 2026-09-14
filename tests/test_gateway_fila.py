"""Testes unitários do GatewayAprovacaoFila e do relógio que pausa."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from runtime.aprovacao import RunSuspensa
from runtime.aprovacao.base import chave_peca
from runtime.aprovacao.gateway_fila import GatewayAprovacaoFila
from runtime.memoria import SQLiteMemoriaRepository


@pytest.fixture()
def repo():
    d = tempfile.mkdtemp()
    r = SQLiteMemoriaRepository(Path(d) / "t.db")
    yield r
    r.close()


def test_suspende_ate_haver_decisao(repo):
    g = GatewayAprovacaoFila(repo)
    peca = {"tema": "x", "slides": [{"ordem": 1, "titulo": "a"}]}

    with pytest.raises(RunSuspensa) as ei:
        g.solicitar_aprovacao(execucao_id="e1", peca=peca, etapa="roteiro")
    apid = ei.value.aprovacao_id

    repo.registrar_decisao_aprovacao(apid, aprovado=True, feedback="", decidido_por="t")
    assert g.solicitar_aprovacao(execucao_id="e1", peca=peca, etapa="roteiro") == {
        "aprovado": True, "feedback": ""
    }


def test_peca_diferente_nova_pendencia(repo):
    g = GatewayAprovacaoFila(repo)
    with pytest.raises(RunSuspensa) as e1:
        g.solicitar_aprovacao(execucao_id="e1", peca={"v": 1}, etapa="roteiro")
    repo.registrar_decisao_aprovacao(e1.value.aprovacao_id, aprovado=False,
                                     feedback="muda", decidido_por="t")
    with pytest.raises(RunSuspensa) as e2:
        g.solicitar_aprovacao(execucao_id="e1", peca={"v": 2}, etapa="roteiro")
    assert e2.value.aprovacao_id != e1.value.aprovacao_id
    assert len(repo.listar_aprovacoes_pendentes()) == 1


def test_confirmar_acao_sensivel_usa_etapa_publicacao(repo):
    g = GatewayAprovacaoFila(repo)
    with pytest.raises(RunSuspensa) as ei:
        g.confirmar_acao_sensivel(execucao_id="e1", nome_ferramenta="publicar_conteudo",
                                  argumentos={"pecas_urls": ["a.png"]})
    assert ei.value.etapa == "publicacao"
    reg = repo.buscar_aprovacao_por_id(ei.value.aprovacao_id)
    assert reg["etapa"] == "publicacao"


def test_decisao_dupla_falha(repo):
    ap = repo.registrar_aprovacao_pendente(
        execucao_id="e1", etapa="roteiro", chave_peca=chave_peca({"a": 1}), peca={"a": 1}
    )
    repo.registrar_decisao_aprovacao(ap, aprovado=True, feedback="", decidido_por="t")
    with pytest.raises(ValueError):
        repo.registrar_decisao_aprovacao(ap, aprovado=False, feedback="", decidido_por="t")


def test_relogio_exclui_espera_humana(repo, monkeypatch):
    """segundos_ja_gastos + tempo ativo do segmento; a espera fica de fora."""
    from runtime import ciclo

    # perfil válido mínimo
    from runtime.perfil_loader import PerfilMarca

    perfil = PerfilMarca(
        caminho=Path("x"), nicho="n", rede="instagram", tom="t",
        secoes={"ICP": "i", "Marca": "m", "Oferta": "1. o"}, texto_completo="",
    )

    # relógio controlado
    t = {"agora": 1000.0}
    monkeypatch.setattr(ciclo.time, "monotonic", lambda: t["agora"])

    # força a 1ª ferramenta a "suspender" na hora
    def suspende(**_):
        raise RunSuspensa(execucao_id="e1", etapa="roteiro", aprovacao_id="ap1")

    from runtime import executor

    monkeypatch.setitem(executor.REGISTRY, "buscar_insights_recentes", suspende)

    repo.criar_execucao_ativa("e1", entrada="tema", formato="reel")
    trace = ciclo.Trace(execucao_id="e1", caminho_arquivo=Path(tempfile.mkdtemp()) / "tr.json")

    # começa com 100s já gastos; passa 3s de processamento antes de suspender
    t["agora"] = 1000.0
    def avanca_e_suspende(**_):
        t["agora"] += 3.0
        raise RunSuspensa(execucao_id="e1", etapa="roteiro", aprovacao_id="ap1")
    monkeypatch.setitem(executor.REGISTRY, "buscar_insights_recentes", avanca_e_suspende)

    with pytest.raises(RunSuspensa) as ei:
        ciclo.executar_ciclo(
            execucao_id="e1", entrada="tema", perfil=perfil, memoria=repo, trace=trace,
            formato="reel", gateway=GatewayAprovacaoFila(repo), segundos_ja_gastos=100.0,
        )
    # 100 já gastos + 3 do segmento = 103 — a "espera" (que seria horas) não conta
    assert 102.0 <= ei.value.segundos_ativos <= 104.0
