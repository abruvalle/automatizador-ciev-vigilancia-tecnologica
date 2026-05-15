"""
Web Scraper para extraer contenido de páginas web.

Extrae título, texto principal y metadatos de las URLs de las propuestas.
Soporta páginas estáticas (requests+BeautifulSoup) y opcionalmente
páginas dinámicas con JavaScript (Playwright).
"""

from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ..models.proposal import Proposal


def scrape_proposals(
    proposals: list[Proposal],
    config: dict,
) -> list[Proposal]:
    """
    Extrae el contenido web de cada propuesta.

    Para cada propuesta, hace scraping de su enlace y llena los campos:
    - titulo (si está vacío)
    - contenido_extraido (texto completo de la página)
    - pais_institucion (si se puede detectar)

    Args:
        proposals: Lista de propuestas con enlaces.
        config: Configuración de scraping.

    Returns:
        Las mismas propuestas con el contenido extraído.
    """
    scraping_config = config.get("scraping", {})
    timeout = scraping_config.get("timeout", 15)
    user_agent = scraping_config.get("user_agent", "Mozilla/5.0")
    delay = scraping_config.get("delay_between_requests", 1.5)
    max_retries = scraping_config.get("max_retries", 2)
    use_playwright = scraping_config.get("use_playwright", False)

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.5",
    }

    total = len(proposals)
    for i, proposal in enumerate(proposals):
        print(f"  🔍 [{i+1}/{total}] Extrayendo contenido de: {_truncate_url(proposal.enlace)}")

        try:
            # Determinar si necesita Playwright (páginas dinámicas)
            needs_playwright = use_playwright and _needs_dynamic_rendering(proposal.enlace)

            if needs_playwright:
                _scrape_with_playwright(proposal, timeout)
            else:
                _scrape_with_requests(proposal, headers, timeout, max_retries)

        except Exception as e:
            error_msg = f"Error extrayendo contenido: {str(e)}"
            proposal.errores.append(error_msg)
            print(f"    ⚠️  {error_msg}")

        # Delay entre requests
        if i < total - 1:
            time.sleep(delay)

    scraped = sum(1 for p in proposals if p.contenido_extraido)
    print(f"\n✅ Contenido extraído de {scraped}/{total} propuestas")
    return proposals


def _scrape_with_requests(
    proposal: Proposal,
    headers: dict,
    timeout: int,
    max_retries: int,
) -> None:
    """Extrae contenido usando requests + BeautifulSoup (páginas estáticas)."""
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                proposal.enlace,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
            proposal.link_status_code = response.status_code

            # Parsear HTML
            soup = BeautifulSoup(response.text, "lxml")

            # Extraer título
            if not proposal.titulo:
                proposal.titulo = _extract_title(soup)

            # Extraer contenido principal
            proposal.contenido_extraido = _extract_main_content(soup)

            # Intentar extraer país/institución
            if not proposal.pais_institucion:
                proposal.pais_institucion = _extract_institution(soup, proposal.enlace)

            return

        except requests.RequestException as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(1)

    if last_error:
        raise last_error


def _scrape_with_playwright(
    proposal: Proposal,
    timeout: int,
) -> None:
    """Extrae contenido usando Playwright (páginas con JavaScript)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ImportError(
            "Para scraping dinámico necesitás Playwright:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(proposal.enlace, timeout=timeout * 1000)
            page.wait_for_load_state("networkidle", timeout=timeout * 1000)

            # Extraer contenido
            content = page.content()
            soup = BeautifulSoup(content, "lxml")

            if not proposal.titulo:
                proposal.titulo = _extract_title(soup)

            proposal.contenido_extraido = _extract_main_content(soup)

            if not proposal.pais_institucion:
                proposal.pais_institucion = _extract_institution(soup, proposal.enlace)

            proposal.link_status_code = 200

        finally:
            browser.close()


def _extract_title(soup: BeautifulSoup) -> str:
    """Extrae el título de la página."""
    # Intentar con og:title primero
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()

    # Luego <title>
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    # Luego <h1>
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)

    return ""


def _extract_main_content(soup: BeautifulSoup) -> str:
    """
    Extrae el contenido textual principal de la página.

    Elimina scripts, estilos, navegación y footer.
    Prioriza el contenido del <main>, <article> o el body.
    """
    # Remover elementos no deseados
    for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                              "aside", "iframe", "noscript"]):
        tag.decompose()

    # Buscar contenido principal en orden de prioridad
    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"(content|main|post|entry|article)", re.I))
        or soup.find("div", id=re.compile(r"(content|main|post|entry|article)", re.I))
        or soup.body
    )

    if not main_content:
        return ""

    # Extraer texto limpio
    text = main_content.get_text(separator="\n", strip=True)

    # Limpiar líneas vacías excesivas
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    text = "\n".join(lines)

    # Limitar longitud (para no saturar el LLM después)
    max_chars = 15000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[... contenido truncado ...]"

    return text


def _extract_institution(soup: BeautifulSoup, url: str) -> str:
    """
    Intenta extraer el país/institución de la página.

    Busca en metadatos, dominio y contenido.
    """
    # Intentar con og:site_name
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        return og_site["content"].strip()

    # Intentar extraer del dominio
    domain = urlparse(url).netloc.lower()
    # Remover www. y extensiones comunes
    domain_clean = domain.replace("www.", "").split(".")[0]

    # Mapeo de dominios conocidos a instituciones
    domain_map = {
        "conicet": "Argentina / CONICET",
        "anpcyt": "Argentina / ANPCyT",
        "argentina": "Argentina",
        "uner": "Argentina / UNER",
        "coursera": "Internacional / Coursera",
        "edx": "Internacional / edX",
        "who": "Internacional / OMS",
        "paho": "Internacional / OPS",
        "unesco": "Internacional / UNESCO",
    }

    for key, value in domain_map.items():
        if key in domain:
            return value

    # Detectar país por TLD
    tld_country = {
        ".ar": "Argentina",
        ".br": "Brasil",
        ".cl": "Chile",
        ".mx": "México",
        ".co": "Colombia",
        ".uy": "Uruguay",
        ".py": "Paraguay",
        ".pe": "Perú",
        ".es": "España",
        ".edu": "Internacional",
    }
    for tld, country in tld_country.items():
        if domain.endswith(tld):
            return country

    return ""


def _needs_dynamic_rendering(url: str) -> bool:
    """Determina si una URL probablemente necesita renderizado dinámico."""
    dynamic_domains = [
        "linkedin.com",
        "instagram.com",
        "facebook.com",
        "twitter.com",
        "x.com",
    ]
    domain = urlparse(url).netloc.lower()
    return any(d in domain for d in dynamic_domains)


def _truncate_url(url: str, max_len: int = 60) -> str:
    """Trunca una URL para mostrarla en logs."""
    if len(url) <= max_len:
        return url
    return url[:max_len - 3] + "..."
