"""
Validador y extractor de fechas.

Extrae fechas del contenido de las propuestas usando múltiples estrategias:
1. Regex para patrones comunes en español/inglés/portugués
2. dateparser para formatos variados
3. LLM como fallback

Luego valida que las fechas sean >= a la fecha del boletín.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from typing import Optional

import dateparser

from ..models.proposal import EstadoValidacion, Proposal, TipoFecha


# Patrones de fechas comunes en español
_DATE_PATTERNS_ES = [
    # "15 de mayo de 2026", "15 de Mayo de 2026"
    r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})",
    # "15/05/2026", "15-05-2026"
    r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})",
    # "2026-05-15" (ISO)
    r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})",
    # "Mayo 15, 2026", "May 15, 2026"
    r"(\w+)\s+(\d{1,2}),?\s+(\d{4})",
    # "15/05/26"
    r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})\b",
]

# Palabras clave que indican el tipo de fecha
_TIPO_FECHA_KEYWORDS = {
    TipoFecha.INSCRIPCION: [
        "inscripción", "inscripcion", "inscribirse", "registro", "registrarse",
        "postulación", "postulacion", "aplicar", "apply", "application",
        "registration", "deadline", "plazo", "cierre de inscripción",
    ],
    TipoFecha.EVENTO: [
        "evento", "event", "se realizará", "tendrá lugar", "fecha del evento",
    ],
    TipoFecha.WEBINAR: [
        "webinar", "webinario", "seminario web", "online event",
        "charla virtual", "conferencia virtual",
    ],
    TipoFecha.SIMPOSIO: [
        "simposio", "symposium", "congreso", "congress", "conferencia",
        "conference", "jornada",
    ],
    TipoFecha.ENTREGA_RESUMENES: [
        "resumen", "resúmenes", "abstract", "abstracts", "envío de resúmenes",
        "submission of abstracts",
    ],
    TipoFecha.ENTREGA_PROYECTOS: [
        "proyecto", "propuesta", "project", "proposal", "entrega de proyecto",
        "submission",
    ],
    TipoFecha.INICIO: [
        "inicio", "comienza", "start", "begins", "apertura", "abre",
    ],
    TipoFecha.CIERRE: [
        "cierre", "finaliza", "vence", "vencimiento", "close", "closes",
        "ends", "until", "hasta",
    ],
}


def extract_and_validate_dates(
    proposals: list[Proposal],
    fecha_boletin: date,
    config: dict,
) -> list[Proposal]:
    """
    Extrae fechas del contenido y valida que sean >= fecha del boletín.

    Para cada propuesta:
    1. Extrae todas las fechas encontradas en el contenido
    2. Clasifica el tipo de fecha (inscripción, evento, etc.)
    3. Selecciona la fecha más relevante
    4. Valida que sea >= fecha_boletin

    Args:
        proposals: Lista de propuestas con contenido extraído.
        fecha_boletin: Fecha del miércoles de envío del boletín.
        config: Configuración.

    Returns:
        Propuestas con fechas extraídas y estado de validación actualizado.
    """
    validacion_config = config.get("validacion", {})
    idiomas = validacion_config.get("idiomas_fechas", ["es", "en", "pt"])

    total = len(proposals)
    validas = 0
    sin_fecha = 0
    pasadas = 0

    print(f"\n📅 Extrayendo y validando fechas (fecha del boletín: {fecha_boletin.strftime('%d/%m/%Y')})...")

    llm_client = _get_llm_client(config.get("llm", {}))

    for i, proposal in enumerate(proposals):
        # Saltar propuestas ya marcadas como inválidas
        if proposal.estado == EstadoValidacion.LINK_ROTO:
            continue

        print(f"  [{i+1}/{total}] {_truncate(proposal.titulo or proposal.enlace, 50)}", end=" ")

        # Extraer fechas con regex primero
        fechas = _extract_dates(proposal.contenido_extraido, idiomas)
        proposal.fechas_detectadas = fechas

        mejor_fecha = _select_best_date(fechas, fecha_boletin)

        # Si encontramos una fecha futura válida con regex, pasamos rápido
        if mejor_fecha and mejor_fecha["date"] >= fecha_boletin:
            proposal.fecha = mejor_fecha["date"]
            proposal.tipo_fecha = mejor_fecha["tipo"]
            proposal.estado = EstadoValidacion.VALIDA
            print(f"✅ {proposal.fecha_formateada()}")
            validas += 1
            continue

        # Búsqueda a profundidad con IA (si no hay fecha regex o si es pasada)
        llm_data = None
        if llm_client:
            llm_data = _extract_date_with_llm(llm_client, proposal.contenido_extraido, config.get("llm", {}))
            
        if llm_data:
            if llm_data.get("es_ventanilla_abierta"):
                proposal.estado = EstadoValidacion.VALIDA
                proposal.tipo_fecha = TipoFecha.OTRO
                print("✅ Ventanilla abierta (IA)")
                validas += 1
            elif llm_data.get("tiene_fecha_limite") and llm_data.get("fecha_limite"):
                try:
                    fecha_llm = date.fromisoformat(llm_data["fecha_limite"])
                    proposal.fecha = fecha_llm
                    proposal.tipo_fecha = TipoFecha.CIERRE
                    if fecha_llm >= fecha_boletin:
                        proposal.estado = EstadoValidacion.VALIDA
                        print(f"✅ Cierre: {fecha_llm.strftime('%d/%m/%Y')} (IA)")
                        validas += 1
                    else:
                        proposal.estado = EstadoValidacion.FECHA_PASADA
                        print(f"❌ Fecha pasada: {fecha_llm.strftime('%d/%m/%Y')} (IA)")
                        proposal.errores.append("Fecha pasada detectada por IA")
                        pasadas += 1
                except ValueError:
                    proposal.estado = EstadoValidacion.FECHA_PASADA
                    print("❌ Fecha inválida de IA, marcando pasada preventivamente")
                    proposal.errores.append("Error al parsear fecha de IA")
                    pasadas += 1
            else:
                proposal.estado = EstadoValidacion.FECHA_PASADA
                print("❌ Sin fecha límite detectada por IA, descartada preventivamente")
                proposal.errores.append("La IA no encontró fecha límite ni ventanilla abierta")
                pasadas += 1
        else:
            # Sin LLM o falló el LLM, nos basamos en regex
            if mejor_fecha:
                proposal.fecha = mejor_fecha["date"]
                proposal.tipo_fecha = mejor_fecha["tipo"]
                proposal.estado = EstadoValidacion.FECHA_PASADA
                print(f"❌ Fecha pasada: {proposal.fecha_formateada()} (Regex)")
                proposal.errores.append("Fecha pasada (Regex)")
                pasadas += 1
            else:
                proposal.estado = EstadoValidacion.FECHA_PASADA
                print("❌ No se detectaron fechas, descartada preventivamente")
                proposal.errores.append("Sin fechas detectadas (rechazo estricto)")
                pasadas += 1

    print(f"\n📅 Resultado: {validas} válidas, {pasadas} con fecha pasada, {sin_fecha} sin fecha")
    return proposals


def _extract_dates(text: str, idiomas: list[str]) -> list[dict]:
    """
    Extrae todas las fechas encontradas en el texto.

    Usa regex para encontrar patrones y dateparser para parsearlos.

    Returns:
        Lista de dicts con: {"text": str, "date": date, "tipo": TipoFecha, "context": str}
    """
    if not text:
        return []

    fechas = []
    seen_dates = set()

    # Buscar con regex
    for pattern in _DATE_PATTERNS_ES:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            date_text = match.group(0)

            # Obtener contexto (50 chars antes y después)
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            context = text[start:end].replace("\n", " ").strip()

            # Intentar parsear con dateparser
            parsed = dateparser.parse(
                date_text,
                languages=idiomas,
                settings={
                    "PREFER_DAY_OF_MONTH": "first",
                    "PREFER_DATES_FROM": "future",
                    "RETURN_AS_TIMEZONE_AWARE": False,
                },
            )

            if parsed:
                d = parsed.date()
                # Evitar duplicados
                if d not in seen_dates:
                    seen_dates.add(d)
                    tipo = _detect_date_type(context)
                    fechas.append({
                        "text": date_text,
                        "date": d,
                        "tipo": tipo,
                        "context": context,
                    })

    # Ordenar por fecha
    fechas.sort(key=lambda f: f["date"])

    return fechas


def _detect_date_type(context: str) -> TipoFecha:
    """
    Detecta el tipo de fecha basándose en el contexto donde aparece.

    Busca palabras clave en el texto circundante.
    """
    context_lower = context.lower()

    # Buscar en orden de especificidad (más específico primero)
    priority_order = [
        TipoFecha.ENTREGA_RESUMENES,
        TipoFecha.ENTREGA_PROYECTOS,
        TipoFecha.WEBINAR,
        TipoFecha.SIMPOSIO,
        TipoFecha.INSCRIPCION,
        TipoFecha.CIERRE,
        TipoFecha.INICIO,
        TipoFecha.EVENTO,
    ]

    for tipo in priority_order:
        keywords = _TIPO_FECHA_KEYWORDS.get(tipo, [])
        for keyword in keywords:
            if keyword in context_lower:
                return tipo

    return TipoFecha.OTRO


def _select_best_date(
    fechas: list[dict],
    fecha_boletin: date,
) -> Optional[dict]:
    """
    Selecciona la fecha más relevante de la lista.

    Prioridad:
    1. Fechas de inscripción/cierre que sean >= fecha_boletin
    2. Cualquier fecha futura más cercana al boletín
    3. Fecha más lejana en el futuro
    """
    if not fechas:
        return None

    # Separar futuras y pasadas
    futuras = [f for f in fechas if f["date"] >= fecha_boletin]
    pasadas = [f for f in fechas if f["date"] < fecha_boletin]

    if futuras:
        # Priorizar fechas de inscripción/cierre
        tipos_prioritarios = {TipoFecha.INSCRIPCION, TipoFecha.CIERRE, TipoFecha.ENTREGA_RESUMENES}
        prioritarias = [f for f in futuras if f["tipo"] in tipos_prioritarios]

        if prioritarias:
            # Tomar la más cercana
            return min(prioritarias, key=lambda f: f["date"])

        # Si no hay prioritarias, tomar la más cercana al boletín
        return min(futuras, key=lambda f: f["date"])

    # Si todas son pasadas, devolver la más reciente
    if pasadas:
        return max(pasadas, key=lambda f: f["date"])

    return None


def _truncate(text: str, max_len: int) -> str:
    """Trunca texto para display."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


# --- Funciones de IA para fechas ---

_SYSTEM_PROMPT_DATES = (
    "Sos un asistente experto en lectura de bases y condiciones de convocatorias. "
    "Tu tarea es encontrar la fecha límite exacta (cierre, deadline, vencimiento). "
    "Respondé ÚNICAMENTE con un objeto JSON válido con esta estructura:\n"
    "{\n"
    '  "tiene_fecha_limite": true/false,\n'
    '  "fecha_limite": "YYYY-MM-DD" o null,\n'
    '  "es_ventanilla_abierta": true/false\n'
    "}"
)

_EXTRACT_DATE_TEMPLATE = (
    "Buscá a profundidad la fecha límite en este texto. Si es ventanilla abierta (sin límite), indicalo.\n"
    "Contenido:\n---\n{contenido}\n---"
)

def _get_llm_client(cfg: dict):
    provider = cfg.get("provider", "gemini")
    api_key = cfg.get("api_key", "")

    if provider == "gemini":
        api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key: return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            return genai.GenerativeModel(cfg.get("model", "gemini-2.0-flash"))
        except ImportError:
            return None
    elif provider == "openai":
        api_key = api_key or os.environ.get("OPENAI_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
        if not api_key: return None
        try:
            from openai import OpenAI
            return OpenAI(api_key=api_key, base_url=cfg.get("base_url"))
        except ImportError:
            return None
    elif provider == "ollama":
        try:
            from openai import OpenAI
            return OpenAI(base_url=cfg.get("base_url", "http://localhost:11434/v1"), api_key="ollama")
        except ImportError:
            return None
    return None

def _extract_date_with_llm(client, text: str, cfg: dict) -> Optional[dict]:
    if not text:
        return None
        
    prompt = _EXTRACT_DATE_TEMPLATE.format(contenido=text[:8000])
    provider = cfg.get("provider", "gemini")
    
    try:
        if provider == "gemini":
            resp = client.generate_content(
                f"{_SYSTEM_PROMPT_DATES}\n\n{prompt}",
                generation_config={"temperature": 0.0},
            )
            resp_text = resp.text
        elif provider in ("openai", "ollama"):
            model = cfg.get("model", "gpt-4o-mini" if provider == "openai" else "llama3")
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT_DATES},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )
            resp_text = resp.choices[0].message.content
        else:
            return None
            
        if not resp_text:
            return None
            
        resp_text = resp_text.strip()
        if resp_text.startswith("```json"): resp_text = resp_text[7:]
        if resp_text.startswith("```"): resp_text = resp_text[3:]
        if resp_text.endswith("```"): resp_text = resp_text[:-3]
        
        return json.loads(resp_text.strip())
    except Exception as e:
        print(f"    ⚠️ Error extrayendo fecha con IA: {e}")
        return None

