"""cli.py — a CLI (implementa comandos.md).

Comandos: `rodar`, `validar`, `rastreamento`. Ponto de entrada:
    python -m runtime.cli <comando> [args]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv não instalado — segue só com os.environ
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

from . import ErroConfiguracaoAusente
from . import ciclo as ciclo_mod
from .memoria import SQLiteMemoriaRepository
from .perfil_loader import carregar_perfil
from .trace import Trace, carregar_trace

_BLOCO_YAML_RE = re.compile(r"```yaml\n(.*?)\n```", re.DOTALL)

# comandos.md: os 9 contratos (agent.md + 8 em contracts/)
ARQUIVOS_CONTRATO = [
    "agent.md",
    "contracts/planner.md",
    "contracts/loop.md",
    "contracts/toolbox.md",
    "contracts/rules.md",
    "contracts/executor.md",
    "contracts/skills.md",
    "contracts/hooks.md",
    "contracts/memory.md",
]


def _extrair_yaml(caminho: Path, problemas: list[str] | None = None) -> dict[str, Any] | None:
    """Extrai o primeiro bloco ```yaml``` de um contrato .md. Erros de
    sintaxe são reportados em `problemas` (se fornecida) em vez de
    derrubar `validar` — um contrato com YAML inválido é exatamente o tipo
    de inconsistência que este comando existe pra apontar."""
    if not caminho.exists():
        return None
    texto = caminho.read_text(encoding="utf-8")
    m = _BLOCO_YAML_RE.search(texto)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        if problemas is not None:
            problemas.append(f"{caminho.name}: bloco yaml inválido ({exc.__class__.__name__}: {exc})")
        return None


def _db_path(agente_dir: Path) -> Path:
    valor_env = os.environ.get("DATABASE_PATH")
    if valor_env:
        return Path(valor_env)
    return agente_dir / "dados" / "agente.db"


def _trace_path(agente_dir: Path) -> Path:
    return agente_dir / "dados" / "trace.json"


def _carregar_env(agente_dir: Path) -> None:
    caminho_env = agente_dir / ".env"
    if caminho_env.exists():
        load_dotenv(caminho_env)
    else:
        load_dotenv()  # fallback: .env no diretório atual


# --------------------------------------------------------------------------
# comando: rodar
# --------------------------------------------------------------------------
def comando_rodar(args: argparse.Namespace) -> int:
    agente_dir = Path(args.agente).resolve()
    _carregar_env(agente_dir)

    perfil = carregar_perfil(args.perfil)

    memoria = SQLiteMemoriaRepository(_db_path(agente_dir))
    execucao_id = ciclo_mod.novo_execucao_id()
    trace = Trace(execucao_id=execucao_id, caminho_arquivo=_trace_path(agente_dir))

    try:
        resultado = ciclo_mod.executar_ciclo(
            execucao_id=execucao_id,
            entrada=args.entrada,
            perfil=perfil,
            memoria=memoria,
            trace=trace,
            formato=args.formato,
        )
    except (NotImplementedError, ErroConfiguracaoAusente) as exc:
        # esperado enquanto uma parte do agente está deliberadamente parada
        # (ferramenta ainda não escrita, ou dependência/credencial de
        # propósito ausente — ex: Chromium do Playwright não instalado,
        # UNSPLASH_ACCESS_KEY vazia, ou rodando sem GEMINI_API_KEY/
        # BUNDLE_SOCIAL_API_KEY, ver README.md) — falha limpa em vez de
        # traceback cru.
        print(f"\n[interrompido] {exc}", file=sys.stderr)
        print(
            f"Progresso até aqui em {_trace_path(agente_dir)} "
            f"(execução {execucao_id}, comando `rastreamento`).",
            file=sys.stderr,
        )
        return 1
    finally:
        memoria.close()

    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------
# comando: validar
# --------------------------------------------------------------------------
def comando_validar(args: argparse.Namespace) -> int:
    agente_dir = Path(args.agente).resolve()
    problemas: list[str] = []

    # 1) os 9 arquivos de contrato existem
    for relativo in ARQUIVOS_CONTRATO:
        if not (agente_dir / relativo).exists():
            problemas.append(f"contrato ausente: {relativo}")

    toolbox = _extrair_yaml(agente_dir / "contracts/toolbox.md", problemas) or {}
    skills = _extrair_yaml(agente_dir / "contracts/skills.md", problemas) or {}
    rules = _extrair_yaml(agente_dir / "contracts/rules.md", problemas) or {}
    loop_contrato = _extrair_yaml(agente_dir / "contracts/loop.md", problemas) or {}

    nomes_toolbox = {f["nome"]: f.get("entrada", {}) for f in toolbox.get("ferramentas", [])}
    nomes_skills = {h["nome"]: h.get("entrada", {}) for h in skills.get("habilidades", [])}

    # 2) toolbox.md <-> skills.md consistentes
    if nomes_toolbox.keys() != nomes_skills.keys():
        so_toolbox = nomes_toolbox.keys() - nomes_skills.keys()
        so_skills = nomes_skills.keys() - nomes_toolbox.keys()
        if so_toolbox:
            problemas.append(f"toolbox.md tem ferramentas sem entrada em skills.md: {sorted(so_toolbox)}")
        if so_skills:
            problemas.append(f"skills.md tem habilidades sem entrada em toolbox.md: {sorted(so_skills)}")
    for nome in nomes_toolbox.keys() & nomes_skills.keys():
        if nomes_toolbox[nome] != nomes_skills[nome]:
            problemas.append(f"entrada de '{nome}' diverge entre toolbox.md e skills.md")

    todas_ferramentas = set(nomes_toolbox) | set(nomes_skills)

    # 3) acoes_sensiveis / ferramentas_obrigatorias ⊆ ferramentas conhecidas
    for chave in ("acoes_sensiveis",):
        for nome in rules.get(chave, []) or []:
            if nome not in todas_ferramentas:
                problemas.append(f"rules.md.{chave} referencia ferramenta inexistente: {nome}")
    for nome in rules.get("ferramentas_obrigatorias", []) or []:
        if nome not in todas_ferramentas:
            problemas.append(f"rules.md.ferramentas_obrigatorias referencia ferramenta inexistente: {nome}")

    # 4) max_etapas consistente entre loop.md e rules.md
    max_etapas_loop = loop_contrato.get("ciclo", {}).get("max_etapas")
    max_etapas_rules = (rules.get("limites") or {}).get("max_etapas")
    if max_etapas_loop is not None and max_etapas_rules is not None and max_etapas_loop != max_etapas_rules:
        problemas.append(
            f"max_etapas diverge: loop.md={max_etapas_loop} vs rules.md={max_etapas_rules}"
        )

    # 5) perfil-marca.md de exemplo tem as seções obrigatórias
    caminho_perfil_exemplo = agente_dir / "config-exemplo/perfil-marca.md"
    perfil_exemplo = carregar_perfil(caminho_perfil_exemplo)
    faltando = perfil_exemplo.secoes_faltando()
    if faltando:
        problemas.append(
            f"config-exemplo/perfil-marca.md sem seções obrigatórias: {faltando}"
        )

    if problemas:
        print(f"validar: {len(problemas)} problema(s) encontrado(s):")
        for p in problemas:
            print(f"  - {p}")
        return 1

    print("validar: os 9 contratos estão completos e consistentes entre si.")
    return 0


# --------------------------------------------------------------------------
# comando: rastreamento
# --------------------------------------------------------------------------
def comando_rastreamento(args: argparse.Namespace) -> int:
    agente_dir = Path(args.agente).resolve() if args.agente else Path.cwd()
    trace = carregar_trace(_trace_path(agente_dir))
    if trace is None:
        print("rastreamento: nenhuma execução encontrada ainda.")
        return 1
    print(json.dumps(trace, ensure_ascii=False, indent=2))
    return 0


def _montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agente-social-media")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_rodar = subparsers.add_parser("rodar", help="executa o agente com uma entrada")
    p_rodar.add_argument("--agente", required=True)
    # comandos.md: --entrada é opcional. Omitido, o planejador escolhe o tema
    # a partir de pesquisar_tendencias_nicho (ver contracts/planner.md) —
    # comportamento goal_oriented.
    p_rodar.add_argument("--entrada", required=False, default=None)
    p_rodar.add_argument("--perfil", required=True)
    # extensão desta ideação (mesmo espírito de --perfil em comandos.md):
    # nenhum contrato define como o formato da peça é escolhido — default
    # documentado em planejador.FORMATO_PADRAO, sobrescrevível aqui.
    p_rodar.add_argument(
        "--formato", required=False, default=ciclo_mod.FORMATO_PADRAO,
        choices=["reel", "carrossel", "estatico"],
    )
    p_rodar.set_defaults(func=comando_rodar)

    p_validar = subparsers.add_parser(
        "validar", help="valida se os 9 contratos estao completos e consistentes entre si"
    )
    p_validar.add_argument("--agente", required=True)
    p_validar.set_defaults(func=comando_validar)

    p_rastreamento = subparsers.add_parser(
        "rastreamento", help="exibe o trace da ultima execucao"
    )
    p_rastreamento.add_argument("--agente", required=False, default=".")
    p_rastreamento.set_defaults(func=comando_rastreamento)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _montar_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
