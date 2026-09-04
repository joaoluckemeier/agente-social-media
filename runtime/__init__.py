"""runtime/ — implementação executável dos contratos do agente-social-media.

Cada módulo aqui referencia explicitamente o contrato (.md) que implementa.
Ver ESTRUTURA-PASTAS.md para o mapa completo.
"""

from __future__ import annotations


class ErroConfiguracaoAusente(RuntimeError):
    """Credencial/config obrigatória (.env) não encontrada — ex: uma
    ferramenta que depende de um provedor (Gemini, bundle.social) ainda não
    configurado de propósito, porque essa parte do agente está parada numa
    fase posterior (ver README.md). Fica neste __init__.py (em vez de em
    executor.py) só pra não criar import circular: ferramentas/geracao_visual/
    adapters levantam essa exceção, e executor.py já importa ferramentas —
    não pode ser o contrário.

    cli.py trata isso separado de um bug de verdade: pára a execução com uma
    mensagem clara em vez de um traceback cru, e sem confundir com
    NotImplementedError (ferramenta ainda não escrita)."""
