"""
Validador de links.

Verifica que los enlaces de las propuestas funcionen correctamente
haciendo requests HTTP y comprobando los status codes.
"""

from __future__ import annotations

import time

import requests

from ..models.proposal import EstadoValidacion, Proposal


def validate_links(
    proposals: list[Proposal],
    config: dict,
) -> list[Proposal]:
    """
    Valida que los enlaces de todas las propuestas funcionen.

    Hace un HEAD request (o GET si HEAD falla) a cada URL y verifica
    que el status code sea 200 (o una redirección exitosa).

    Args:
        proposals: Lista de propuestas a validar.
        config: Configuración de validación.

    Returns:
        Las mismas propuestas con link_status_code y estado actualizados.
    """
    validacion_config = config.get("validacion", {})
    timeout = validacion_config.get("link_timeout", 10)
    scraping_config = config.get("scraping", {})
    user_agent = scraping_config.get("user_agent", "Mozilla/5.0")
    delay = scraping_config.get("delay_between_requests", 1.5)

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml",
    }

    total = len(proposals)
    validos = 0
    rotos = 0

    print(f"\n🔗 Validando {total} enlaces...")

    for i, proposal in enumerate(proposals):
        print(f"  [{i+1}/{total}] {_truncate(proposal.enlace, 55)}", end=" ")

        status = _check_url(proposal.enlace, headers, timeout)
        proposal.link_status_code = status

        if status and 200 <= status < 400:
            print(f"✅ ({status})")
            validos += 1
        else:
            status_str = str(status) if status else "sin respuesta"
            print(f"❌ ({status_str})")
            proposal.estado = EstadoValidacion.LINK_ROTO
            proposal.errores.append(f"Link roto o inaccesible (status: {status_str})")
            rotos += 1

        if i < total - 1:
            time.sleep(delay)

    print(f"\n✅ Validación de links completa: {validos} válidos, {rotos} rotos")
    return proposals


def _check_url(url: str, headers: dict, timeout: int) -> int | None:
    """
    Verifica la accesibilidad de una URL.

    Intenta primero con HEAD (más rápido), luego con GET si HEAD falla.

    Returns:
        Status code HTTP, o None si no se pudo conectar.
    """
    # Intentar con HEAD
    try:
        response = requests.head(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )
        # Algunos servidores bloquean HEAD, verificar
        if response.status_code < 400:
            return response.status_code
    except requests.RequestException:
        pass

    # Fallback a GET
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            stream=True,  # No descargar todo el body
        )
        return response.status_code
    except requests.RequestException:
        return None


def _truncate(text: str, max_len: int) -> str:
    """Trunca texto para display."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
