"""
CLI principal — Pipeline de automatización del boletín.

Orquesta todos los módulos: recolección → validación → resumen →
categorización → armado de fichas.

Uso:
    python -m src.main --boletin emprendedurismo --fecha-envio 2026-05-06
    python -m src.main --boletin tecnologias_medicas --fecha-envio 2026-05-13 --solo-validar
"""

from __future__ import annotations

import sys
import os
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
import yaml

from src.models.proposal import TipoBoletin
from src.collector.sheets_collector import collect_from_sheets, collect_from_manual_urls
from src.collector.search_collector import collect_from_search
from src.collector.web_scraper import scrape_proposals
from src.validator.link_validator import validate_links
from src.validator.date_validator import extract_and_validate_dates
from src.validator.geo_validator import validate_geography
from src.summarizer.ai_summarizer import generate_summaries
from src.categorizer.categorizer import categorize_proposals
from src.card_builder.card_builder import build_cards


def load_config(config_path: str = "config/settings.yaml") -> dict:
    """Carga la configuración desde el archivo YAML."""
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"⚠️  Archivo de configuración no encontrado: {config_path}")
        print("   Usando configuración por defecto.")
        return {}

    with open(config_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@click.command()
@click.option(
    "--boletin", "-b",
    type=click.Choice(["emprendedurismo", "tecnologias_medicas"]),
    required=True,
    help="Tipo de boletín a generar.",
)
@click.option(
    "--fecha-envio", "-f",
    type=str,
    required=True,
    help="Fecha de envío del boletín (YYYY-MM-DD).",
)
@click.option(
    "--config", "-c",
    type=str,
    default="config/settings.yaml",
    help="Ruta al archivo de configuración.",
)
@click.option(
    "--solo-validar",
    is_flag=True,
    default=False,
    help="Solo recolectar y validar, sin generar resúmenes.",
)
@click.option(
    "--urls-extra",
    type=str,
    default="",
    help="URLs adicionales separadas por coma.",
)
@click.option(
    "--csv-input",
    type=str,
    default="",
    help="Ruta a un CSV con propuestas (alternativa a Google Sheets).",
)
@click.option(
    "--output-format",
    type=click.Choice(["json", "markdown", "csv", "all"]),
    default="markdown",
    help="Formato de salida.",
)
@click.option(
    "--origen",
    type=click.Choice(["csv", "internet", "ambos"]),
    default="csv",
    help="Fuente de búsqueda: solo CSV, solo Internet, o ambos.",
)
def main(
    boletin: str,
    fecha_envio: str,
    config: str,
    solo_validar: bool,
    urls_extra: str,
    csv_input: str,
    output_format: str,
    origen: str,
):
    """
    🗞️  Pipeline de automatización del Boletín de Vigilancia Tecnológica — CIEV/UNER

    Automatiza: recolección de propuestas → validación de links y fechas →
    generación de resúmenes → categorización → armado de fichas.
    """
    # Banner
    print("=" * 65)
    print("🗞️  Boletín de Vigilancia Tecnológica — CIEV/UNER")
    print("=" * 65)

    # Parsear tipo de boletín y fecha
    tipo_boletin = TipoBoletin(boletin)
    try:
        fecha = date.fromisoformat(fecha_envio)
    except ValueError:
        print(f"❌ Fecha inválida: {fecha_envio}. Usá el formato YYYY-MM-DD.")
        sys.exit(1)

    print(f"📋 Boletín: {tipo_boletin.value.replace('_', ' ').title()}")
    print(f"📅 Fecha de envío: {fecha.strftime('%d/%m/%Y')}")
    print(f"⚙️  Config: {config}")
    print()

    # Cargar configuración
    cfg = load_config(config)

    # Override del CSV si se proporcionó
    if csv_input:
        cfg.setdefault("google_sheets", {})["csv_fallback_path"] = csv_input

    # Override del formato de output
    if output_format == "all":
        cfg.setdefault("output", {})["formatos"] = ["json", "markdown", "csv"]
    else:
        cfg.setdefault("output", {})["formatos"] = [output_format]

    # === PASO 1: Recolección ===
    print("\n" + "=" * 50)
    print("📥 PASO 1: Recolección de propuestas")
    print("=" * 50)

    proposals = []

    # Recolección desde CSV/Sheets
    if origen in ["csv", "ambos"]:
        proposals.extend(collect_from_sheets(cfg, tipo_boletin))

    # Agregar URLs extra si se proporcionaron
    if urls_extra:
        extra_urls = [u.strip() for u in urls_extra.split(",") if u.strip()]
        extra_proposals = collect_from_manual_urls(extra_urls, tipo_boletin)
        proposals.extend(extra_proposals)

    # Búsqueda profunda en internet
    if origen in ["internet", "ambos"]:
        search_proposals = collect_from_search(tipo_boletin, cfg)
        proposals.extend(search_proposals)

    if not proposals:
        print("\n❌ No se encontraron propuestas. Verificá la configuración.")
        sys.exit(1)

    print(f"\n📊 Total de propuestas recolectadas: {len(proposals)}")

    # === PASO 2: Validación de links ===
    print("\n" + "=" * 50)
    print("🔗 PASO 2: Validación de enlaces")
    print("=" * 50)

    proposals = validate_links(proposals, cfg)

    # === PASO 3: Scraping de contenido ===
    print("\n" + "=" * 50)
    print("🔍 PASO 3: Extracción de contenido web")
    print("=" * 50)

    # Solo scrapear propuestas con links válidos
    to_scrape = [p for p in proposals if p.link_status_code and p.link_status_code < 400]
    scrape_proposals(to_scrape, cfg)

    # === PASO 4: Extracción y validación de fechas ===
    print("\n" + "=" * 50)
    print("📅 PASO 4: Extracción y validación de fechas")
    print("=" * 50)

    proposals = extract_and_validate_dates(proposals, fecha, cfg)

    # === PASO 4.5: Validación geográfica ===
    print("\n" + "=" * 50)
    print("🌎 PASO 4.5: Validación geográfica (Argentina/LatAm)")
    print("=" * 50)

    proposals = validate_geography(proposals, cfg)

    if solo_validar:
        print("\n" + "=" * 50)
        print("✅ Modo --solo-validar: pipeline detenido.")
        _print_summary(proposals)
        sys.exit(0)

    # === PASO 5: Generación de resúmenes ===
    print("\n" + "=" * 50)
    print("🤖 PASO 5: Generación de resúmenes")
    print("=" * 50)

    proposals = generate_summaries(proposals, cfg)

    # === PASO 6: Categorización ===
    print("\n" + "=" * 50)
    print("🏷️  PASO 6: Categorización")
    print("=" * 50)

    proposals = categorize_proposals(proposals, cfg)

    # === PASO 7: Armado de fichas ===
    print("\n" + "=" * 50)
    print("📊 PASO 7: Armado de fichas y generación de output")
    print("=" * 50)

    result = build_cards(proposals, tipo_boletin, fecha, cfg)

    # === Resumen final ===
    print("\n" + "=" * 65)
    print("🎉 ¡Pipeline completado exitosamente!")
    print("=" * 65)
    stats = result["estadisticas"]
    print(f"   📊 Total procesadas:     {stats['total_propuestas']}")
    print(f"   ✅ Fichas válidas:        {stats['validas']}")
    print(f"   ⚠️  Pendientes revisión:  {stats['pendientes']}")
    print(f"   ❌ Rechazadas:            {stats['rechazadas']}")
    print(f"   🏷️  Categorías:            {stats['categorias']}")
    print()
    print("   📄 Archivos generados:")
    for fmt, path in result["archivos"].items():
        print(f"      → {path}")
    print()
    print("   Revisá los archivos generados y armá el HTML del boletín. 🚀")


def _print_summary(proposals):
    """Imprime un resumen del estado de las propuestas."""
    from src.models.proposal import EstadoValidacion
    print("\n📊 Resumen:")
    for estado in EstadoValidacion:
        count = sum(1 for p in proposals if p.estado == estado)
        if count > 0:
            print(f"   {estado.value}: {count}")


if __name__ == "__main__":
    main()
