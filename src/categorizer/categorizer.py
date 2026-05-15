"""
Categorizador de propuestas.

Clasifica propuestas en las categorías del boletín usando:
1. La categoría ya asignada en la planilla (si existe)
2. Clasificación automática con LLM basada en el contenido
"""

from __future__ import annotations

import os
from typing import Optional

from ..models.proposal import Categoria, EstadoValidacion, Proposal


# Palabras clave para clasificación rápida (sin LLM)
_KEYWORD_MAP: dict[Categoria, list[str]] = {
    Categoria.BECAS: [
        "beca", "scholarship", "fellowship", "estipendio", "grant",
        "becario", "becaria",
    ],
    Categoria.CONVOCATORIAS: [
        "convocatoria", "call for", "llamado", "concurso",
    ],
    Categoria.CURSOS: [
        "curso", "course", "capacitación", "formación", "training",
        "diplomatura", "especialización", "taller", "workshop",
    ],
    Categoria.EVENTOS: [
        "congreso", "congress", "conferencia", "conference", "simposio",
        "symposium", "jornada", "encuentro", "foro", "forum",
    ],
    Categoria.FINANCIAMIENTO: [
        "financiamiento", "funding", "subsidio", "subvención",
        "capital semilla", "seed", "inversión", "investment",
    ],
    Categoria.NORMAS: [
        "norma", "regulación", "regulation", "estándar", "standard",
        "certificación", "iso", "iram",
    ],
    Categoria.NOTICIAS: [
        "noticia", "news", "publicación", "artículo", "article",
        "investigación", "research", "descubrimiento",
    ],
    Categoria.PATENTES: [
        "patente", "patent", "propiedad intelectual", "intellectual property",
        "invención", "invention",
    ],
    Categoria.WEBINARS: [
        "webinar", "webinario", "seminario web", "online seminar",
        "charla virtual", "live", "streaming",
    ],
}

_CATEGORIZE_PROMPT = (
    "Clasificá la siguiente propuesta en exactamente UNA de estas categorías: "
    "becas, convocatorias, cursos, eventos, financiamiento, normas, noticias, patentes, webinars.\n\n"
    "Título: {titulo}\n"
    "Resumen: {resumen}\n\n"
    "Respondé SOLAMENTE con el nombre de la categoría en minúsculas, sin explicación."
)


def categorize_proposals(proposals: list[Proposal], config: dict) -> list[Proposal]:
    """
    Categoriza todas las propuestas que no tengan categoría asignada.

    Estrategia:
    1. Si ya tiene categoría de la planilla → la mantiene
    2. Intenta clasificar por palabras clave
    3. Si falla, usa el LLM
    """
    to_categorize = [
        p for p in proposals
        if p.categoria is None and p.estado != EstadoValidacion.LINK_ROTO
    ]

    already = sum(1 for p in proposals if p.categoria is not None)
    total = len(to_categorize)

    print(f"\n🏷️  Categorizando propuestas ({already} ya tienen categoría, {total} pendientes)...")

    llm_client = None
    llm_needed = []

    for prop in to_categorize:
        # Intentar con palabras clave
        cat = _categorize_by_keywords(prop)
        if cat:
            prop.categoria = cat
            print(f"  🏷️  {(prop.titulo or prop.enlace)[:40]} → {cat.value} (keywords)")
        else:
            llm_needed.append(prop)

    # Usar LLM para las que no se pudieron clasificar por keywords
    if llm_needed:
        llm_client = _get_llm_for_categorization(config)

    if llm_client and llm_needed:
        print(f"  🤖 Clasificando {len(llm_needed)} propuestas con IA...")
        for prop in llm_needed:
            cat = _categorize_with_llm(llm_client, prop, config)
            if cat:
                prop.categoria = cat
                print(f"  🏷️  {(prop.titulo or prop.enlace)[:40]} → {cat.value} (IA)")
            else:
                prop.categoria = Categoria.NOTICIAS  # Default
                print(f"  🏷️  {(prop.titulo or prop.enlace)[:40]} → noticias (default)")

    categorized = sum(1 for p in proposals if p.categoria is not None)
    print(f"\n✅ Categorización completa: {categorized}/{len(proposals)}")
    return proposals


def _categorize_by_keywords(proposal: Proposal) -> Optional[Categoria]:
    """Clasifica por palabras clave en título, resumen y contenido."""
    text = " ".join([
        (proposal.titulo or "").lower(),
        (proposal.resumen or "").lower(),
        (proposal.contenido_extraido or "")[:2000].lower(),
    ])

    scores: dict[Categoria, int] = {}
    for cat, keywords in _KEYWORD_MAP.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[cat] = score

    if scores:
        return max(scores, key=scores.get)
    return None


def _get_llm_for_categorization(config: dict):
    """Obtiene un cliente LLM para categorización."""
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "gemini")
    api_key = llm_config.get("api_key", "")

    if provider == "gemini":
        api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            return genai.GenerativeModel(llm_config.get("model", "gemini-2.0-flash"))
        except ImportError:
            return None

    elif provider in ("openai", "ollama"):
        api_key = api_key or os.environ.get("OPENAI_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
        if provider == "ollama":
            api_key = "ollama"
        if not api_key:
            return None
        try:
            from openai import OpenAI
            if provider == "ollama":
                return OpenAI(
                    base_url=llm_config.get("base_url", "http://localhost:11434/v1"),
                    api_key="ollama",
                )
            base_url = llm_config.get("base_url")
            return OpenAI(api_key=api_key, base_url=base_url)
        except ImportError:
            return None

    return None


def _categorize_with_llm(client, proposal: Proposal, config: dict) -> Optional[Categoria]:
    """Clasifica una propuesta usando el LLM."""
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "gemini")

    prompt = _CATEGORIZE_PROMPT.format(
        titulo=proposal.titulo or "Sin título",
        resumen=proposal.resumen or proposal.contenido_extraido[:500],
    )

    try:
        if provider == "gemini":
            resp = client.generate_content(prompt, generation_config={"temperature": 0.0})
            text = (resp.text or "").strip().lower()
        elif provider in ("openai", "ollama"):
            model = llm_config.get("model", "gpt-4o-mini" if provider == "openai" else "llama3")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            text = (resp.choices[0].message.content or "").strip().lower()
        else:
            return None

        try:
            return Categoria(text)
        except ValueError:
            # Buscar si la respuesta contiene alguna categoría
            for cat in Categoria:
                if cat.value in text:
                    return cat
            return None

    except Exception:
        return None
