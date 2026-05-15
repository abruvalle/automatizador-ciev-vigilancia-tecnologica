"""
Validador geográfico basado en IA.

Verifica si la oportunidad es accesible para residentes de Argentina.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from ..models.proposal import EstadoValidacion, Proposal


_GEO_PROMPT = (
    "Sos un experto analista de vigilancia tecnológica. Tu tarea es determinar si la siguiente oportunidad "
    "(beca, evento, convocatoria, curso, etc.) admite la participación de residentes de Argentina.\n\n"
    "REGLA ESTRICTA:\n"
    "- Si el texto indica explícitamente que está dirigido a Argentina, Latinoamérica, o que es Internacional, "
    "o si simplemente no restringe la nacionalidad/residencia para participar, responde 'APTO'.\n"
    "- Si el texto restringe la participación EXCLUSIVAMENTE a residentes de países específicos que NO incluyen a Argentina "
    "(por ejemplo, 'solo para residentes en México', 'dirigido a ciudadanos españoles', 'emprendedores de Colombia', etc.), "
    "responde 'NO_APTO'.\n\n"
    "Contenido a analizar:\n---\n{contenido}\n---\n\n"
    "Responde ÚNICAMENTE con 'APTO' o 'NO_APTO'. No incluyas ninguna explicación adicional ni puntuación."
)


def validate_geography(proposals: list[Proposal], config: dict) -> list[Proposal]:
    """Valida que las propuestas sean aptas para residentes de Argentina usando IA."""
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "gemini")

    # Solo validamos las que ya pasaron la validación de link y fecha
    to_validate = [
        p for p in proposals
        if p.estado == EstadoValidacion.VALIDA and p.contenido_extraido
    ]

    total = len(to_validate)
    if total == 0:
        return proposals

    client = _get_llm_client(llm_config)
    if client is None:
        print("❌ No se pudo inicializar el cliente de IA para validación geográfica.")
        return proposals

    print(f"\n🌎 Validando geografía para {total} propuestas válidas (proveedor: {provider})...")

    validas_geo = 0
    excluidas = 0

    for i, prop in enumerate(to_validate):
        print(f"  [{i+1}/{total}] {(prop.titulo or prop.enlace)[:50]}", end=" ")
        try:
            prompt = _GEO_PROMPT.format(contenido=prop.contenido_extraido[:8000])
            resp = _call_llm(client, llm_config, prompt)
            
            if resp and "NO_APTO" in resp.upper():
                prop.estado = EstadoValidacion.EXCLUIDA_GEOGRAFIA
                prop.errores.append("Excluida por no ser apta para residentes de Argentina")
                print("❌ Excluida (No apta para Argentina)")
                excluidas += 1
            else:
                print("✅ Apta")
                validas_geo += 1
                
        except Exception as e:
            prop.errores.append(f"Error geo-validación: {e}")
            print(f"⚠️  Error: {e}")

        if i < total - 1:
            time.sleep(0.5)

    print(f"\n🌎 Resultado Geográfico: {validas_geo} aptas, {excluidas} excluidas")
    return proposals


def _get_llm_client(cfg: dict):
    """Inicializa el cliente LLM según el proveedor."""
    provider = cfg.get("provider", "gemini")
    api_key = cfg.get("api_key", "")

    if provider == "gemini":
        api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            return genai.GenerativeModel(cfg.get("model", "gemini-2.0-flash"))
        except ImportError:
            return None

    elif provider == "openai":
        api_key = api_key or os.environ.get("OPENAI_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return None
        try:
            from openai import OpenAI
            base_url = cfg.get("base_url")
            return OpenAI(api_key=api_key, base_url=base_url)
        except ImportError:
            return None

    elif provider == "ollama":
        try:
            from openai import OpenAI
            base_url = cfg.get("base_url", "http://localhost:11434/v1")
            return OpenAI(base_url=base_url, api_key="ollama")
        except ImportError:
            return None

    return None


def _call_llm(client, cfg: dict, prompt: str) -> Optional[str]:
    """Llama al LLM y retorna la respuesta."""
    provider = cfg.get("provider", "gemini")
    temp = 0.0  # Temperatura 0 para mayor determinismo en la validación
    model = cfg.get("model", "")

    try:
        if provider == "gemini":
            resp = client.generate_content(
                prompt,
                generation_config={"temperature": temp},
            )
            return resp.text if resp.text else None
        elif provider in ("openai", "ollama"):
            resp = client.chat.completions.create(
                model=model or ("gpt-4o-mini" if provider == "openai" else "llama3"),
                messages=[
                    {"role": "user", "content": prompt},
                ],
                temperature=temp,
            )
            return resp.choices[0].message.content
    except Exception:
        return None
