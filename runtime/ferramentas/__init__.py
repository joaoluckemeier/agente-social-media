"""ferramentas/__init__.py — REGISTRY usado por executor.py.

Mantém executor.py fechado pra modificação (OCP): adicionar/trocar uma
ferramenta é uma entrada aqui + o arquivo correspondente, nunca uma mudança
em executor.py. Nome da chave = `nome` em contracts/toolbox.md e
contracts/skills.md.
"""

from __future__ import annotations

from typing import Any, Callable

from .aprovacao_humana import solicitar_aprovacao_humana
from .autocritica import autocritica_conteudo
from .buscar_insights import buscar_insights_recentes
from .gerar_peca_visual import gerar_peca_visual
from .gerar_roteiro import gerar_roteiro
from .pesquisar_tendencias import pesquisar_tendencias_nicho
from .publicar_conteudo import publicar_conteudo

REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "buscar_insights_recentes": buscar_insights_recentes,
    "pesquisar_tendencias_nicho": pesquisar_tendencias_nicho,
    "gerar_roteiro": gerar_roteiro,
    "autocritica_conteudo": autocritica_conteudo,
    "gerar_peca_visual": gerar_peca_visual,
    "solicitar_aprovacao_humana": solicitar_aprovacao_humana,
    "publicar_conteudo": publicar_conteudo,
}

# entrada esperada de cada ferramenta (nome do argumento -> tipo, informativo)
# usado por executor.py pra validar argumentos_ferramenta antes de chamar.
# Espelha contracts/skills.md — fonte única de verdade sobre o schema.
ENTRADA_ESPERADA: dict[str, tuple[str, ...]] = {
    "buscar_insights_recentes": ("limite",),
    "pesquisar_tendencias_nicho": ("nicho", "rede"),
    "gerar_roteiro": ("tema", "perfil", "insights_anteriores", "formato"),
    "autocritica_conteudo": ("conteudo", "tipo", "criterios"),
    "gerar_peca_visual": ("slides", "formato"),
    "solicitar_aprovacao_humana": ("peca", "etapa"),
    "publicar_conteudo": ("pecas_urls", "rede", "legenda"),
}
