---
nicho: "IA aplicada para lojas de móveis planejados e marcenarias (B2B)"
rede: instagram
tom: "direto, consultivo, com exemplos concretos do dia a dia da loja — sem jargão técnico de IA"
---

# Perfil de marca — Moveleiro.IA

## ICP (Perfil de Cliente Ideal)

- **Quem:** donos/gestores de lojas de móveis planejados e marcenarias de
  pequeno/médio porte.
- **Onde vendem:** loja física + WhatsApp/Instagram como canal principal de
  atendimento e fechamento.
- **Dores (em ordem de prioridade):**
  1. **Perde venda por demorar pra responder o cliente** no WhatsApp/Instagram
     (dor #1 — é o gancho mais forte de conteúdo).
  2. Processo manual de orçamento e medidas trava a operação.
  3. Não sabe usar IA e tem medo de ficar pra trás da concorrência.
- **Desejos:** vender mais sem contratar mais gente, parecer moderno e
  profissional, não perder lead por lentidão.

## Marca

- **Promessa central:** IA prática (não hype) pra loja de móveis vender mais
  e atender mais rápido.
- **Tom de voz:** direto, consultivo, com exemplos concretos da rotina da
  loja — nunca "tecniquês" de IA.
- **Nunca fazer:**
  - Prometer "substituir o vendedor".
  - Falar de IA de forma abstrata/genérica sem conectar à rotina real da
    loja (orçamento, medida, atendimento).
  - Usar termos técnicos de IA sem tradução pro dia a dia do dono de loja.

## Oferta

1. Atendimento via WhatsApp/IA (respostas automáticas, orçamento inicial).
2. Automação de vendas/orçamentos (medidas, projetos, follow-up).
3. Marketing/geração de leads com IA.

As três frentes podem aparecer em conteúdo, mas **resposta rápida ao
cliente (dor #1)** é o gancho com maior potencial de viralizar e ainda
vender ao mesmo tempo — priorizar esse ângulo quando o tema permitir.

## Diretriz de conteúdo viral x vendedor

- Pode e deve usar ganchos virais de dor real da loja (ex: "cliente mandou
  mensagem sexta à noite e você só respondeu segunda de manhã — adivinha se
  ele ainda quis comprar").
- Todo conteúdo viral precisa fechar conectando com uma das 3 frentes de
  oferta, mesmo que sutilmente — não é viral por viral, é viral que vende.
- CTA nem sempre é "compre agora" — pode ser diagnóstico gratuito,
  comentário, ou salvar o post pra usar depois.

## Identidade Visual (carrossel/estático)

Baseado em referências reais aprovadas (linhas @brandsdecoded__ e Content
Machine) — tipografia forte carregando o gancho, identidade fixa de
cabeçalho/rodapé, e foto real só quando agrega. Renderizado por template
de código, nunca por IA generativa (ver decisoes-de-engenharia.md, seção 2).

Os design tokens abaixo são lidos pelo motor de template (`perfil_loader.py`
extrai este bloco `yaml`). A prosa que segue é a explicação humana da mesma
coisa — o que vale pro código é o bloco. Qualquer chave omitida cai no
default embutido em `runtime/perfil_loader.py` (`IDENTIDADE_VISUAL_PADRAO`).

```yaml
dimensoes:
  largura: 1080
  altura: 1350          # retrato 4:5 — melhor alcance no feed
cores:
  fundo: "#F1ECE4"       # bege/off-white quente
  texto: "#1F1710"       # marrom escuro quase preto — nunca preto puro
  destaque: "#C1622D"    # terracota/âmbar — só em palavras/números que saltam
  linha: "#1F1710"       # linha fina do rodapé
tipografia:
  familia_titulo: "'Anton', 'Archivo Black', 'Arial Narrow', sans-serif"
  familia_corpo: "'Inter', 'Helvetica Neue', Arial, sans-serif"
  peso_titulo: 800       # gancho: bem pesado, condensado, caixa alta
  peso_corpo: 400
  google_fonts_url: "https://fonts.googleapis.com/css2?family=Anton&family=Inter:wght@400;600;700&display=swap"
cabecalho:
  arroba: "@moveleiro.ia"
  indicador_arraste: "arraste →"
rodape:
  mostrar_contador: true  # contador de slide "3/8"
```

**Paleta (tom quente/madeira — remete ao móvel):**
- Fundo padrão: bege/off-white quente (ex: `#F1ECE4`)
- Texto principal: marrom escuro quase preto (ex: `#1F1710`), nunca preto puro
- Cor de destaque (títulos-chave, números, CTA): terracota/âmbar (ex:
  `#C1622D`) — usar com moderação, só em palavras/números que precisam
  saltar aos olhos, nunca o texto inteiro
- *(Placeholder — ajustar pro hex exato assim que houver um guia de marca
  formal da Moveleiro.IA; a direção "quente/madeira" já está validada.)*

**Tipografia:**
- Título/gancho: peso bem pesado (800–900), condensada, tudo em caixa alta
  quando for o gancho principal do slide
- Corpo: peso regular, boa altura de linha, sem caixa alta

**Estrutura fixa de cabeçalho/rodapé (todo slide, sem exceção):**
- Topo: @ da Moveleiro.IA (esquerda) + seta ou indicador de "arraste"
  (direita)
- Rodapé: linha fina horizontal + contador de slide (ex: "3/8")

**Tipos de layout (`tipo_layout`, ver skills.md):**
- `capa` — gancho grande, sem corpo extenso, é o slide 1
- `texto_grande` — título forte + parágrafo curto de apoio
- `lista_numerada` — título + itens numerados (01, 02, 03...) com o
  numeral na cor de destaque
- `diagrama_processo` — sequência de passos com ícone + seta conectando
- `comparacao` — antes/depois, ou frase em destaque dentro de uma caixa
  com borda na cor de destaque
- `foto_split` — metade da tela com foto real (banco de estoque), metade
  com texto — usar quando uma foto de ambiente/atendimento real agrega
  mais que texto sozinho
- `cta` — fechamento com a chamada de ação, geralmente com uma caixa de
  destaque pro comentário/gatilho

**Fotos (quando `foto_split` ou `capa` pedir):**
- Sempre fotografia real de banco de estoque licenciado (Unsplash/Pexels)
  — nunca gente gerada por IA
- Temas preferenciais: ambiente de loja de móveis/marcenaria, atendimento
  via celular/WhatsApp, dono de loja no dia a dia — nunca imagem genérica
  de "escritório corporativo" sem relação com o nicho
