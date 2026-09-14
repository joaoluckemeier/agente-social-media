"""api/ — casca HTTP fina por cima do agente-social-media.

NÃO faz parte do runtime do agente (contratos + ciclo). É uma interface
estável, adicional, que o componente `front-end` (~/agents/front-end/)
consome como cliente externo — o front-end nunca importa `runtime/`
diretamente (ver ~/agents/front-end/arquitetura.md, seção 1).

Garantias (arquitetura.md, "Segurança dessa interface interna"):
  - bind só em 127.0.0.1 — nunca alcançável pela internet;
  - autenticação por chave compartilhada (env `AGENTE_API_KEY`) em todo
    request — não JWT (conexão máquina-a-máquina, um único chamador);
  - toda ação passa pela MESMA lógica de `runtime/` que o CLI usa —
    nunca um caminho paralelo mais permissivo;
  - toda chamada fica registrada no trace com `origem="api"`.

O CLI (`python -m runtime.cli rodar ...`) continua funcionando igual —
esta casca é adicional, não uma substituição.
"""

from __future__ import annotations
