"""api/media.py — reescreve caminho de disco de peça visual pra URL servida
por GET /pecas/{arquivo}.

`decisoes-de-engenharia.md` (via `geracao_visual/base_estrategia.py`) já
registrava essa lacuna: skills.md pede `peca_url` como URL, mas a
implementação sempre devolveu o caminho local absoluto do PNG salvo em
`dados/pecas/`. Isso fechava a lacuna dentro do processo (upload direto do
arquivo pro adapter de publicação), mas quebrava a casca HTTP: o
front-end recebia um path de disco da VPS, não algo que dá pra exibir.
Esta função é o fechamento real: só reescreve `.png` (única extensão que
`GET /pecas/{arquivo}` serve — reel/vídeo fica de fora por ora, sem rota
pra servir ainda) — qualquer outra coisa passa intacta.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


def url_peca(caminho_disco: str) -> str:
    nome = PurePosixPath(caminho_disco.replace("\\", "/")).name
    if not nome.lower().endswith(".png"):
        return caminho_disco
    return f"/pecas/{nome}"


def _reescrever_lista_ou_string(valor: Any) -> Any:
    if isinstance(valor, list):
        return [url_peca(v) if isinstance(v, str) else v for v in valor]
    if isinstance(valor, str):
        return url_peca(valor)
    return valor


def reescrever_peca_url(valor: Any) -> Any:
    """Pra `posts.peca_url` (lista ou string legada)."""
    return _reescrever_lista_ou_string(valor)


def reescrever_peca(peca: dict[str, Any]) -> dict[str, Any]:
    """Pra `aprovacoes.peca_json` — cobre as duas formas em que `pecas_urls`
    aparece: direto (etapa=visual) ou dentro de `argumentos` (etapa=
    publicacao, onde `peca` é o `{ferramenta, argumentos}` de
    `publicar_conteudo`)."""
    peca = dict(peca)
    if "pecas_urls" in peca:
        peca["pecas_urls"] = _reescrever_lista_ou_string(peca["pecas_urls"])
    argumentos = peca.get("argumentos")
    if isinstance(argumentos, dict) and "pecas_urls" in argumentos:
        peca["argumentos"] = {
            **argumentos,
            "pecas_urls": _reescrever_lista_ou_string(argumentos["pecas_urls"]),
        }
    return peca
