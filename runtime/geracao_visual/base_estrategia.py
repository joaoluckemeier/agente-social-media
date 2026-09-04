"""geracao_visual/base_estrategia.py — interface Strategy + storage local.

decisoes-de-engenharia.md, seção 2: a geração de imagem não usa mais IA
generativa (é motor de template — ver geracao_visual/imagem/). Esta
interface Strategy hoje é usada só pelo caminho de vídeo (geracao_visual/
video/, Veo), mas continua existindo pra manter a porta aberta a um segundo
provedor de vídeo sem tocar em ferramentas/gerar_peca_visual.py nem em
executor.py (OCP).

`salvar_peca_localmente` é o ponto único de storage local — usado tanto
pelas estratégias de vídeo quanto pelo motor de template de imagem.
"""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# só o que é seguro num nome de arquivo — o resto é removido
_NOME_SEGURO_RE = re.compile(r"[^A-Za-z0-9._-]+")

# Lacuna não coberta por nenhum contrato: skills.md pede peca_url (uma URL),
# mas nenhum documento define storage/CDN pra hospedar a peça gerada. Opção
# adotada nesta implementação, sem credencial nova: salvar localmente em
# dados/pecas/ e devolver o caminho local — adapters/redes_sociais faz
# upload direto do arquivo pra bundle.social (a maioria das APIs unificadas
# aceita isso), sem precisar de storage público. Se algum dia bundle.social
# exigir uma URL pública em vez de upload de arquivo, é aqui que se troca.
_DIR_PECAS = Path(__file__).resolve().parents[2] / "dados" / "pecas"


def salvar_peca_localmente(dados_binarios: bytes, extensao: str, nome: str | None = None) -> str:
    """Salva em dados/pecas/. `nome` (sem extensão) define o nome do arquivo
    — agent.md fixa a convenção `{post_id}_slide{ordem}` (ver
    ferramentas/gerar_peca_visual.py). Sem `nome` (ou nome vazio depois de
    sanitizado), cai num hash aleatório."""
    _DIR_PECAS.mkdir(parents=True, exist_ok=True)
    base = _NOME_SEGURO_RE.sub("", nome or "") or uuid.uuid4().hex
    caminho = _DIR_PECAS / f"{base}.{extensao.lstrip('.')}"
    caminho.write_bytes(dados_binarios)
    return str(caminho)


class EstrategiaGeracaoVisual(ABC):
    @abstractmethod
    def gerar(self, *, roteiro: str, formato: str, nome_base: str | None = None) -> dict[str, Any]:
        """Retorna {"peca_url": str, "formato": str}. `nome_base`: nome do
        arquivo sem extensão (convenção de agent.md)."""
        raise NotImplementedError
