"""
Buscador automático de propuestas en internet.

Utiliza DuckDuckGo para buscar activamente convocatorias, becas,
cursos y eventos relevantes para el boletín actual, complementando
las fuentes manuales del CSV.

Estrategia de volumen:
- Se generan ~12 queries por tipo de boletín, priorizando América Latina
  e internacional, para compensar el rechazo por fechas/geografía y
  asegurar suficientes candidatos válidos al final del pipeline.
"""

from __future__ import annotations

import time

from ddgs import DDGS

from ..models.proposal import Proposal, TipoBoletin

# Resultados por query — lo suficiente para llegar con ~60-80 candidatos brutos
_RESULTS_PER_QUERY = 8

# Dominios genéricos a ignorar
_IGNORED_DOMAINS = [
    "youtube.com", "wikipedia.org", "facebook.com", "tiktok.com",
    "pinterest.com", "twitter.com", "instagram.com", "linkedin.com",
    "reddit.com",
]


def collect_from_search(tipo_boletin: TipoBoletin, config: dict) -> list[Proposal]:
    """
    Realiza búsquedas en internet para encontrar nuevas propuestas.

    Genera un volumen amplio de candidatos (~60-80) para que, tras el
    filtrado por fechas, geografía y relevancia, queden 20
    fichas válidas listas para el boletín.
    """
    print("\n" + "=" * 50)
    print("🌐 BÚSQUEDA PROFUNDA AUTOMÁTICA EN INTERNET")
    print("=" * 50)

    queries = _generate_queries(tipo_boletin)
    print(f"Buscando en internet usando {len(queries)} criterios distintos ({_RESULTS_PER_QUERY} resultados c/u)...")

    proposals: list[Proposal] = []
    seen_urls: set[str] = set()

    with DDGS() as ddgs:
        for query in queries:
            print(f"  🔍 Buscando: '{query}'")
            try:
                results = list(ddgs.text(
                    query,
                    region="wt-wt",
                    safesearch="moderate",
                    max_results=_RESULTS_PER_QUERY,
                ))

                for r in results:
                    url = r.get("href", "")
                    title = r.get("title", "")

                    if not url or url in seen_urls:
                        continue
                    if any(d in url for d in _IGNORED_DOMAINS):
                        continue

                    seen_urls.add(url)
                    proposals.append(Proposal(
                        titulo=title,
                        enlace=url,
                        boletin=tipo_boletin,
                        fuente="busqueda_automatica",
                    ))

                time.sleep(2)  # Pausa para no saturar el buscador
            except Exception as e:
                print(f"    ⚠️ Error buscando '{query}': {e}")

    print(f"✅ Se encontraron {len(proposals)} links potenciales en internet.")
    print("   El sistema ahora analizará si son propuestas puntuales o páginas generales...")
    return proposals


def _generate_queries(tipo_boletin: TipoBoletin) -> list[str]:
    """
    Genera frases de búsqueda amplias y geográficamente inclusivas.

    Se priorizan términos que impliquen acceso para residentes de Argentina:
    'latinoamérica', 'internacional', 'iberoamérica', 'Argentina'.
    Se usan 12 queries para garantizar volumen suficiente de candidatos.
    """
    year = "2026"

    if tipo_boletin == TipoBoletin.EMPRENDEDURISMO:
        return [
            # Convocatorias / financiamiento enfocadas
            f'"startup" "financiamiento" "tecnología" {year} site:gob.ar',
            f'"pymes" "ANR" "innovación" {year} argentina',
            f'"emprendedor" "aceleración" "incubación" {year} latinoamérica',
            f'"fondo" "aportes no reembolsables" "startups" {year}',
            f'"convocatoria" "emprendimientos de base tecnológica" {year}',
            # Específicos de instituciones
            f'"convocatoria" "financiamiento" {year} site:agencia.mincyt.gob.ar',
            f'"startups" "incubación" {year} site:fan.org.ar',
            f'"emprendedores" "aceleración" {year} site:endeavor.org.ar',
            # Cursos y Eventos
            f'"curso" "industria 4.0" "transformación digital" {year} inscripción',
            f'"taller" "economía del conocimiento" "pymes" {year}',
            f'"congreso" "ecosistema emprendedor" {year} argentina',
            f'"webinar" "agtech" OR "healthtech" {year} gratuito',
        ]
    elif tipo_boletin == TipoBoletin.TECNOLOGIAS_MEDICAS:
        return [
            # Convocatorias / proyectos específicos
            f'"salud digital" "convocatoria" "innovación" {year} latinoamérica',
            f'"bioingeniería" "proyectos de investigación" {year} argentina',
            f'"dispositivos médicos" "financiamiento" {year} internacional',
            f'"evaluación de tecnologías sanitarias" {year} site:iecs.org.ar',
            # Becas e Investigación
            f'"beca" "investigación médica" "salud pública" {year}',
            f'"beca" "posdoctorado" "materiales nanoestructurados" {year} argentina',
            f'"fellowship" "bioinformática" {year} latinoamérica',
            f'"aportaciones innovadoras" "medicina" {year}',
            # Cursos / formación y Eventos
            f'"curso" "seguridad del paciente" "salud" {year} inscripción',
            f'"diplomatura" "ingeniería clínica" {year}',
            f'"simposio" "biónica" OR "point-of-care" {year} latinoamérica',
            f'"congreso" "bioingeniería" OR "bioinformática" {year} site:edu.ar',
            f'"curso" "análisis de datos" OR "ciencia de datos" "salud" {year}',
            f'"analistas de datos" "salud digital" {year} latinoamérica',
        ]

    return []
