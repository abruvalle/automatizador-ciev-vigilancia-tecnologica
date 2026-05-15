"""
Generador de resúmenes con IA.

Genera resúmenes de 5-8 líneas basados exclusivamente en el contenido
extraído de cada propuesta. Soporta: Google Gemini, OpenAI, Ollama.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from ..models.proposal import EstadoValidacion, Proposal


_SYSTEM_PROMPT = (
    "Sos una asistente de vigilancia tecnológica del CIEV (Facultad de Ingeniería, UNER). "
    "Tu tarea es generar resúmenes concisos e identificar metadatos clave sobre propuestas "
    "(becas, convocatorias, cursos, eventos, etc.) para un boletín. "
    "Reglas: 1) Usá SOLO la información proporcionada, NO inventes datos. "
    "2) El resumen debe tener entre 5 y 8 líneas. "
    "3) En emprendedurismo, priorizá mencionar 'aportes no reembolsables' y 'TRL'. "
    "4) Respondé ÚNICAMENTE con un objeto JSON válido con la siguiente estructura:\n"
    "{\n"
    '  "resumen": "tu resumen de 5 a 8 líneas",\n'
    '  "modalidad": "Virtual, Presencial, Híbrido, Ventanilla abierta, o vacío",\n'
    '  "publico_objetivo": "A quién va dirigido (ej. Startups, Investigadores, etc.)",\n'
    '  "trl": "Nivel TRL si se menciona, sino vacío"\n'
    "}"
)

_SUMMARIZE_TEMPLATE = (
    "Analizá la propuesta y generá el JSON solicitado.\n\n"
    "Título: {titulo}\nURL: {enlace}\n\n"
    "Contenido:\n---\n{contenido}\n---\n\n"
)

_DETECT_SUMMARY_TEMPLATE = (
    "Analizá el siguiente contenido y determiná si ya contiene un resumen claro de la propuesta. "
    "Si es así, extraelo y también extraé la modalidad, público objetivo y TRL si están disponibles. "
    "Respondé ÚNICAMENTE con un objeto JSON válido con la estructura solicitada.\n\n"
    "Contenido:\n---\n{contenido}\n---"
)


def generate_summaries(proposals: list[Proposal], config: dict) -> list[Proposal]:
    """Genera resúmenes para propuestas válidas usando IA."""
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "gemini")
    min_l = llm_config.get("resumen_min_lineas", 5)
    max_l = llm_config.get("resumen_max_lineas", 8)

    client = _get_llm_client(llm_config)
    if client is None:
        print("❌ No se pudo inicializar el cliente de IA.")
        return proposals

    to_summarize = [
        p for p in proposals
        if p.estado == EstadoValidacion.VALIDA and p.contenido_extraido and not p.resumen
    ]

    total = len(to_summarize)
    print(f"\n🤖 Generando resúmenes para {total} propuestas (proveedor: {provider})...")

    for i, prop in enumerate(to_summarize):
        print(f"  [{i+1}/{total}] {(prop.titulo or prop.enlace)[:50]}")
        try:
            # Paso 1: buscar resumen existente y extraer metadatos
            existing = _detect_existing(client, prop, llm_config)
            if existing and existing.get("resumen"):
                prop.resumen = _trim(existing.get("resumen", ""), min_l, max_l)
                prop.resumen_fuente = "original"
                prop.modalidad = existing.get("modalidad", "")
                prop.publico_objetivo = existing.get("publico_objetivo", "")
                prop.trl = existing.get("trl", "")
                print(f"    📋 Resumen existente ({_count(prop.resumen)} líneas)")
            else:
                # Paso 2: generar con IA
                gen = _generate(client, prop, llm_config)
                if gen and gen.get("resumen"):
                    prop.resumen = _trim(gen.get("resumen", ""), min_l, max_l)
                    prop.resumen_fuente = "generado_ia"
                    prop.modalidad = gen.get("modalidad", "")
                    prop.publico_objetivo = gen.get("publico_objetivo", "")
                    prop.trl = gen.get("trl", "")
                    print(f"    ✨ Resumen generado ({_count(prop.resumen)} líneas)")
                else:
                    prop.errores.append("No se pudo generar el resumen")
                    print("    ⚠️  No se pudo generar")
        except Exception as e:
            prop.errores.append(f"Error: {e}")
            print(f"    ❌ {e}")

        if i < total - 1:
            time.sleep(0.5)

    done = sum(1 for p in to_summarize if p.resumen)
    print(f"\n✅ Resúmenes: {done}/{total}")
    return proposals


def _get_llm_client(cfg: dict):
    """Inicializa el cliente LLM según el proveedor."""
    provider = cfg.get("provider", "gemini")
    api_key = cfg.get("api_key", "")

    if provider == "gemini":
        api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            print("⚠️  No se encontró GOOGLE_API_KEY")
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            return genai.GenerativeModel(cfg.get("model", "gemini-2.0-flash"))
        except ImportError:
            print("⚠️  pip install google-generativeai")
            return None

    elif provider == "openai":
        api_key = api_key or os.environ.get("OPENAI_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            print("⚠️  No se encontró OPENAI_API_KEY ni GROQ_API_KEY")
            return None
        try:
            from openai import OpenAI
            base_url = cfg.get("base_url")
            return OpenAI(api_key=api_key, base_url=base_url)
        except ImportError:
            print("⚠️  pip install openai")
            return None

    elif provider == "ollama":
        try:
            from openai import OpenAI
            base_url = cfg.get("base_url", "http://localhost:11434/v1")
            return OpenAI(base_url=base_url, api_key="ollama")
        except ImportError:
            print("⚠️  pip install openai")
            return None

    return None


import json

def _parse_json_response(resp: Optional[str]) -> Optional[dict]:
    if not resp:
        return None
    try:
        # Extraer JSON si el LLM envolvió en markdown
        resp = resp.strip()
        if resp.startswith("```json"):
            resp = resp[7:]
        if resp.startswith("```"):
            resp = resp[3:]
        if resp.endswith("```"):
            resp = resp[:-3]
        return json.loads(resp.strip())
    except Exception:
        return None


def _detect_existing(client, prop: Proposal, cfg: dict) -> Optional[dict]:
    """Detecta si el contenido ya tiene un resumen usable."""
    prompt = _DETECT_SUMMARY_TEMPLATE.format(contenido=prop.contenido_extraido[:5000])
    resp = _call_llm(client, cfg, prompt)
    parsed = _parse_json_response(resp)
    if parsed and parsed.get("resumen") and len(parsed.get("resumen", "")) > 50:
        return parsed
    return None


def _generate(client, prop: Proposal, cfg: dict) -> Optional[dict]:
    """Genera un resumen con IA."""
    prompt = _SUMMARIZE_TEMPLATE.format(
        titulo=prop.titulo or "Sin título",
        enlace=prop.enlace,
        contenido=prop.contenido_extraido[:8000],
    )
    resp = _call_llm(client, cfg, prompt)
    return _parse_json_response(resp)


def _call_llm(client, cfg: dict, prompt: str) -> Optional[str]:
    """Llama al LLM y retorna la respuesta."""
    provider = cfg.get("provider", "gemini")
    temp = cfg.get("temperature", 0.2)
    model = cfg.get("model", "")

    try:
        if provider == "gemini":
            resp = client.generate_content(
                f"{_SYSTEM_PROMPT}\n\n{prompt}",
                generation_config={"temperature": temp},
            )
            return resp.text if resp.text else None
        elif provider in ("openai", "ollama"):
            resp = client.chat.completions.create(
                model=model or ("gpt-4o-mini" if provider == "openai" else "llama3"),
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=temp,
            )
            return resp.choices[0].message.content
    except Exception as e:
        print(f"    ⚠️  Error LLM: {e}")
        return None


def _trim(text: str, min_l: int, max_l: int) -> str:
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    return "\n".join(lines[:max_l])


def _count(text: str) -> int:
    return len([l for l in text.split("\n") if l.strip()])
