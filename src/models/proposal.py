"""
Modelo de datos para las propuestas del boletín de vigilancia tecnológica.

Define la estructura de una propuesta y métodos de serialización
a JSON, diccionario y CSV.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from enum import Enum
from typing import Optional


class TipoBoletin(str, Enum):
    """Tipo de boletín."""
    EMPRENDEDURISMO = "emprendedurismo"
    TECNOLOGIAS_MEDICAS = "tecnologias_medicas"


class Categoria(str, Enum):
    """Categorías válidas para las fichas del boletín."""
    BECAS = "becas"
    CONVOCATORIAS = "convocatorias"
    CURSOS = "cursos"
    EVENTOS = "eventos"
    FINANCIAMIENTO = "financiamiento"
    NORMAS = "normas"
    NOTICIAS = "noticias"
    PATENTES = "patentes"
    TITULO = "titulo"
    WEBINARS = "webinars"


class TipoFecha(str, Enum):
    """Tipos de fecha que puede tener una propuesta."""
    INSCRIPCION = "inscripción"
    EVENTO = "evento"
    WEBINAR = "webinar"
    SIMPOSIO = "simposio"
    ENTREGA_RESUMENES = "entrega de resúmenes"
    ENTREGA_PROYECTOS = "entrega de proyectos"
    INICIO = "inicio"
    CIERRE = "cierre"
    OTRO = "otro"


class EstadoValidacion(str, Enum):
    """Estado de validación de una propuesta."""
    PENDIENTE = "pendiente"
    VALIDA = "válida"
    LINK_ROTO = "link_roto"
    FECHA_PASADA = "fecha_pasada"
    EXCLUIDA_GEOGRAFIA = "excluida_geografia"
    ERROR = "error"


@dataclass
class Proposal:
    """
    Representa una propuesta/ficha del boletín.

    Contiene toda la información necesaria para armar la ficha final:
    título, resumen, país/institución, fecha, enlace, categoría, etc.
    """

    # --- Campos de la ficha ---
    titulo: str = ""
    resumen: str = ""
    pais_institucion: str = ""
    fecha: Optional[date] = None
    tipo_fecha: TipoFecha = TipoFecha.OTRO
    enlace: str = ""
    modalidad: str = ""
    publico_objetivo: str = ""
    trl: str = ""

    # --- Metadatos ---
    categoria: Optional[Categoria] = None
    boletin: Optional[TipoBoletin] = None
    estado: EstadoValidacion = EstadoValidacion.PENDIENTE

    # --- Información de procesamiento ---
    contenido_extraido: str = ""  # Texto completo extraído de la página
    resumen_fuente: str = ""  # "original" | "generado_ia" | ""
    link_status_code: Optional[int] = None
    fechas_detectadas: list[dict] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)

    # --- Origen ---
    fuente: str = ""  # "google_sheets", "manual", etc.
    fila_sheets: Optional[int] = None  # Fila en la planilla de origen

    def es_valida(self) -> bool:
        """Retorna True si la propuesta pasó todas las validaciones."""
        return self.estado == EstadoValidacion.VALIDA

    def fecha_formateada(self) -> str:
        """Retorna la fecha formateada con el tipo de fecha."""
        if self.fecha is None:
            return "Sin fecha"
        fecha_str = self.fecha.strftime("%d/%m/%Y")
        return f"{self.tipo_fecha.value.capitalize()}: {fecha_str}"

    def to_dict(self) -> dict:
        """Convierte la propuesta a diccionario (serializable a JSON)."""
        data = asdict(self)
        # Convertir date a string
        if data.get("fecha"):
            data["fecha"] = data["fecha"].isoformat()
        # Convertir enums a string
        for key in ["tipo_fecha", "categoria", "boletin", "estado"]:
            if data.get(key) and hasattr(data[key], "value"):
                data[key] = data[key]
            # asdict already converts enum to value for dataclass
        return data

    def to_ficha_dict(self) -> dict:
        """
        Retorna la ficha en el formato de 2 columnas × 5 filas
        que se usa en el boletín.
        """
        ficha = {
            "Título": self.titulo,
            "Resumen": self.resumen,
            "País/Institución": self.pais_institucion,
            "Fecha": self.fecha_formateada(),
            "Enlace": self.enlace,
        }
        if self.modalidad:
            ficha["Modalidad"] = self.modalidad
        if self.publico_objetivo:
            ficha["Público Objetivo"] = self.publico_objetivo
        if self.trl:
            ficha["TRL"] = self.trl
        return ficha

    def to_json(self) -> str:
        """Serializa la propuesta a JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)

    @classmethod
    def from_dict(cls, data: dict) -> Proposal:
        """Crea una propuesta desde un diccionario."""
        # Convertir fecha string a date
        if data.get("fecha") and isinstance(data["fecha"], str):
            try:
                data["fecha"] = date.fromisoformat(data["fecha"])
            except ValueError:
                data["fecha"] = None

        # Convertir strings a enums
        if data.get("tipo_fecha") and isinstance(data["tipo_fecha"], str):
            try:
                data["tipo_fecha"] = TipoFecha(data["tipo_fecha"])
            except ValueError:
                data["tipo_fecha"] = TipoFecha.OTRO

        if data.get("categoria") and isinstance(data["categoria"], str):
            try:
                data["categoria"] = Categoria(data["categoria"])
            except ValueError:
                data["categoria"] = None

        if data.get("boletin") and isinstance(data["boletin"], str):
            try:
                data["boletin"] = TipoBoletin(data["boletin"])
            except ValueError:
                data["boletin"] = None

        if data.get("estado") and isinstance(data["estado"], str):
            try:
                data["estado"] = EstadoValidacion(data["estado"])
            except ValueError:
                data["estado"] = EstadoValidacion.PENDIENTE

        # Filtrar keys que no son campos del dataclass
        valid_fields = {f.name for f in Proposal.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered_data)

    def __repr__(self) -> str:
        return (
            f"Proposal(titulo={self.titulo!r}, "
            f"categoria={self.categoria}, "
            f"fecha={self.fecha}, "
            f"estado={self.estado})"
        )
