"""perfil_loader.py — carrega o perfil-marca.md apontado por --perfil
(comandos.md) e o injeta no planejador (agent.md: "[EXTENSÃO desta
ideação]... contexto persistente de nicho/marca/oferta").

Formato esperado (ver config-exemplo/perfil-marca.md):
  - frontmatter YAML: nicho, rede, tom
  - seções markdown obrigatórias: "## ICP", "## Marca", "## Oferta"
  - seção "## Identidade Visual ..." com um bloco ```yaml``` de design tokens
    (cores, tipografia, cabeçalho/rodapé, dimensão da peça) — lidos pelo
    motor de template (decisoes-de-engenharia.md, seção 2). O que faltar no
    bloco cai no default embutido aqui.
  - seção "## Hashtags" (opcional) em prosa — bullets `- #hashtag` sob
    subtítulos em negrito reconhecidos por palavra-chave (fixas/nicho/
    frente 1/frente 2), lidos por gerar_roteiro.py. Sem a seção ou sem
    subtítulo reconhecido, cada categoria cai numa lista vazia (sem
    default hardcoded: hashtag de marca é conteúdo de marketing real).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SECOES_OBRIGATORIAS = ("ICP", "Marca", "Oferta")

# decisoes-de-engenharia.md, seção 2 / config-exemplo/perfil-marca.md, seção
# "Identidade Visual": tokens usados pelo motor de template. Estes defaults
# refletem a direção "quente/madeira" já validada — o bloco yaml do perfil
# sobrescreve chave a chave (merge profundo).
IDENTIDADE_VISUAL_PADRAO: dict = {
    "dimensoes": {"largura": 1080, "altura": 1350},  # retrato 4:5
    "cores": {
        "fundo": "#F1ECE4",       # bege/off-white quente
        "texto": "#1F1710",       # marrom escuro quase preto
        "destaque": "#C1622D",    # terracota/âmbar
        "linha": "#1F1710",       # linha fina do rodapé
    },
    "tipografia": {
        "familia_titulo": "'Anton', 'Archivo Black', 'Arial Narrow', sans-serif",
        "familia_corpo": "'Inter', 'Helvetica Neue', Arial, sans-serif",
        "peso_titulo": 800,
        "peso_corpo": 400,
        # Playwright busca isto no render; offline cai na stack de fallback.
        "google_fonts_url": (
            "https://fonts.googleapis.com/css2?family=Anton&"
            "family=Inter:wght@400;600;700&display=swap"
        ),
    },
    "cabecalho": {
        "arroba": "@moveleiro.ia",
        "indicador_arraste": "arraste →",
    },
    "rodape": {
        "mostrar_contador": True,
    },
}


# catálogo de hashtags de marca (perfil-marca.md, seção "Hashtags") — ao
# contrário de IDENTIDADE_VISUAL_PADRAO, não tem default hardcoded em
# Python: é conteúdo de marketing real, não token técnico de renderização.
# Sem a seção (ou seção inválida), cada chave cai numa lista vazia.
HASHTAGS_VAZIO: dict = {
    "fixas": [], "nicho": [], "frente_demanda": [], "frente_atendimento": []
}


@dataclass
class PerfilMarca:
    caminho: Path
    nicho: str | None
    rede: str | None
    tom: str | None
    secoes: dict[str, str]  # nome da seção -> conteúdo markdown
    texto_completo: str
    identidade_visual: dict = field(default_factory=lambda: copy.deepcopy(IDENTIDADE_VISUAL_PADRAO))
    hashtags: dict = field(default_factory=lambda: copy.deepcopy(HASHTAGS_VAZIO))

    def secoes_faltando(self) -> list[str]:
        return [s for s in SECOES_OBRIGATORIAS if s not in self.secoes]

    def valido(self) -> bool:
        return not self.secoes_faltando()

    def as_dict(self) -> dict:
        """Formato passado como `perfil: object` pra gerar_roteiro (toolbox.md)."""
        return {
            "nicho": self.nicho,
            "rede": self.rede,
            "tom": self.tom,
            "icp": self.secoes.get("ICP"),
            "marca": self.secoes.get("Marca"),
            "oferta": self.secoes.get("Oferta"),
            "hashtags": self.hashtags,
        }


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_SECAO_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_BLOCO_YAML_RE = re.compile(r"```yaml\n(.*?)\n```", re.DOTALL)


def _merge_profundo(base: dict, sobre: dict) -> dict:
    """Merge recursivo — `sobre` vence, mas só nas chaves que traz."""
    resultado = copy.deepcopy(base)
    for chave, valor in (sobre or {}).items():
        if isinstance(valor, dict) and isinstance(resultado.get(chave), dict):
            resultado[chave] = _merge_profundo(resultado[chave], valor)
        else:
            resultado[chave] = valor
    return resultado


def carregar_perfil(caminho_perfil: str | Path) -> PerfilMarca:
    caminho = Path(caminho_perfil)
    if not caminho.exists():
        # planner.md: "perfil-marca.md estiver ausente" -> PERGUNTAR_USUARIO.
        # Devolvemos um PerfilMarca vazio (secoes={}) em vez de levantar
        # exceção, pra quem chama (ciclo.py/planejador.py) decidir o próximo
        # passo do jeito que o contrato manda, e não travar o processo.
        return PerfilMarca(
            caminho=caminho, nicho=None, rede=None, tom=None, secoes={}, texto_completo=""
        )

    texto = caminho.read_text(encoding="utf-8")

    frontmatter: dict = {}
    corpo = texto
    m = _FRONTMATTER_RE.match(texto)
    if m:
        frontmatter = yaml.safe_load(m.group(1)) or {}
        corpo = m.group(2)

    secoes = _extrair_secoes(corpo)

    return PerfilMarca(
        caminho=caminho,
        nicho=frontmatter.get("nicho"),
        rede=frontmatter.get("rede"),
        tom=frontmatter.get("tom"),
        secoes=secoes,
        texto_completo=texto,
        identidade_visual=_extrair_identidade_visual(secoes),
        hashtags=_extrair_hashtags(secoes),
    )


def _extrair_secoes(corpo: str) -> dict[str, str]:
    """Quebra o corpo do markdown em {titulo_da_secao_h2: conteudo}."""
    matches = list(_SECAO_RE.finditer(corpo))
    secoes: dict[str, str] = {}
    for i, m in enumerate(matches):
        titulo = m.group(1).strip()
        # nomes de seção do contrato são "ICP (...)" — casamos pelo prefixo
        # com as chaves de SECOES_OBRIGATORIAS quando aplicável.
        chave = next((s for s in SECOES_OBRIGATORIAS if titulo.startswith(s)), titulo)
        inicio = m.end()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(corpo)
        secoes[chave] = corpo[inicio:fim].strip()
    return secoes


def _extrair_identidade_visual(secoes: dict[str, str]) -> dict:
    """Lê o bloco ```yaml``` da seção "Identidade Visual ..." e faz merge
    sobre IDENTIDADE_VISUAL_PADRAO. Sem seção, sem bloco ou bloco inválido:
    devolve o default puro (o motor de template sempre tem tokens válidos)."""
    conteudo = next(
        (v for k, v in secoes.items() if k.startswith("Identidade Visual")), None
    )
    if not conteudo:
        return copy.deepcopy(IDENTIDADE_VISUAL_PADRAO)
    m = _BLOCO_YAML_RE.search(conteudo)
    if not m:
        return copy.deepcopy(IDENTIDADE_VISUAL_PADRAO)
    try:
        tokens = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return copy.deepcopy(IDENTIDADE_VISUAL_PADRAO)
    if not isinstance(tokens, dict):
        return copy.deepcopy(IDENTIDADE_VISUAL_PADRAO)
    return _merge_profundo(IDENTIDADE_VISUAL_PADRAO, tokens)


# seção "Hashtags" é prosa (bullets "- #hashtag" sob subtítulos em
# negrito), mesmo estilo de "Provas de sustentação"/"Objeções a quebrar" —
# não um bloco ```yaml``` como Identidade Visual (aqui é lista simples por
# categoria, não config chave-valor aninhada). Cada subtítulo casa por
# palavra-chave com uma das 4 categorias de HASHTAGS_VAZIO.
_HASHTAG_CATEGORIA_HEADERS = (
    ("fixas", re.compile(r"fixas", re.IGNORECASE)),
    ("frente_demanda", re.compile(r"frente\s*1|gera[cç][aã]o de demanda|presen[cç]a digital", re.IGNORECASE)),
    ("frente_atendimento", re.compile(r"frente\s*2|atendimento|vazamento|janela de ouro", re.IGNORECASE)),
    ("nicho", re.compile(r"nicho", re.IGNORECASE)),
)
_HASHTAG_SUBTITULO_RE = re.compile(r"^\*\*(.+?)\*\*")
_HASHTAG_BULLET_RE = re.compile(r"^-\s*(#\S+)")


def _extrair_hashtags(secoes: dict[str, str]) -> dict:
    """Lê a seção "Hashtags" (catálogo usado por gerar_roteiro.py — ver
    HASHTAGS_VAZIO acima): bullets `- #hashtag` agrupados sob subtítulos em
    negrito que a gente reconhece por palavra-chave (fixas/nicho/frente 1
    ou 2). Sem seção, sem subtítulo reconhecido, ou nada aproveitável:
    listas vazias em vez de conteúdo hardcoded em Python — hashtag de
    marca é decisão de marketing, não token técnico."""
    resultado = {chave: [] for chave in HASHTAGS_VAZIO}
    conteudo = next((v for k, v in secoes.items() if k.startswith("Hashtags")), None)
    if not conteudo:
        return resultado
    categoria_atual: str | None = None
    for linha in conteudo.splitlines():
        linha = linha.strip()
        m_subtitulo = _HASHTAG_SUBTITULO_RE.match(linha)
        if m_subtitulo:
            texto = m_subtitulo.group(1)
            categoria_atual = next(
                (c for c, padrao in _HASHTAG_CATEGORIA_HEADERS if padrao.search(texto)), None
            )
            continue
        if categoria_atual:
            m_bullet = _HASHTAG_BULLET_RE.match(linha)
            if m_bullet:
                resultado[categoria_atual].append(m_bullet.group(1))
    return resultado
