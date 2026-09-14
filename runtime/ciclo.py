"""ciclo.py — o motor (implementa contracts/loop.md).

Orquestra planejador.py -> executor.py em loop, aplicando as 5
condicoes_parada de loop.md, e grava o resumo final (memory.md:
resumo_final) ao terminar. A saída de `executar_ciclo` segue o
contrato_saida de agent.md.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .aprovacao import GatewayAprovacao, RunSuspensa
from .aprovacao.gateway_cli import GatewayAprovacaoCLI
from .executor import ConfirmacaoHumanaNegada, LimiteDeChamadasExcedido, executar_ferramenta
from .memoria import MemoriaRepository
from .perfil_loader import PerfilMarca
from .planejador import FORMATO_PADRAO, decidir_proxima_acao, roteiro_como_texto
from .trace import Trace, carregar_trace

# loop.md
OBJETIVO = "gerar_conteudo_engajante_conectado_a_oferta"
MAX_ETAPAS = 12
LIMITE_TEMPO_SEGUNDOS = 1800

CondicaoParada = str  # objetivo_alcancado | max_etapas_excedido | sem_progresso
# | limite_tempo_excedido | confirmacao_humana_negada


def novo_execucao_id() -> str:
    hoje = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    return f"post_{hoje}_{uuid.uuid4().hex[:6]}"


def _tema_registrado(memoria: MemoriaRepository, execucao_id: str) -> str | None:
    """Tema escolhido pelo planejador quando o agente roda sem --entrada
    (planner.md) — gravado na memória curta como `tema_escolhido`. None se a
    execução teve --entrada explícito ou ainda não chegou na escolha."""
    registros = memoria.listar_memoria(execucao_id, tipo="tema_escolhido")
    return registros[-1].conteudo.get("tema") if registros else None


def _estado_conhecido(memoria: MemoriaRepository, execucao_id: str) -> dict[str, Any]:
    """Reconstrói do histórico o que já se sabe sobre o post em andamento,
    pra popular o contrato_saida de agent.md mesmo quando o ciclo pára antes
    de publicar_conteudo."""
    hist = [r.conteudo for r in memoria.listar_memoria(execucao_id, tipo="resultado_de_ferramenta")]
    estado: dict[str, Any] = {
        "slides": [],
        "roteiro": None,  # texto derivado dos slides — legenda / tabela posts
        "pecas_urls": [],
        "status_aprovacao": "pendente",
        "status_publicacao": "nao_publicado",
    }
    for registro in hist:
        nome = registro.get("ferramenta")
        saida = registro.get("saida") or {}
        if nome == "gerar_roteiro":
            estado["slides"] = saida.get("slides", [])
            estado["roteiro"] = roteiro_como_texto(estado["slides"])
        elif nome == "gerar_peca_visual":
            estado["pecas_urls"] = saida.get("pecas_urls", [])
        elif nome == "solicitar_aprovacao_humana":
            estado["status_aprovacao"] = "aprovado" if saida.get("aprovado") else "reprovado"
        elif nome == "publicar_conteudo":
            estado["status_publicacao"] = saida.get("status", estado["status_publicacao"])
    return estado


def _ferramentas_chamadas(memoria: MemoriaRepository, execucao_id: str) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for r in memoria.listar_memoria(execucao_id, tipo="resultado_de_ferramenta"):
        nome = r.conteudo.get("ferramenta")
        contagem[nome] = contagem.get(nome, 0) + 1
    return contagem


def _custo_total(memoria: MemoriaRepository, execucao_id: str) -> dict[str, Any]:
    """decisoes-de-engenharia.md, seção 8: custo estimado por execução."""
    tokens_openai = 0
    usd_gemini = 0.0
    for r in memoria.listar_memoria(execucao_id, tipo="custo_ferramenta"):
        c = r.conteudo
        if c.get("provedor") == "openai":
            tokens_openai += c.get("tokens_entrada", 0) + c.get("tokens_saida", 0)
        elif c.get("provedor") == "gemini":
            usd_gemini += c.get("usd_estimado", 0.0)
    return {"tokens_openai": tokens_openai, "usd_estimado_gemini": round(usd_gemini, 4)}


def _taxa_reprovacao_por_etapa(memoria: MemoriaRepository, execucao_id: str) -> dict[str, dict[str, int]]:
    """decisoes-de-engenharia.md, seção 8: taxa de reprovação por etapa
    (roteiro vs visual) — sinaliza se perfil-marca.md está calibrado."""
    resultado: dict[str, dict[str, int]] = {"roteiro": {"aprovado": 0, "reprovado": 0}, "visual": {"aprovado": 0, "reprovado": 0}}
    for r in memoria.listar_memoria(execucao_id, tipo="resultado_de_ferramenta"):
        c = r.conteudo
        if c.get("ferramenta") != "solicitar_aprovacao_humana":
            continue
        etapa = (c.get("argumentos") or {}).get("etapa")
        if etapa not in resultado:
            continue
        chave = "aprovado" if (c.get("saida") or {}).get("aprovado") else "reprovado"
        resultado[etapa][chave] += 1
    return resultado


def executar_ciclo(
    *,
    execucao_id: str,
    entrada: str | None = None,
    perfil: PerfilMarca,
    memoria: MemoriaRepository,
    trace: Trace,
    formato: str = FORMATO_PADRAO,
    gateway: GatewayAprovacao | None = None,
    segundos_ja_gastos: float = 0.0,
) -> dict[str, Any]:
    # gateway padrão = CLI síncrono (comportamento de sempre). A casca HTTP
    # passa GatewayAprovacaoFila; nesse caso solicitar_aprovacao_humana pode
    # levantar RunSuspensa e a execução é suspensa até a decisão chegar.
    gateway = gateway or GatewayAprovacaoCLI()
    modo_fila = not isinstance(gateway, GatewayAprovacaoCLI)

    tempo_inicio = time.monotonic()
    condicao_parada: CondicaoParada | None = None
    pergunta_anterior: str | None = None
    pergunta_para_operador: str | None = None  # só preenchida em aguardando_intervencao_operador

    def _segundos_ativos() -> float:
        # loop.md: limite_tempo_segundos conta só processamento ativo — o
        # tempo em que a execução ficou suspensa esperando decisão humana
        # (modo fila) fica de fora, senão uma aprovação que demora um dia
        # dispararia limite_tempo_excedido por engano.
        return segundos_ja_gastos + (time.monotonic() - tempo_inicio)

    for etapa in range(1, MAX_ETAPAS + 1):
        if _segundos_ativos() > LIMITE_TEMPO_SEGUNDOS:
            condicao_parada = "limite_tempo_excedido"
            break

        decisao = decidir_proxima_acao(
            memoria=memoria, execucao_id=execucao_id, perfil=perfil, entrada=entrada, formato=formato
        )
        trace.antes_da_etapa(etapa=etapa, decisao=asdict(decisao))
        # unica: numa retomada, os primeiros passos re-derivam decisões já
        # registradas (mesma etapa de aprovação antes/depois da suspensão) —
        # o dedup evita inflar memoria_curta. Não afeta lógica: nenhum módulo
        # lê `decisao_do_planejador` (é espelho do trace).
        memoria.guardar_memoria_unica(execucao_id, "decisao_do_planejador", asdict(decisao))

        if decisao.proxima_acao == "FINALIZAR":
            trace.apos_etapa(etapa=etapa, resultado="finalizado")
            condicao_parada = "objetivo_alcancado"
            break

        if decisao.proxima_acao == "PERGUNTAR_USUARIO":
            if modo_fila:
                # Sem stdin no worker da casca HTTP. PERGUNTAR_USUARIO aqui
                # (perfil incompleto, feedback vazio, pedido de métricas) pede
                # intervenção do operador — pára com um motivo claro em vez de
                # travar o thread num input(). O operador corrige e redispara.
                memoria.guardar_memoria(
                    execucao_id, "feedback_de_aprovacao",
                    {"pergunta": decisao.pergunta, "resposta": None, "origem": "fila"},
                )
                trace.apos_etapa(
                    etapa=etapa, resultado="aguardando_intervencao_operador",
                    pergunta=decisao.pergunta,
                )
                condicao_parada = "aguardando_intervencao_operador"
                pergunta_para_operador = decisao.pergunta
                break
            # loop.md não lista PERGUNTAR_USUARIO como condição de parada —
            # o ciclo continua após a resposta. Guarda contra loop infinito:
            # se a mesma pergunta reaparecer sem nada ter mudado no estado
            # persistido, é sem_progresso (nenhuma ferramenta nova saberia o
            # que fazer com uma segunda resposta livre sem lógica adicional
            # de re-injeção, que é matéria do próximo plano).
            if decisao.pergunta == pergunta_anterior:
                trace.apos_etapa(etapa=etapa, resultado="pergunta_repetida_sem_progresso")
                condicao_parada = "sem_progresso"
                break
            pergunta_anterior = decisao.pergunta
            print(f"\n[PERGUNTA] {decisao.pergunta}")
            resposta = input("> ").strip()
            memoria.guardar_memoria(
                execucao_id, "feedback_de_aprovacao", {"pergunta": decisao.pergunta, "resposta": resposta}
            )
            trace.apos_etapa(etapa=etapa, pergunta=decisao.pergunta, resposta=resposta)
            continue

        # CHAMAR_FERRAMENTA
        pergunta_anterior = None
        assert decisao.nome_ferramenta is not None
        try:
            executar_ferramenta(
                nome_ferramenta=decisao.nome_ferramenta,
                argumentos_ferramenta=decisao.argumentos_ferramenta or {},
                execucao_id=execucao_id,
                memoria=memoria,
                trace=trace,
                gateway=gateway,
            )
        except RunSuspensa as suspensa:
            # gateway de fila: pendência criada, ninguém decidiu ainda. Anexa
            # o tempo ativo acumulado (pra retomada continuar a contagem de
            # limite_tempo daqui) e propaga — quem orquestra persiste o
            # estado 'suspensa'.
            suspensa.segundos_ativos = _segundos_ativos()
            trace.apos_etapa(
                etapa=etapa,
                resultado="suspenso_para_aprovacao",
                etapa_aprovacao=suspensa.etapa,
                aprovacao_id=suspensa.aprovacao_id,
            )
            raise
        except ConfirmacaoHumanaNegada:
            condicao_parada = "confirmacao_humana_negada"
            trace.apos_etapa(etapa=etapa, resultado="confirmacao_humana_negada")
            break
        except LimiteDeChamadasExcedido:
            condicao_parada = "sem_progresso"
            trace.apos_etapa(etapa=etapa, resultado="limite_de_chamadas_excedido")
            break
        trace.apos_etapa(etapa=etapa, ferramenta=decisao.nome_ferramenta)
    else:
        condicao_parada = "max_etapas_excedido"

    estado = _estado_conhecido(memoria, execucao_id)
    ferramentas_chamadas = _ferramentas_chamadas(memoria, execucao_id)
    # --entrada explícito, ou o tema que o planejador escolheu de
    # temas_sugeridos quando rodou sem --entrada (planner.md). Fica None só se
    # a execução parou antes de a escolha acontecer.
    tema = (entrada.strip() if entrada and entrada.strip()
            else _tema_registrado(memoria, execucao_id))

    resumo_final = {
        # memory.md: campos obrigatórios do resumo_final
        "objetivo": OBJETIVO,
        "etapas_executadas": sum(ferramentas_chamadas.values()),
        "ferramentas_chamadas": ferramentas_chamadas,
        "resultado_final": condicao_parada,
        "proximos_passos": (
            "publicado com sucesso" if condicao_parada == "objetivo_alcancado"
            else f"execução interrompida ({condicao_parada}) — revisar trace.json e, se aplicável, rodar novamente"
        ),
        # extensão — decisoes-de-engenharia.md, seção 8: custo e taxa de
        # reprovação por etapa, não fazem parte dos campos exigidos por
        # memory.md mas são o que a seção 8 pede pra rastrear por execução.
        "custo_estimado": _custo_total(memoria, execucao_id),
        "taxa_reprovacao_por_etapa": _taxa_reprovacao_por_etapa(memoria, execucao_id),
    }
    memoria.salvar_resumo_final(execucao_id, resumo_final)

    # agent.md: contrato_saida — `slides` (estruturado) e `pecas_visuais_urls`
    # (lista, 1 peça por slide) são campos obrigatórios.
    resultado = {
        "post_id": execucao_id,
        "tema": tema,
        "slides": estado["slides"],
        "pecas_visuais_urls": estado["pecas_urls"],
        "rede": perfil.rede or "instagram",
        "status_aprovacao": estado["status_aprovacao"],
        "status_publicacao": estado["status_publicacao"],
        "motivo_parada": condicao_parada,
        # extensão (Etapa 3, front-end): só presente quando motivo_parada é
        # aguardando_intervencao_operador — o worker persiste em
        # execucao_ativa.pergunta_aberta pra a interface poder mostrá-la.
        "pergunta_aberta": pergunta_para_operador,
    }

    if condicao_parada == "objetivo_alcancado":
        memoria.upsert_post(
            {
                "post_id": execucao_id,
                "tema": tema,
                "roteiro": estado["roteiro"],
                "peca_url": estado["pecas_urls"],  # MemoriaRepository serializa a lista — ver memoria.py
                "rede": perfil.rede or "instagram",
                "status_aprovacao": estado["status_aprovacao"],
                "status_publicacao": estado["status_publicacao"],
                "publicado_em": _agora_iso(),
            }
        )

    return resultado


def retomar_ciclo(
    *,
    execucao_id: str,
    perfil: PerfilMarca,
    memoria: MemoriaRepository,
    trace: Trace,
    gateway: GatewayAprovacao,
) -> dict[str, Any]:
    """Retoma uma execução suspensa (gateway de fila). Lê `entrada`/`formato`
    e o tempo ativo já gasto de `execucao_ativa`; o planejador reconstrói
    todo o resto a partir de `memoria_curta` + a decisão recém-registrada em
    `aprovacoes`. Mesmo caminho de validação de `executar_ciclo` — nada
    paralelo."""
    est = memoria.buscar_execucao_ativa(execucao_id)
    if est is None:
        raise ValueError(f"execução {execucao_id} não encontrada em execucao_ativa")
    if est["estado"] not in ("suspensa", "rodando"):
        raise ValueError(
            f"execução {execucao_id} está '{est['estado']}' — não dá pra retomar"
        )
    return executar_ciclo(
        execucao_id=execucao_id,
        entrada=est.get("entrada"),
        perfil=perfil,
        memoria=memoria,
        trace=trace,
        formato=est.get("formato") or FORMATO_PADRAO,
        gateway=gateway,
        segundos_ja_gastos=float(est.get("segundos_ativos") or 0.0),
    )


def trace_para_retomada(caminho, execucao_id: str) -> Trace:
    """Reabre o trace.json da execução pra APENDAR eventos na retomada, em vez
    de truncar. Se o arquivo for de outra execução, começa vazio."""
    previo = carregar_trace(caminho)
    eventos = previo["eventos"] if previo and previo.get("execucao_id") == execucao_id else []
    return Trace(execucao_id=execucao_id, caminho_arquivo=caminho, eventos=list(eventos))


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
