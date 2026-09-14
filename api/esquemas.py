"""api/esquemas.py — modelos Pydantic de entrada/saída da casca HTTP.

Deliberadamente frouxos onde o dado vem do runtime (posts, tokens de
identidade visual): a fonte da verdade do schema é o runtime, não aqui.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PostOut(BaseModel):
    post_id: str
    tema: str | None = None
    roteiro: str | None = None
    peca_url: Any = None  # str legado ou list[str] (carrossel)
    rede: str | None = None
    status_aprovacao: str | None = None
    status_publicacao: str | None = None
    publicado_em: str | None = None


class HistoricoOut(BaseModel):
    posts: list[PostOut]
    limite: int
    offset: int


class PerfilOut(BaseModel):
    nicho: str | None = None
    rede: str | None = None
    tom: str | None = None
    icp: str | None = None
    marca: str | None = None
    oferta: str | None = None
    identidade_visual: dict[str, Any] = Field(default_factory=dict)
    secoes_extras: dict[str, str] = Field(default_factory=dict)
    secoes_faltando: list[str] = Field(default_factory=list)
    existe: bool = True


class AprovacaoPendenteOut(BaseModel):
    id: str
    execucao_id: str
    etapa: str  # roteiro | visual | publicacao
    peca: dict[str, Any]
    criado_em: str


class PendentesOut(BaseModel):
    pendentes: list[AprovacaoPendenteOut]


class DecisaoIn(BaseModel):
    aprovado: bool
    feedback: str = ""


class DecisaoOut(BaseModel):
    aprovacao_id: str
    etapa: str
    aprovado: bool
    execucao_retomada: str


class DisparoIn(BaseModel):
    entrada: str | None = None
    formato: Literal["reel", "carrossel", "estatico"] = "reel"  # ciclo.FORMATO_PADRAO


class ExecucaoOut(BaseModel):
    execucao_id: str
    # rodando | suspensa | aguardando_intervencao | finalizada | erro | descartada
    estado: str
    entrada: str | None = None
    formato: str | None = None
    segundos_ativos: float | None = None
    motivo_parada: str | None = None
    pergunta_aberta: str | None = None
    atualizado_em: str | None = None


class AguardandoOut(BaseModel):
    execucoes: list[ExecucaoOut]


class PerfilIn(BaseModel):
    nicho: str | None = None
    rede: str | None = None
    tom: str | None = None
    icp: str | None = None
    marca: str | None = None
    oferta: str | None = None
    identidade_visual: dict[str, Any] = Field(default_factory=dict)
    secoes_extras: dict[str, str] = Field(default_factory=dict)
    # rótulo só pro título H1 do .md — não é dado de negócio.
    nome_marca: str | None = None
