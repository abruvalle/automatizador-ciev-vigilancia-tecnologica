"""
Recolector de links desde Google Sheets.

Soporta dos modos:
1. Conexión directa a Google Sheets via API (requiere Service Account)
2. Lectura de un archivo CSV/Excel exportado manualmente (fallback)
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Optional

from ..models.proposal import Proposal, TipoBoletin


def collect_from_sheets(
    config: dict,
    tipo_boletin: TipoBoletin,
) -> list[Proposal]:
    """
    Recolecta propuestas desde Google Sheets.

    Intenta conectarse vía API primero. Si no hay credenciales configuradas
    o falla la conexión, usa el CSV de fallback.

    Args:
        config: Diccionario de configuración (de settings.yaml).
        tipo_boletin: Tipo de boletín a recolectar.

    Returns:
        Lista de propuestas con los datos básicos (enlace, metadatos de origen).
    """
    sheets_config = config.get("google_sheets", {})
    spreadsheet_id = sheets_config.get("spreadsheet_id", "")
    credentials_path = sheets_config.get("credentials_path", "")
    csv_fallback = sheets_config.get("csv_fallback_path", "")

    # Intentar con Google Sheets API
    if spreadsheet_id and credentials_path and Path(credentials_path).exists():
        try:
            return _collect_via_api(sheets_config, tipo_boletin)
        except Exception as e:
            print(f"⚠️  Error conectando a Google Sheets API: {e}")
            print("   Intentando con CSV de fallback...")

    # Fallback: leer desde CSV
    if csv_fallback and Path(csv_fallback).exists():
        return _collect_from_csv(csv_fallback, tipo_boletin)

    print("❌ No se pudo acceder a Google Sheets ni al CSV de fallback.")
    print("   Configurá 'google_sheets.spreadsheet_id' o 'google_sheets.csv_fallback_path' en config/settings.yaml")
    return []


def _collect_via_api(
    sheets_config: dict,
    tipo_boletin: TipoBoletin,
) -> list[Proposal]:
    """
    Recolecta links directamente desde la API de Google Sheets.

    Requiere:
    - gspread instalado
    - Un Service Account con acceso al spreadsheet
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise ImportError(
            "Para usar Google Sheets API necesitás instalar gspread y google-auth:\n"
            "  pip install gspread google-auth"
        )

    credentials_path = sheets_config["credentials_path"]
    spreadsheet_id = sheets_config["spreadsheet_id"]
    hojas = sheets_config.get("hojas", {})

    # Nombre de la hoja según el tipo de boletín
    nombre_hoja = hojas.get(tipo_boletin.value, tipo_boletin.value.replace("_", " ").title())

    # Autenticarse
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    client = gspread.authorize(creds)

    # Abrir spreadsheet y hoja
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(nombre_hoja)

    # Obtener todos los registros como lista de diccionarios
    records = worksheet.get_all_records()

    proposals = []
    for i, row in enumerate(records, start=2):  # start=2 porque fila 1 es header
        proposal = _row_to_proposal(row, tipo_boletin, fila=i)
        if proposal:
            proposals.append(proposal)

    # También intentar leer la hoja "Ambas" si existe
    try:
        ambas_nombre = hojas.get("ambas", "Ambas")
        worksheet_ambas = spreadsheet.worksheet(ambas_nombre)
        records_ambas = worksheet_ambas.get_all_records()
        for i, row in enumerate(records_ambas, start=2):
            proposal = _row_to_proposal(row, tipo_boletin, fila=i)
            if proposal:
                proposals.append(proposal)
    except Exception:
        # La hoja "Ambas" es opcional
        pass

    print(f"✅ Se recolectaron {len(proposals)} propuestas desde Google Sheets")
    return proposals


def _collect_from_csv(
    csv_path: str,
    tipo_boletin: TipoBoletin,
) -> list[Proposal]:
    """
    Recolecta links desde un archivo CSV exportado de Google Sheets.

    El CSV debe tener al menos las columnas: enlace/link/url
    Columnas opcionales: titulo, categoria, tipo_boletin, pais_institucion
    """
    proposals = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Normalizar nombres de columnas (minúsculas, sin espacios extra)
        if reader.fieldnames:
            reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]

        for i, row in enumerate(reader, start=2):
            # Normalizar keys
            row = {k.strip().lower(): v.strip() for k, v in row.items() if v}

            proposal = _row_to_proposal(row, tipo_boletin, fila=i)
            if proposal:
                proposals.append(proposal)

    print(f"✅ Se recolectaron {len(proposals)} propuestas desde CSV ({csv_path})")
    return proposals


def _row_to_proposal(
    row: dict,
    tipo_boletin: TipoBoletin,
    fila: int,
) -> Optional[Proposal]:
    """
    Convierte una fila (dict) en una Proposal.

    Busca el enlace en múltiples nombres de columna posibles.
    """
    # Normalizar keys
    row_lower = {k.strip().lower(): str(v).strip() for k, v in row.items()}

    # --- Filtrado por tipo de fuente ---
    # Determinar el tipo de boletín/fuente de la fila
    tipo_fila = (
        row_lower.get("tipo de fuente") or
        row_lower.get("tipo_fuente") or
        row_lower.get("tipo_boletin") or
        row_lower.get("boletin") or
        row_lower.get("tipo") or
        ""
    )
    tipo_fila = str(tipo_fila).lower().strip()

    # Lógica de filtrado:
    es_valido = False
    
    if tipo_boletin == TipoBoletin.EMPRENDEDURISMO:
        # Acepta 'Emprendedores' y 'Tecnologías médicas - Emprendedores'
        if "emprendedor" in tipo_fila or "ambas" in tipo_fila:
            es_valido = True
    elif tipo_boletin == TipoBoletin.TECNOLOGIAS_MEDICAS:
        # Acepta 'Tecnologías médicas' y 'Tecnologías médicas - Emprendedores'
        if "tecnologías médicas" in tipo_fila or "tecnologias medicas" in tipo_fila or "ambas" in tipo_fila:
            es_valido = True

    if not es_valido:
        return None
    # -----------------------------------

    # Buscar el enlace en varias columnas posibles
    enlace = (
        row_lower.get("enlace")
        or row_lower.get("link")
        or row_lower.get("url")
        or row_lower.get("enlace/link")
        or row_lower.get("dirección")
        or ""
    )

    if not enlace:
        return None

    # Asegurarse de que sea una URL válida
    if not enlace.startswith(("http://", "https://")):
        if enlace.startswith("www."):
            enlace = f"https://{enlace}"
        else:
            return None

    # Extraer otros campos si están disponibles
    titulo = row_lower.get("titulo", row_lower.get("título", row_lower.get("fuente", row_lower.get("descripción", ""))))
    categoria = row_lower.get("categoria", row_lower.get("categoría", row_lower.get("sector", "")))
    pais = row_lower.get("pais_institucion", row_lower.get("país/institución",
           row_lower.get("pais", row_lower.get("institución", row_lower.get("país/región", "")))))

    from ..models.proposal import Categoria
    cat = None
    if categoria:
        try:
            cat = Categoria(categoria.lower())
        except ValueError:
            pass

    return Proposal(
        titulo=titulo,
        enlace=enlace,
        pais_institucion=pais,
        categoria=cat,
        boletin=tipo_boletin,
        fuente="google_sheets",
        fila_sheets=fila,
    )


def collect_from_manual_urls(
    urls: list[str],
    tipo_boletin: TipoBoletin,
) -> list[Proposal]:
    """
    Crea propuestas a partir de una lista de URLs proporcionadas manualmente.

    Útil para agregar propuestas encontradas en LinkedIn, Instagram, etc.

    Args:
        urls: Lista de URLs.
        tipo_boletin: Tipo de boletín.

    Returns:
        Lista de propuestas.
    """
    proposals = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        proposals.append(
            Proposal(
                enlace=url,
                boletin=tipo_boletin,
                fuente="manual",
            )
        )
    print(f"✅ Se agregaron {len(proposals)} propuestas manuales")
    return proposals
