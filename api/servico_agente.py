"""api/servico_agente.py — a ÚNICA ponte entre a casca HTTP e o runtime do
agente.

Aqui SIM é permitido importar `runtime.*`: esta pasta faz parte do repo do
agente-social-media, é a interface estável que o agente expõe. Quem NÃO pode
importar `runtime/` é o componente `front-end` — ele fala só com esta casca
por HTTP (arquitetura.md, seção 1).

Regra: nenhuma lógica de validação nova mora aqui. Leitura/escrita de perfil
reusa `runtime.perfil_loader`; a validação de "perfil completo" é a mesma
`PerfilMarca.secoes_faltando()` que o `planejador.py` usa pra decidir
PERGUNTAR_USUARIO e que o comando `validar` do CLI aplica.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from runtime.memoria import SQLiteMemoriaRepository
from runtime.perfil_loader import carregar_perfil

from . import worker
from .config import ConfigApi
from .media import reescrever_peca, reescrever_peca_url
from .perfil_render import estrutura_para_markdown, perfil_para_estrutura


class PerfilInvalido(ValueError):
    """PUT /perfil recusado: o resultado não passaria na mesma checagem que o
    runtime aplica (seções obrigatórias ausentes). O arquivo real não é
    tocado."""

    def __init__(self, secoes_faltando: list[str]):
        self.secoes_faltando = secoes_faltando
        super().__init__(
            "perfil incompleto — seções obrigatórias ausentes: "
            + ", ".join(secoes_faltando)
        )


def _com_peca_url_reescrita(post: dict[str, Any]) -> dict[str, Any]:
    post = dict(post)
    post["peca_url"] = reescrever_peca_url(post.get("peca_url"))
    return post


def listar_posts(config: ConfigApi, *, limite: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    repo = SQLiteMemoriaRepository(config.db_path)
    try:
        posts = repo.listar_posts(limite=limite, offset=offset)
    finally:
        repo.close()
    return [_com_peca_url_reescrita(p) for p in posts]


def buscar_post(config: ConfigApi, post_id: str) -> dict[str, Any] | None:
    repo = SQLiteMemoriaRepository(config.db_path)
    try:
        post = repo.buscar_post(post_id)
    finally:
        repo.close()
    return _com_peca_url_reescrita(post) if post else None


# -- fila de aprovação -------------------------------------------------------
class AprovacaoNaoPendente(ValueError):
    """POST /aprovacoes/{id}/decidir numa aprovação que já foi decidida (ou
    não existe)."""


def listar_aprovacoes_pendentes(config: ConfigApi) -> list[dict[str, Any]]:
    repo = SQLiteMemoriaRepository(config.db_path)
    try:
        pendentes = repo.listar_aprovacoes_pendentes()
    finally:
        repo.close()
    for p in pendentes:
        p["peca"] = reescrever_peca(p["peca"])
    return pendentes


def decidir_aprovacao(
    config: ConfigApi,
    aprovacao_id: str,
    *,
    aprovado: bool,
    feedback: str,
    chamador: str,
) -> dict[str, Any]:
    """Grava a decisão (a lógica de aprovação é do runtime; aqui só registra)
    e dispara a retomada do ciclo em background. Devolve a aprovação
    atualizada + o id da execução retomada."""
    repo = SQLiteMemoriaRepository(config.db_path)
    try:
        try:
            registro = repo.registrar_decisao_aprovacao(
                aprovacao_id, aprovado=aprovado, feedback=feedback, decidido_por=chamador
            )
        except (KeyError, ValueError) as exc:
            raise AprovacaoNaoPendente(str(exc)) from exc
        execucao_id = registro["execucao_id"]
    finally:
        repo.close()

    worker.retomar(config, execucao_id, chamador=chamador)
    registro["peca"] = reescrever_peca(registro["peca"])
    return {"aprovacao": registro, "execucao_retomada": execucao_id}


def disparar_execucao(
    config: ConfigApi, *, entrada: str | None, formato: str, chamador: str
) -> dict[str, Any]:
    execucao_id = worker.disparar(config, entrada=entrada, formato=formato, chamador=chamador)
    return {"execucao_id": execucao_id, "estado": "rodando"}


def obter_trace(config: ConfigApi, execucao_id: str) -> dict[str, Any] | None:
    """dados/trace.json guarda só a execução mais recente (runtime/trace.py —
    decisão pré-existente, não mudada aqui). Se `execucao_id` não bater, não
    há trace disponível pra ela (foi sobrescrito por uma execução seguinte)."""
    from runtime.trace import carregar_trace

    bruto = carregar_trace(config.trace_path)
    if bruto is None or bruto.get("execucao_id") != execucao_id:
        return None
    return bruto


def estado_execucao(config: ConfigApi, execucao_id: str) -> dict[str, Any] | None:
    repo = SQLiteMemoriaRepository(config.db_path)
    try:
        return repo.buscar_execucao_ativa(execucao_id)
    finally:
        repo.close()


def listar_execucoes_aguardando(config: ConfigApi) -> list[dict[str, Any]]:
    repo = SQLiteMemoriaRepository(config.db_path)
    try:
        return repo.listar_execucoes_aguardando_intervencao()
    finally:
        repo.close()


class ExecucaoNaoEncontrada(KeyError):
    pass


class ExecucaoNaoDescartavel(ValueError):
    pass


def descartar_execucao(config: ConfigApi, execucao_id: str, *, chamador: str) -> dict[str, Any]:
    repo = SQLiteMemoriaRepository(config.db_path)
    try:
        try:
            return repo.descartar_execucao(execucao_id, por=chamador)
        except KeyError as exc:
            raise ExecucaoNaoEncontrada(str(exc)) from exc
        except ValueError as exc:
            raise ExecucaoNaoDescartavel(str(exc)) from exc
    finally:
        repo.close()


# -- mídia (GET /pecas/{arquivo}) --------------------------------------
class PecaInvalida(ValueError):
    """Nome de arquivo malformado ou fora da área permitida — nunca chega
    a tocar disco de verdade."""


class PecaNaoEncontrada(KeyError):
    """Nome bem-formado, mas não é uma peça registrada pelo agente (ou o
    arquivo não existe mais em disco)."""


def obter_peca_bytes(config: ConfigApi, nome_arquivo: str) -> bytes:
    """Camadas 2-4 de validação (a 1ª, o regex de formato, é em
    api/rotas/pecas.py — falha mais barata, antes de tocar config/disco):

    2) resolve o caminho e confirma que continua dentro de dados/pecas/
       depois de resolvido — nunca confia só no regex contra `..`;
    3) só serve extensão .png;
    4) o nome precisa bater com uma peça REGISTRADA no banco (posts,
       aprovações, ou memória de alguma execução) — nunca "existe um
       arquivo com esse nome na pasta" sozinho.
    """
    pasta_pecas = (config.agente_dir / "dados" / "pecas").resolve()
    candidato = (pasta_pecas / nome_arquivo).resolve()

    if not candidato.is_relative_to(pasta_pecas):
        raise PecaInvalida(f"{nome_arquivo!r} resolve pra fora de dados/pecas/")
    if candidato.suffix.lower() != ".png":
        raise PecaInvalida(f"{nome_arquivo!r}: extensão não permitida")

    repo = SQLiteMemoriaRepository(config.db_path)
    try:
        registrada = repo.peca_registrada(nome_arquivo)
    finally:
        repo.close()
    if not registrada:
        raise PecaNaoEncontrada(nome_arquivo)

    if not candidato.is_file():
        raise PecaNaoEncontrada(nome_arquivo)

    return candidato.read_bytes()


def ler_perfil(config: ConfigApi) -> dict[str, Any]:
    return perfil_para_estrutura(config.perfil_path)


def escrever_perfil(
    config: ConfigApi, dados: dict[str, Any], *, nome_marca: str | None = None
) -> dict[str, Any]:
    """Renderiza o .md, valida com a MESMA regra do runtime, e só então
    substitui o arquivo real (escrita atômica). Devolve a estrutura relida."""
    texto = estrutura_para_markdown(dados, nome_marca=nome_marca)

    destino = Path(config.perfil_path)
    destino.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_nome = tempfile.mkstemp(
        dir=destino.parent, prefix=".perfil-", suffix=".md.tmp"
    )
    tmp = Path(tmp_nome)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)

        # mesma checagem que planejador.py / cli.validar aplicam
        perfil = carregar_perfil(tmp)
        faltando = perfil.secoes_faltando()
        if faltando:
            raise PerfilInvalido(faltando)

        os.replace(tmp, destino)
    finally:
        if tmp.exists():
            tmp.unlink()

    return perfil_para_estrutura(destino)
