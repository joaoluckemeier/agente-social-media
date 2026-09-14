"""executor.py — o braço (implementa contracts/executor.md).

Valida entrada, chama a ferramenta (via ferramentas.REGISTRY — nunca por
`if/elif` de nome, pra manter OCP), aplica retry, e avalia/persiste o
resultado. Também é onde vivem, de forma genérica (a partir de rules.md e
hooks.md, não de lógica hardcoded por ferramenta):
  - o limite de chamadas por ferramenta (rules.md: chamadas_ferramenta);
  - o gate de confirmação humana síncrona antes de qualquer acao_sensivel
    (rules.md: acoes_sensiveis; hooks.md: antes_da_acao vira alerta).

Retry com backoff exponencial e timeout por chamada em gerar_peca_visual e
publicar_conteudo: decisoes-de-engenharia.md, seção 6.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturoTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from . import ErroConfiguracaoAusente
from .aprovacao import GatewayAprovacao, RunSuspensa
from .aprovacao.gateway_cli import GatewayAprovacaoCLI
from .ferramentas import ENTRADA_ESPERADA, REGISTRY
from .memoria import MemoriaRepository
from .trace import Trace

# rules.md: acoes_sensiveis
ACOES_SENSIVEIS = {"publicar_conteudo"}

# rules.md: limites.chamadas_ferramenta
LIMITES_CHAMADAS: dict[str, int] = {
    "buscar_insights_recentes": 1,
    "pesquisar_tendencias_nicho": 2,
    "gerar_roteiro": 3,
    "gerar_peca_visual": 3,
    "publicar_conteudo": 1,
}
LIMITE_TOTAL_CHAMADAS = 16

# decisoes-de-engenharia.md, seção 6
RETRY_PADRAO = 1
RETRY_GERAR_PECA_VISUAL = 2
TIMEOUT_IMAGEM_SEGUNDOS = 60
TIMEOUT_VIDEO_SEGUNDOS = 120
BACKOFF_BASE_SEGUNDOS = 2  # exponencial: BACKOFF_BASE ** tentativa


class ErroValidacaoEntrada(Exception):
    pass


class LimiteDeChamadasExcedido(Exception):
    """Sinaliza pra ciclo.py tratar como condição de parada (sem_progresso /
    max_etapas_excedido, conforme o caso — loop.md)."""


class ConfirmacaoHumanaNegada(Exception):
    """Ação sensível (rules.md) recusada na confirmação síncrona do CLI —
    ciclo.py trata como a condição de parada confirmacao_humana_negada."""


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ResultadoExecucao:
    nome_ferramenta: str
    argumentos: dict[str, Any]
    saida: dict[str, Any]


def _validar_entrada(nome_ferramenta: str, argumentos: dict[str, Any]) -> None:
    esperados = ENTRADA_ESPERADA.get(nome_ferramenta)
    if esperados is None:
        raise ErroValidacaoEntrada(f"ferramenta desconhecida: {nome_ferramenta!r}")
    faltando = [c for c in esperados if c not in argumentos]
    if faltando:
        raise ErroValidacaoEntrada(
            f"{nome_ferramenta}: argumentos obrigatórios ausentes: {faltando}"
        )


def _contar_chamadas(memoria: MemoriaRepository, execucao_id: str, nome_ferramenta: str | None = None) -> int:
    registros = memoria.listar_memoria(execucao_id, tipo="resultado_de_ferramenta")
    if nome_ferramenta is None:
        return len(registros)
    return sum(1 for r in registros if r.conteudo.get("ferramenta") == nome_ferramenta)


def _verificar_limites(memoria: MemoriaRepository, execucao_id: str, nome_ferramenta: str) -> None:
    total = _contar_chamadas(memoria, execucao_id)
    if total >= LIMITE_TOTAL_CHAMADAS:
        raise LimiteDeChamadasExcedido(
            f"limite total de chamadas de ferramenta atingido ({LIMITE_TOTAL_CHAMADAS})"
        )
    limite_ferramenta = LIMITES_CHAMADAS.get(nome_ferramenta)
    if limite_ferramenta is not None:
        usadas = _contar_chamadas(memoria, execucao_id, nome_ferramenta)
        if usadas >= limite_ferramenta:
            raise LimiteDeChamadasExcedido(
                f"{nome_ferramenta}: limite de chamadas atingido ({limite_ferramenta})"
            )


# A confirmação de acao_sensivel e a aprovação de conteúdo (roteiro/visual)
# agora passam por um GatewayAprovacao (runtime/aprovacao/) — CLI síncrono por
# padrão, ou fila assíncrona quando a casca HTTP orquestra. rules.md já prevê
# essa troca "sem reescrever o resto".


def _politica_retry(
    nome_ferramenta: str, formato: str | None, numero_de_pecas: int = 1
) -> tuple[int, float | None]:
    """Retorna (tentativas_extras, timeout_segundos).

    `numero_de_pecas`: carrossel gera 1 peça por slide dentro de UMA
    chamada de gerar_peca_visual (chamadas sequenciais de verdade à API) —
    o timeout escala linearmente, senão um carrossel de 7-8 slides estoura
    o limite pensado pra 1 peça só.
    """
    if nome_ferramenta == "gerar_peca_visual":
        timeout_unitario = TIMEOUT_VIDEO_SEGUNDOS if formato == "reel" else TIMEOUT_IMAGEM_SEGUNDOS
        return RETRY_GERAR_PECA_VISUAL, timeout_unitario * max(1, numero_de_pecas)
    if nome_ferramenta == "publicar_conteudo":
        return RETRY_GERAR_PECA_VISUAL, None
    return RETRY_PADRAO, None


def _chamar_com_retry(
    funcao: Callable[..., dict[str, Any]],
    argumentos: dict[str, Any],
    *,
    tentativas_extras: int,
    timeout: float | None,
    trace: Trace,
    nome_ferramenta: str,
) -> dict[str, Any]:
    ultima_excecao: Exception | None = None
    for tentativa in range(tentativas_extras + 1):
        try:
            if timeout is None:
                return funcao(**argumentos)
            with ThreadPoolExecutor(max_workers=1) as executor_thread:
                futuro = executor_thread.submit(funcao, **argumentos)
                return futuro.result(timeout=timeout)
        except (NotImplementedError, ErroConfiguracaoAusente, RunSuspensa):
            # falha permanente, não transitória (ferramenta não escrita ou
            # credencial deliberadamente ausente) — repassar na hora, sem
            # queimar retry/backoff tentando de novo algo que nunca muda.
            # RunSuspensa: não é erro — é o gateway de fila pedindo pra
            # suspender a execução até a decisão humana chegar; retentar só
            # criaria pendências duplicadas.
            raise
        except FuturoTimeoutError as exc:
            ultima_excecao = exc
            trace.em_erro(ferramenta=nome_ferramenta, tentativa=tentativa, erro="timeout")
        except Exception as exc:  # noqa: BLE001 — repassado após esgotar retries
            ultima_excecao = exc
            trace.em_erro(ferramenta=nome_ferramenta, tentativa=tentativa, erro=str(exc))
        if tentativa < tentativas_extras:
            time.sleep(BACKOFF_BASE_SEGUNDOS**tentativa)
    assert ultima_excecao is not None
    raise ultima_excecao


def executar_ferramenta(
    *,
    nome_ferramenta: str,
    argumentos_ferramenta: dict[str, Any],
    execucao_id: str,
    memoria: MemoriaRepository,
    trace: Trace,
    gateway: GatewayAprovacao | None = None,
) -> ResultadoExecucao:
    # gateway padrão = CLI síncrono (comportamento de sempre). A casca HTTP
    # passa GatewayAprovacaoFila.
    gateway = gateway or GatewayAprovacaoCLI()

    # executor.md: validar_entrada
    _validar_entrada(nome_ferramenta, argumentos_ferramenta)
    _verificar_limites(memoria, execucao_id, nome_ferramenta)

    eh_sensivel = nome_ferramenta in ACOES_SENSIVEIS
    trace.antes_da_acao(
        ferramenta=nome_ferramenta, argumentos=argumentos_ferramenta, acao_sensivel=eh_sensivel
    )

    if eh_sensivel:
        # pode levantar RunSuspensa (gateway de fila) — propaga sem virar erro.
        confirmada = gateway.confirmar_acao_sensivel(
            execucao_id=execucao_id,
            nome_ferramenta=nome_ferramenta,
            argumentos=argumentos_ferramenta,
        )
        if not confirmada:
            trace.em_erro(ferramenta=nome_ferramenta, erro="confirmação humana negada")
            raise ConfirmacaoHumanaNegada(f"{nome_ferramenta}: confirmação negada pelo usuário")

    # regeneração parcial (extensão — ver ferramentas/gerar_peca_visual.py)
    # só gera len(indices_para_regenerar) peças, não o carrossel inteiro.
    indices_regen = argumentos_ferramenta.get("indices_para_regenerar")
    numero_de_pecas = len(indices_regen) if indices_regen else (
        len(argumentos_ferramenta.get("slides") or []) or 1
    )
    tentativas_extras, timeout = _politica_retry(
        nome_ferramenta, argumentos_ferramenta.get("formato"), numero_de_pecas
    )
    funcao = REGISTRY[nome_ferramenta]

    # contexto extra injetado em toda ferramenta (absorvido via **_ nos
    # stubs); cada implementação usa só o que precisar. `gateway`/`execucao_id`
    # são pra solicitar_aprovacao_humana delegar a decisão ao gateway.
    argumentos_com_contexto = {
        **argumentos_ferramenta,
        "memoria": memoria,
        "gateway": gateway,
        "execucao_id": execucao_id,
    }

    saida = _chamar_com_retry(
        funcao,
        argumentos_com_contexto,
        tentativas_extras=tentativas_extras,
        timeout=timeout,
        trace=trace,
        nome_ferramenta=nome_ferramenta,
    )

    # decisoes-de-engenharia.md, seção 8/12: custo estimado por chamada,
    # quando a ferramenta reporta um (chave interna `_custo`, não faz parte
    # do contrato de saída de skills.md — removida antes de seguir adiante).
    custo = saida.pop("_custo", None)
    if custo is not None:
        memoria.guardar_memoria(
            execucao_id, "custo_ferramenta", {"ferramenta": nome_ferramenta, **custo}
        )

    trace.apos_acao(ferramenta=nome_ferramenta, saida=saida, custo=custo)

    # executor.md: pos_execucao.avaliar_resultado — persistido pra o
    # planejador reconstruir estado, e pra memory.md (resultado_de_ferramenta)
    memoria.guardar_memoria(
        execucao_id,
        "resultado_de_ferramenta",
        {"ferramenta": nome_ferramenta, "argumentos": argumentos_ferramenta, "saida": saida},
    )
    if nome_ferramenta == "solicitar_aprovacao_humana":
        memoria.guardar_memoria(execucao_id, "feedback_de_aprovacao", saida)

    return ResultadoExecucao(nome_ferramenta=nome_ferramenta, argumentos=argumentos_ferramenta, saida=saida)
