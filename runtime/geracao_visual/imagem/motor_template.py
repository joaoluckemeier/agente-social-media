"""geracao_visual/imagem/motor_template.py — Template Method.

Recebe uma string HTML já montada (ver selecionar_template.py) e renderiza
um PNG com Chromium headless (Playwright), no tamanho da peça definido nos
design tokens. Salva pelo mesmo ponto único de storage local usado pelo
resto da geração visual (`geracao_visual/base_estrategia.salvar_peca_localmente`).

Timeout e retry são aplicados por executor.py, não aqui — mesmo padrão das
estratégias de vídeo.
"""

from __future__ import annotations

from typing import Any

from ... import ErroConfiguracaoAusente
from ..base_estrategia import salvar_peca_localmente

# margem extra pra as web fonts (@import) assentarem antes do screenshot
_ESPERA_FONTE_MS = 250
_TIMEOUT_CARREGAMENTO_MS = 15_000


class MotorTemplate:
    def __init__(self, *, largura: int = 1080, altura: int = 1350, escala: int = 2):
        self.largura = int(largura)
        self.altura = int(altura)
        self.escala = int(escala)

    def renderizar_varios(
        self, htmls: list[str], nomes: list[str | None] | None = None
    ) -> list[str]:
        """Renderiza N HTMLs reaproveitando um único navegador. Retorna os
        caminhos locais dos PNGs, na mesma ordem. `nomes[i]` é o nome do
        arquivo (sem extensão) da peça i — convenção `{post_id}_slide{ordem}`
        de agent.md; None cai num hash."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # dependência ainda não instalada
            raise ErroConfiguracaoAusente(
                "Playwright não está instalado — o motor de template de imagem "
                "precisa dele. Rode: pip install -r requirements.txt && "
                "playwright install chromium"
            ) from exc

        caminhos: list[str] = []
        with sync_playwright() as pw:
            try:
                navegador = pw.chromium.launch(
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--font-render-hinting=none"]
                )
            except Exception as exc:  # binário do Chromium ausente
                if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
                    raise ErroConfiguracaoAusente(
                        "Chromium do Playwright não instalado — rode: "
                        "playwright install chromium"
                    ) from exc
                raise
            try:
                for i, html in enumerate(htmls):
                    pagina = navegador.new_page(
                        viewport={"width": self.largura, "height": self.altura},
                        device_scale_factor=self.escala,
                    )
                    try:
                        pagina.set_content(
                            html, wait_until="networkidle", timeout=_TIMEOUT_CARREGAMENTO_MS
                        )
                        pagina.wait_for_timeout(_ESPERA_FONTE_MS)
                        png = pagina.screenshot(type="png")
                    finally:
                        pagina.close()
                    nome = nomes[i] if nomes and i < len(nomes) else None
                    caminhos.append(salvar_peca_localmente(png, "png", nome=nome))
            finally:
                navegador.close()
        return caminhos

    def renderizar(self, html: str, nome: str | None = None) -> str:
        return self.renderizar_varios([html], [nome])[0]


def motor_de(identidade_visual: dict[str, Any] | None) -> MotorTemplate:
    """Constrói o MotorTemplate a partir dos tokens de perfil-marca.md."""
    dim = ((identidade_visual or {}).get("dimensoes")) or {}
    return MotorTemplate(
        largura=dim.get("largura", 1080),
        altura=dim.get("altura", 1350),
    )
