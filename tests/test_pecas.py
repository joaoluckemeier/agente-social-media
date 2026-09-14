"""GET /pecas/{arquivo} — serve o PNG real; nunca um path de disco cru."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.config import carregar_config
from runtime.memoria import SQLiteMemoriaRepository
from tests.conftest import esperar, estado_execucao, pendentes, proxima_pendencia

_PNG_MINIMO = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture()
def pasta_pecas_real():
    caminho = carregar_config().agente_dir / "dados" / "pecas"
    caminho.mkdir(parents=True, exist_ok=True)
    criados: list[Path] = []
    yield caminho, criados
    for p in criados:
        p.unlink(missing_ok=True)


def _dispara_ate_visual(client) -> tuple[str, str]:
    """Sobe uma execução até a aprovação de VISUAL (gerar_peca_visual já
    rodou nesse ponto) e devolve (execucao_id, arquivo_da_peca)."""
    eid = client.post("/execucoes", json={"entrada": "tema pecas"}).json()["execucao_id"]
    decididas: set[str] = set()
    p = proxima_pendencia(client, decididas)
    assert p["etapa"] == "roteiro"
    client.post(f"/aprovacoes/{p['id']}/decidir", json={"aprovado": True})
    decididas.add(p["id"])
    p = proxima_pendencia(client, decididas)
    assert p["etapa"] == "visual"
    arquivo = p["peca"]["pecas_urls"][0].rsplit("/", 1)[-1]
    return eid, arquivo


def test_serve_peca_registrada_e_reescreve_url_na_fila(client, pasta_pecas_real):
    pasta, criados = pasta_pecas_real
    eid, arquivo = _dispara_ate_visual(client)
    caminho = pasta / arquivo
    caminho.write_bytes(_PNG_MINIMO)
    criados.append(caminho)

    # a fila já devolve /pecas/<arquivo>, não o path de disco
    pend = pendentes(client)
    assert pend[0]["peca"]["pecas_urls"][0] == f"/pecas/{arquivo}"

    r = client.get(f"/pecas/{arquivo}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == _PNG_MINIMO
    _ = eid


def test_nome_fora_do_padrao_400(client):
    for ruim in (
        "../../etc/passwd",
        "post_x_slide1.jpg",
        "post_x_sliden.png",
        "post_x_slide1.png.exe",
        "post_x_slide1.PNG",  # maiúsculo — fora do padrão exato
        "",
    ):
        r = client.get(f"/pecas/{ruim}")
        assert r.status_code in (400, 404), (ruim, r.status_code)
        # nunca 200 pra nome fora do formato
        assert r.status_code != 200


def test_nome_bem_formado_mas_nao_registrado_404(client, pasta_pecas_real):
    """Mesmo que o arquivo exista fisicamente em disco, sem estar registrado
    no banco (posts/aprovações/memória) a rota recusa — nunca 'existe na
    pasta' sozinho."""
    pasta, criados = pasta_pecas_real
    arquivo = "post_2020_01_01_deadbe_slide9.png"
    caminho = pasta / arquivo
    caminho.write_bytes(_PNG_MINIMO)
    criados.append(caminho)

    r = client.get(f"/pecas/{arquivo}")
    assert r.status_code == 404


def test_nome_registrado_mas_arquivo_ausente_404(client):
    eid, arquivo = _dispara_ate_visual(client)
    # não escreve o arquivo em disco — está "registrado" (memoria_curta tem
    # o resultado_de_ferramenta) mas o PNG não existe
    r = client.get(f"/pecas/{arquivo}")
    assert r.status_code == 404
    _ = eid


def test_sem_api_key_401(client):
    r = client.get("/pecas/post_x_slide1.png", headers={"X-API-Key": "errada"})
    assert r.status_code == 401


def test_path_traversal_bloqueado_mesmo_burlando_o_regex(pasta_pecas_real):
    """Defesa em profundidade: chama obter_peca_bytes diretamente (pulando o
    regex da rota) com um nome que, teoricamente, resolveria pra fora de
    dados/pecas/ — a checagem de containment tem que barrar de qualquer jeito."""
    from api.servico_agente import PecaInvalida, obter_peca_bytes

    config = carregar_config()
    with pytest.raises(PecaInvalida):
        obter_peca_bytes(config, "../../../../etc/passwd.png")


def test_peca_registrada_via_memoria_curta_antes_de_virar_post(tmp_path):
    """peca_registrada() enxerga uma peça só de resultado_de_ferramenta, sem
    precisar que a execução tenha terminado (virado post) nem que exista
    aprovação — é o caso normal (aprovação pendente ainda não decidida).

    Repositório isolado num DB próprio (tmp_path) — nunca toca no banco
    real, nem depende de carregar_config()/cache entre testes."""
    repo = SQLiteMemoriaRepository(tmp_path / "isolado.db")
    try:
        assert repo.peca_registrada("post_teste_isolado_slide1.png") is False
        repo.guardar_memoria(
            "exec_teste_isolado", "resultado_de_ferramenta",
            {"ferramenta": "gerar_peca_visual",
             "saida": {"pecas_urls": ["/home/x/dados/pecas/post_teste_isolado_slide1.png"]}},
        )
        assert repo.peca_registrada("post_teste_isolado_slide1.png") is True
        assert repo.peca_registrada("post_teste_isolado_slide2.png") is False
    finally:
        repo.close()
