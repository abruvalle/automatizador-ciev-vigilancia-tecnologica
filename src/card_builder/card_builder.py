"""
Armador de fichas del boletín.

Toma las propuestas procesadas, las agrupa por categoría,
las ordena por fecha, y genera los archivos de salida
en múltiples formatos (JSON, Markdown, CSV).
"""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import date
from pathlib import Path

from ..models.proposal import Categoria, EstadoValidacion, Proposal, TipoBoletin


# Emojis por defecto para las categorías
_DEFAULT_EMOJIS = {
    "becas": "🎓",
    "convocatorias": "📢",
    "cursos": "📚",
    "eventos": "🎪",
    "financiamiento": "💰",
    "normas": "📜",
    "noticias": "📰",
    "patentes": "🔬",
    "titulo": "📌",
    "webinars": "💻",
}


def build_cards(
    proposals: list[Proposal],
    tipo_boletin: TipoBoletin,
    fecha_boletin: date,
    config: dict,
) -> dict:
    """
    Arma las fichas del boletín a partir de las propuestas procesadas.

    1. Filtra solo propuestas válidas
    2. Agrupa por categoría
    3. Ordena por fecha dentro de cada categoría
    4. Genera los archivos de salida

    Args:
        proposals: Lista de propuestas procesadas.
        tipo_boletin: Tipo de boletín.
        fecha_boletin: Fecha de envío del boletín.
        config: Configuración.

    Returns:
        Diccionario con las fichas agrupadas y las rutas de los archivos generados.
    """
    # Filtrar propuestas válidas (con resumen y categoría)
    valid = [
        p for p in proposals
        if p.estado == EstadoValidacion.VALIDA
        and p.resumen
        and p.categoria
    ]

    # También incluir las que no tienen fecha pero sí resumen (para revisión)
    pendientes = [
        p for p in proposals
        if p.estado == EstadoValidacion.PENDIENTE
        and p.resumen
        and p.categoria
    ]

    all_cards = valid + pendientes
    rechazadas = [p for p in proposals if p not in all_cards]

    print(f"\n📊 Armando fichas del boletín...")
    print(f"   ✅ Propuestas válidas: {len(valid)}")
    print(f"   ⚠️  Pendientes de revisión: {len(pendientes)}")
    print(f"   ❌ Rechazadas: {len(rechazadas)}")

    # Agrupar por categoría
    grouped = defaultdict(list)
    for prop in all_cards:
        cat_name = prop.categoria.value if prop.categoria else "sin_categoria"
        grouped[cat_name].append(prop)

    # Ordenar cada categoría por fecha (menor a mayor)
    for cat in grouped:
        grouped[cat].sort(key=lambda p: p.fecha or date.max)

    # Obtener emojis de la config
    emojis = config.get("boletin", {}).get("categoria_emojis", _DEFAULT_EMOJIS)

    # Generar outputs
    output_config = config.get("output", {})
    output_dir = output_config.get("directorio", "output")
    formatos = output_config.get("formatos", ["markdown"])

    # Crear directorio de salida
    os.makedirs(output_dir, exist_ok=True)

    # Nombre base para los archivos
    boletin_name = tipo_boletin.value.replace("_", "-")
    fecha_str = fecha_boletin.strftime("%Y-%m-%d")
    base_name = f"boletin-{boletin_name}-{fecha_str}"

    output_files = {}

    if "json" in formatos:
        path = _generate_json(grouped, output_dir, base_name, fecha_boletin, tipo_boletin)
        output_files["json"] = path

    if "markdown" in formatos:
        path = _generate_markdown(grouped, output_dir, base_name, fecha_boletin, tipo_boletin, emojis)
        output_files["markdown"] = path

    if "csv" in formatos:
        path = _generate_csv(grouped, output_dir, base_name)
        output_files["csv"] = path



    print(f"\n📄 Archivos generados:")
    for fmt, path in output_files.items():
        print(f"   → {fmt}: {path}")

    return {
        "fichas": dict(grouped),
        "archivos": output_files,
        "estadisticas": {
            "total_propuestas": len(proposals),
            "validas": len(valid),
            "pendientes": len(pendientes),
            "rechazadas": len(rechazadas),
            "categorias": len(grouped),
        },
    }


def _generate_json(
    grouped: dict[str, list[Proposal]],
    output_dir: str,
    base_name: str,
    fecha_boletin: date,
    tipo_boletin: TipoBoletin,
) -> str:
    """Genera el output en formato JSON."""
    data = {
        "boletin": tipo_boletin.value,
        "fecha_envio": fecha_boletin.isoformat(),
        "categorias": {},
    }

    for cat, props in grouped.items():
        data["categorias"][cat] = [
            {
                "titulo": p.titulo,
                "resumen": p.resumen,
                "pais_institucion": p.pais_institucion,
                "fecha": p.fecha_formateada(),
                "enlace": p.enlace,
                "modalidad": p.modalidad,
                "publico_objetivo": p.publico_objetivo,
                "trl": p.trl,
                "tipo_fecha": p.tipo_fecha.value if p.tipo_fecha else "",
                "resumen_fuente": p.resumen_fuente,
            }
            for p in props
        ]

    filepath = os.path.join(output_dir, f"{base_name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath


def _generate_markdown(
    grouped: dict[str, list[Proposal]],
    output_dir: str,
    base_name: str,
    fecha_boletin: date,
    tipo_boletin: TipoBoletin,
    emojis: dict,
) -> str:
    """Genera el output en formato Markdown."""
    boletin_titulo = tipo_boletin.value.replace("_", " ").title()
    lines = [
        f"# Boletín de {boletin_titulo} — {fecha_boletin.strftime('%d de %B de %Y')}",
        "",
    ]

    # Ordenar categorías
    cat_order = [c.value for c in Categoria]
    sorted_cats = sorted(grouped.keys(), key=lambda c: cat_order.index(c) if c in cat_order else 99)

    total_fichas = sum(len(props) for props in grouped.values())
    lines.append(f"**Total de fichas: {total_fichas}**\n")

    for cat in sorted_cats:
        props = grouped[cat]
        emoji = emojis.get(cat, "📋")
        lines.append(f"## {emoji} {cat.capitalize()}")
        lines.append("")

        for prop in props:
            lines.append(f"### {prop.titulo or 'Sin título'}")
            lines.append("")
            lines.append("| | |")
            lines.append("|---|---|")
            lines.append(f"| Título | {prop.titulo} |")

            # Resumen: reemplazar saltos de línea con espacios para la tabla
            resumen_table = prop.resumen.replace("\n", " ") if prop.resumen else ""
            lines.append(f"| Resúmen | {resumen_table} |")
            lines.append(f"| País/Institución | {prop.pais_institucion or ''} |")
            
            fecha_str = prop.fecha.strftime("%d/%m/%Y") if prop.fecha else "Sin fecha"
            lines.append(f"| Fecha límite de inscripción | {fecha_str} |")
            lines.append(f"| Enlace | {prop.enlace} |")
            if prop.modalidad:
                lines.append(f"| Modalidad | {prop.modalidad} |")
            if prop.publico_objetivo:
                lines.append(f"| Público Objetivo | {prop.publico_objetivo} |")
            if prop.trl:
                lines.append(f"| TRL | {prop.trl} |")
            lines.append("")
            lines.append("---")
            lines.append("")

    filepath = os.path.join(output_dir, f"{base_name}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def _generate_csv(
    grouped: dict[str, list[Proposal]],
    output_dir: str,
    base_name: str,
) -> str:
    """Genera el output en formato CSV."""
    filepath = os.path.join(output_dir, f"{base_name}.csv")

    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Categoría", "Título", "Resumen", "País/Institución",
            "Fecha", "Tipo de Fecha", "Enlace", "Modalidad",
            "Público Objetivo", "TRL", "Fuente del Resumen",
        ])

        # Ordenar por categoría
        cat_order = [c.value for c in Categoria]
        sorted_cats = sorted(grouped.keys(), key=lambda c: cat_order.index(c) if c in cat_order else 99)

        for cat in sorted_cats:
            for prop in grouped[cat]:
                writer.writerow([
                    cat.capitalize(),
                    prop.titulo,
                    prop.resumen.replace("\n", " "),
                    prop.pais_institucion or "",
                    prop.fecha_formateada(),
                    prop.tipo_fecha.value if prop.tipo_fecha else "",
                    prop.enlace,
                    prop.modalidad,
                    prop.publico_objetivo,
                    prop.trl,
                    prop.resumen_fuente,
                ])

    return filepath


def _generate_rejected_report(
    rechazadas: list[Proposal],
    output_dir: str,
    base_name: str,
) -> str:
    """Genera un reporte de propuestas rechazadas para revisión."""
    lines = [
        "# Propuestas Rechazadas",
        "",
        "Estas propuestas fueron excluidas del boletín por los siguientes motivos:\n",
    ]

    for i, prop in enumerate(rechazadas, 1):
        lines.append(f"### {i}. {prop.titulo or prop.enlace}")
        lines.append(f"- **Enlace:** {prop.enlace}")
        lines.append(f"- **Estado:** {prop.estado.value}")
        if prop.errores:
            lines.append(f"- **Errores:** {'; '.join(prop.errores)}")
        lines.append("")

    filepath = os.path.join(output_dir, f"{base_name}-rechazadas.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath
