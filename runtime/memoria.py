"""memoria.py — Repository de persistência (implementa memory.md + a seção 3
de decisoes-de-engenharia.md).

Todo acesso a banco do runtime passa por `MemoriaRepository`. Nenhum outro
módulo deve abrir o SQLite diretamente (decisão registrada em
decisoes-de-engenharia.md, seção 3 — troca futura para Postgres, e ponto de
handoff com o agente-analista-metricas via as tabelas `posts`/`insights`).
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Campos que memory.md manda guardar na memória curta. Qualquer `tipo` fora
# desta lista ainda é aceito (não é um contrato fechado sobre o schema), mas
# esses são os nomes usados pelo restante do runtime.
TIPOS_GUARDAVEIS = {
    "resultado_de_ferramenta",
    "decisao_do_planejador",
    "insights_recebidos",
    "evidencia_coletada",
    "roteiro_aprovado",
    "feedback_de_aprovacao",
    # tema escolhido pelo planejador a partir de temas_sugeridos quando o
    # agente roda sem --entrada (planner.md/comandos.md) — equivale a um
    # --entrada explícito daí pra frente.
    "tema_escolhido",
}

MAX_REGISTROS_MEMORIA_CURTA = 40  # memory.md: memoria_curta.max_registros


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RegistroMemoria:
    id: int | None
    execucao_id: str
    tipo: str
    conteudo: dict[str, Any]
    criado_em: str = field(default_factory=_agora_iso)


class MemoriaRepository(ABC):
    """Interface de persistência. Trocar SQLite por outro banco significa
    implementar esta interface de novo — nada mais no runtime muda."""

    # -- memória curta (memory.md) ------------------------------------
    @abstractmethod
    def guardar_memoria(self, execucao_id: str, tipo: str, conteudo: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def listar_memoria(self, execucao_id: str, tipo: str | None = None) -> list[RegistroMemoria]:
        ...

    # -- tabela posts (decisoes-de-engenharia.md, seção 3) -------------
    @abstractmethod
    def upsert_post(self, post: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def buscar_post(self, post_id: str) -> dict[str, Any] | None:
        ...

    # -- tabela insights (escrita pelo agente-analista-metricas) -------
    @abstractmethod
    def buscar_insights_recentes(self, limite: int) -> list[dict[str, Any]]:
        ...

    # -- resumo final (memory.md: resumo_final) ------------------------
    @abstractmethod
    def salvar_resumo_final(self, execucao_id: str, resumo: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def buscar_resumo_final(self, execucao_id: str) -> dict[str, Any] | None:
        ...

    # -- cache (decisoes-de-engenharia.md, seção 4: cache curto só em
    # pesquisar_tendencias_nicho) — extensão de engenharia, não faz parte
    # de nenhum contrato de saída; vive atrás do Repository como tudo mais
    # que toca o banco.
    @abstractmethod
    def obter_cache(self, chave: str) -> dict[str, Any] | None:
        """None se não existir ou se tiver expirado."""
        ...

    @abstractmethod
    def salvar_cache(self, chave: str, valor: dict[str, Any], ttl_segundos: int) -> None:
        ...


class SQLiteMemoriaRepository(MemoriaRepository):
    """Implementação v1 (decisoes-de-engenharia.md, seção 3)."""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._criar_schema()

    def _criar_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memoria_curta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execucao_id TEXT NOT NULL,
                tipo TEXT NOT NULL,
                conteudo TEXT NOT NULL,
                criado_em TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memoria_execucao
                ON memoria_curta (execucao_id, tipo);

            CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT PRIMARY KEY,
                tema TEXT,
                roteiro TEXT,
                peca_url TEXT,
                rede TEXT,
                status_aprovacao TEXT,
                status_publicacao TEXT,
                publicado_em TEXT
            );

            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                insight TEXT,
                recomendacao TEXT,
                gerado_por TEXT,
                gerado_em TEXT
            );

            CREATE TABLE IF NOT EXISTS resumos_finais (
                execucao_id TEXT PRIMARY KEY,
                resumo TEXT NOT NULL,
                criado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cache (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL,
                expira_em TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    # -- memória curta ---------------------------------------------------
    def guardar_memoria(self, execucao_id: str, tipo: str, conteudo: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO memoria_curta (execucao_id, tipo, conteudo, criado_em) VALUES (?, ?, ?, ?)",
            (execucao_id, tipo, json.dumps(conteudo, ensure_ascii=False), _agora_iso()),
        )
        self._conn.commit()
        self._aplicar_max_registros(execucao_id)

    def _aplicar_max_registros(self, execucao_id: str) -> None:
        """memory.md: max_registros: 40 — descarta os mais antigos além do
        limite, dentro dos tipos marcados como descartáveis quando o limite
        é ultrapassado."""
        total = self._conn.execute(
            "SELECT COUNT(*) FROM memoria_curta WHERE execucao_id = ?", (execucao_id,)
        ).fetchone()[0]
        excedente = total - MAX_REGISTROS_MEMORIA_CURTA
        if excedente > 0:
            ids_antigos = self._conn.execute(
                "SELECT id FROM memoria_curta WHERE execucao_id = ? ORDER BY id ASC LIMIT ?",
                (execucao_id, excedente),
            ).fetchall()
            self._conn.executemany(
                "DELETE FROM memoria_curta WHERE id = ?", [(row["id"],) for row in ids_antigos]
            )
            self._conn.commit()

    def listar_memoria(self, execucao_id: str, tipo: str | None = None) -> list[RegistroMemoria]:
        if tipo is None:
            rows = self._conn.execute(
                "SELECT * FROM memoria_curta WHERE execucao_id = ? ORDER BY id ASC",
                (execucao_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memoria_curta WHERE execucao_id = ? AND tipo = ? ORDER BY id ASC",
                (execucao_id, tipo),
            ).fetchall()
        return [
            RegistroMemoria(
                id=row["id"],
                execucao_id=row["execucao_id"],
                tipo=row["tipo"],
                conteudo=json.loads(row["conteudo"]),
                criado_em=row["criado_em"],
            )
            for row in rows
        ]

    # -- posts -------------------------------------------------------
    def upsert_post(self, post: dict[str, Any]) -> None:
        campos = (
            "post_id",
            "tema",
            "roteiro",
            "peca_url",
            "rede",
            "status_aprovacao",
            "status_publicacao",
            "publicado_em",
        )
        post = dict(post)
        # decisão revista (skills.md: gerar_peca_visual): carrossel de
        # verdade tem várias peças — a coluna `peca_url` (TEXT) guarda a
        # lista serializada em JSON em vez de mudar o schema da tabela.
        if isinstance(post.get("peca_url"), list):
            post["peca_url"] = json.dumps(post["peca_url"], ensure_ascii=False)
        valores = tuple(post.get(c) for c in campos)
        placeholders = ", ".join("?" for _ in campos)
        atualizacoes = ", ".join(f"{c}=excluded.{c}" for c in campos if c != "post_id")
        self._conn.execute(
            f"INSERT INTO posts ({', '.join(campos)}) VALUES ({placeholders}) "
            f"ON CONFLICT(post_id) DO UPDATE SET {atualizacoes}",
            valores,
        )
        self._conn.commit()

    def buscar_post(self, post_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM posts WHERE post_id = ?", (post_id,)
        ).fetchone()
        if row is None:
            return None
        post = dict(row)
        if post.get("peca_url"):
            try:
                post["peca_url"] = json.loads(post["peca_url"])
            except (json.JSONDecodeError, TypeError):
                pass  # posts antigos (v1, antes do carrossel) guardavam string simples
        return post

    # -- insights (lidos aqui; escritos pelo agente-analista-metricas) --
    def buscar_insights_recentes(self, limite: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM insights ORDER BY gerado_em DESC LIMIT ?", (limite,)
        ).fetchall()
        return [dict(row) for row in rows]

    # -- resumo final --------------------------------------------------
    def salvar_resumo_final(self, execucao_id: str, resumo: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO resumos_finais (execucao_id, resumo, criado_em) VALUES (?, ?, ?) "
            "ON CONFLICT(execucao_id) DO UPDATE SET resumo=excluded.resumo, criado_em=excluded.criado_em",
            (execucao_id, json.dumps(resumo, ensure_ascii=False), _agora_iso()),
        )
        self._conn.commit()

    def buscar_resumo_final(self, execucao_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT resumo FROM resumos_finais WHERE execucao_id = ?", (execucao_id,)
        ).fetchone()
        return json.loads(row["resumo"]) if row else None

    # -- cache ---------------------------------------------------------
    def obter_cache(self, chave: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT valor, expira_em FROM cache WHERE chave = ?", (chave,)
        ).fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row["expira_em"]) < datetime.now(timezone.utc):
            self._conn.execute("DELETE FROM cache WHERE chave = ?", (chave,))
            self._conn.commit()
            return None
        return json.loads(row["valor"])

    def salvar_cache(self, chave: str, valor: dict[str, Any], ttl_segundos: int) -> None:
        from datetime import timedelta

        expira_em = (datetime.now(timezone.utc) + timedelta(seconds=ttl_segundos)).isoformat()
        self._conn.execute(
            "INSERT INTO cache (chave, valor, expira_em) VALUES (?, ?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, expira_em=excluded.expira_em",
            (chave, json.dumps(valor, ensure_ascii=False), expira_em),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
