"""api/worker.py — roda e retoma execuções do agente em background.

v1: 1 instância = 1 tenant, e a trava garante no máximo uma execução ativa,
então um `threading.Thread` daemon por vez basta. Cada thread abre o seu
próprio `SQLiteMemoriaRepository` (conexão própria; WAL + busy_timeout no
`memoria.py` cobrem a concorrência leitura/escrita com os requests).

Transições de estado de `execucao_ativa`:
    (disparo)  -> rodando
    RunSuspensa -> suspensa   (segundos_ativos acumulados; relógio pausa)
    retorno     -> finalizada (motivo_parada = condicao_parada do ciclo)
    exceção     -> erro
"""

from __future__ import annotations

import threading
import traceback
from typing import Any

from runtime import ErroConfiguracaoAusente as _ErroConfiguracaoAusente
from runtime import ciclo as ciclo_mod
from runtime.aprovacao import RunSuspensa
from runtime.aprovacao.gateway_fila import GatewayAprovacaoFila
from runtime.memoria import SQLiteMemoriaRepository
from runtime.perfil_loader import carregar_perfil
from runtime.trace import Trace

from .config import ConfigApi
from .guardas import checar_pode_disparar
from .observabilidade import registrar_evento_api

_disparo_lock = threading.Lock()
_thread_atual: threading.Thread | None = None


def _spawn(alvo, *args: Any) -> None:
    global _thread_atual
    t = threading.Thread(target=alvo, args=args, daemon=True)
    _thread_atual = t
    t.start()


def ha_execucao_no_worker() -> bool:
    return _thread_atual is not None and _thread_atual.is_alive()


def disparar(config: ConfigApi, *, entrada: str | None, formato: str, chamador: str) -> str:
    """Cria a execução (sob trava atômica) e larga o ciclo num thread.
    Levanta ExecucaoEmAndamento / RateLimitLocalAtingido (guardas.py)."""
    with _disparo_lock:
        repo = SQLiteMemoriaRepository(config.db_path)
        try:
            checar_pode_disparar(repo, config)
            execucao_id = ciclo_mod.novo_execucao_id()
            repo.registrar_disparo_execucao(execucao_id=execucao_id, origem=chamador)
            repo.criar_execucao_ativa(execucao_id, entrada=entrada, formato=formato)
        finally:
            repo.close()
    _spawn(_rodar, config, execucao_id, entrada, formato, chamador)
    return execucao_id


def retomar(config: ConfigApi, execucao_id: str, *, chamador: str) -> None:
    _spawn(_retomar, config, execucao_id, chamador)


# -- alvos de thread ----------------------------------------------------------
def _rodar(
    config: ConfigApi, execucao_id: str, entrada: str | None, formato: str, chamador: str
) -> None:
    repo = SQLiteMemoriaRepository(config.db_path)
    trace = Trace(execucao_id=execucao_id, caminho_arquivo=config.trace_path)
    try:
        perfil = carregar_perfil(config.perfil_path)
        resultado = ciclo_mod.executar_ciclo(
            execucao_id=execucao_id,
            entrada=entrada,
            perfil=perfil,
            memoria=repo,
            trace=trace,
            formato=formato,
            gateway=GatewayAprovacaoFila(repo),
        )
        _finalizou(repo, execucao_id, resultado, chamador, "POST /execucoes")
    except RunSuspensa as s:
        _suspendeu(repo, execucao_id, s, chamador, "POST /execucoes")
    except (NotImplementedError, _ErroConfiguracaoAusente) as exc:
        _errou(repo, execucao_id, f"{type(exc).__name__}: {exc}", chamador, "POST /execucoes")
    except Exception as exc:  # noqa: BLE001
        _errou(repo, execucao_id, f"{type(exc).__name__}: {exc}", chamador, "POST /execucoes",
               tb=traceback.format_exc())
    finally:
        repo.close()


def _retomar(config: ConfigApi, execucao_id: str, chamador: str) -> None:
    repo = SQLiteMemoriaRepository(config.db_path)
    trace = ciclo_mod.trace_para_retomada(config.trace_path, execucao_id)
    try:
        perfil = carregar_perfil(config.perfil_path)
        repo.atualizar_execucao_ativa(execucao_id, estado="rodando")
        resultado = ciclo_mod.retomar_ciclo(
            execucao_id=execucao_id,
            perfil=perfil,
            memoria=repo,
            trace=trace,
            gateway=GatewayAprovacaoFila(repo),
        )
        _finalizou(repo, execucao_id, resultado, chamador, "POST /aprovacoes/decidir")
    except RunSuspensa as s:
        _suspendeu(repo, execucao_id, s, chamador, "POST /aprovacoes/decidir")
    except (NotImplementedError, _ErroConfiguracaoAusente) as exc:
        _errou(repo, execucao_id, f"{type(exc).__name__}: {exc}", chamador, "POST /aprovacoes/decidir")
    except Exception as exc:  # noqa: BLE001
        _errou(repo, execucao_id, f"{type(exc).__name__}: {exc}", chamador,
               "POST /aprovacoes/decidir", tb=traceback.format_exc())
    finally:
        repo.close()


def _finalizou(repo, execucao_id, resultado, chamador, rota) -> None:
    motivo = resultado.get("motivo_parada")
    if motivo == "aguardando_intervencao_operador":
        # estado próprio: também segura a trava (execucao_em_andamento) até o
        # operador corrigir a causa e descartar, ou um CLI `retomar` resolver
        # manualmente — não é um "finalizada" de verdade (Etapa 3, front-end).
        repo.atualizar_execucao_ativa(
            execucao_id, estado="aguardando_intervencao", motivo_parada=motivo,
            pergunta_aberta=resultado.get("pergunta_aberta"),
        )
    else:
        repo.atualizar_execucao_ativa(execucao_id, estado="finalizada", motivo_parada=motivo)
    registrar_evento_api(
        rota=rota, metodo="worker", chamador=chamador, resultado=f"finalizada:{motivo}",
        execucao_id=execucao_id,
    )


def _suspendeu(repo, execucao_id, s: RunSuspensa, chamador, rota) -> None:
    repo.atualizar_execucao_ativa(
        execucao_id, estado="suspensa", segundos_ativos=s.segundos_ativos
    )
    registrar_evento_api(
        rota=rota, metodo="worker", chamador=chamador,
        resultado=f"suspensa:{s.etapa}", execucao_id=execucao_id,
        detalhes={"aprovacao_id": s.aprovacao_id},
    )


def _errou(repo, execucao_id, msg, chamador, rota, tb: str | None = None) -> None:
    repo.atualizar_execucao_ativa(execucao_id, estado="erro", motivo_parada=msg)
    registrar_evento_api(
        rota=rota, metodo="worker", chamador=chamador, resultado="erro", nivel="alerta",
        execucao_id=execucao_id, detalhes={"erro": msg, **({"traceback": tb} if tb else {})},
    )
