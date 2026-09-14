"""api/perfil_render.py — converte entre o perfil-marca.md real (que o
runtime consome via --perfil) e uma forma estruturada que o front-end edita
por formulário (nunca YAML/markdown cru na tela — arquitetura.md).

  - `perfil_para_estrutura()` : lê o .md atual -> dict estruturado (GET /perfil)
  - `estrutura_para_markdown()`: dict estruturado -> texto .md (PUT /perfil)

O parsing reusa `runtime.perfil_loader.carregar_perfil` — a MESMA função que
o CLI usa — pra garantir que o que a API entende como "perfil válido" é
exatamente o que o runtime entende (sem caminho paralelo).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from runtime.perfil_loader import SECOES_OBRIGATORIAS, carregar_perfil

_TITULOS_SECAO = {
    "icp": "ICP (Perfil de Cliente Ideal)",
    "marca": "Marca",
    "oferta": "Oferta",
}
_TITULO_IDENTIDADE = "Identidade Visual (carrossel/estático)"


def perfil_para_estrutura(caminho: str | Path) -> dict[str, Any]:
    perfil = carregar_perfil(caminho)
    secoes = dict(perfil.secoes)

    extras = {
        titulo: conteudo
        for titulo, conteudo in secoes.items()
        if titulo not in SECOES_OBRIGATORIAS and not titulo.startswith("Identidade Visual")
    }

    return {
        "nicho": perfil.nicho,
        "rede": perfil.rede,
        "tom": perfil.tom,
        "icp": secoes.get("ICP"),
        "marca": secoes.get("Marca"),
        "oferta": secoes.get("Oferta"),
        # tokens já mesclados com IDENTIDADE_VISUAL_PADRAO — o form mostra o
        # efetivo; o que o operador não mexer volta igual.
        "identidade_visual": perfil.identidade_visual,
        "secoes_extras": extras,
        "secoes_faltando": perfil.secoes_faltando(),
        "existe": Path(caminho).exists(),
    }


def _bloco(titulo: str, corpo: str | None, *, obrigatoria: bool = False) -> str:
    corpo = (corpo or "").strip()
    if corpo:
        return f"## {titulo}\n\n{corpo}\n"
    # Seção obrigatória vazia => NÃO renderiza a seção. Assim carregar_perfil
    # a vê ausente e secoes_faltando() a acusa (a MESMA validação do runtime
    # rejeita o PUT). Placeholder aqui mascararia a lacuna.
    if obrigatoria:
        return ""
    return f"## {titulo}\n\n_(a preencher)_\n"


def estrutura_para_markdown(dados: dict[str, Any], *, nome_marca: str | None = None) -> str:
    """dict estruturado -> texto de perfil-marca.md. O resultado, relido por
    carregar_perfil, precisa devolver as mesmas seções — por isso os títulos
    seguem o padrão de config-exemplo/perfil-marca.md."""
    frontmatter = {
        chave: dados.get(chave)
        for chave in ("nicho", "rede", "tom")
        if dados.get(chave) not in (None, "")
    }
    partes: list[str] = []
    if frontmatter:
        fm = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
        partes.append(f"---\n{fm}\n---")

    partes.append(f"# Perfil de marca — {nome_marca or dados.get('nicho') or 'sem nome'}")
    partes.append(_bloco(_TITULOS_SECAO["icp"], dados.get("icp"), obrigatoria=True))
    partes.append(_bloco(_TITULOS_SECAO["marca"], dados.get("marca"), obrigatoria=True))
    partes.append(_bloco(_TITULOS_SECAO["oferta"], dados.get("oferta"), obrigatoria=True))

    identidade = dados.get("identidade_visual")
    if isinstance(identidade, dict) and identidade:
        tokens = yaml.safe_dump(identidade, allow_unicode=True, sort_keys=False).strip()
        partes.append(
            f"## {_TITULO_IDENTIDADE}\n\n"
            "Design tokens lidos pelo motor de template (perfil_loader.py extrai "
            "este bloco). Qualquer chave omitida cai no default de "
            "`runtime/perfil_loader.py`.\n\n"
            f"```yaml\n{tokens}\n```\n"
        )

    for titulo, conteudo in (dados.get("secoes_extras") or {}).items():
        partes.append(_bloco(str(titulo), str(conteudo)))

    return "\n".join(p for p in partes if p).rstrip() + "\n"
