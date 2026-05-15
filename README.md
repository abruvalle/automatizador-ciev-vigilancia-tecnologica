# 🗞️ Automatizador de Boletines de Vigilancia Tecnológica — CIEV/UNER

Sistema en desarrollo para la automatización parcial del proceso de generación de boletines de vigilancia tecnológica del CIEV (Centro de Investigación y Estudios en Vigilancia Tecnológica) de la Facultad de Ingeniería de la UNER.

---

## ⚠️ Estado del proyecto

> **Proyecto actualmente en desarrollo activo.**

Este repositorio corresponde a un prototipo experimental desarrollado en el marco de una beca académica.  
La arquitectura, funcionalidades y flujo de procesamiento continúan evolucionando y pueden modificarse significativamente.

Actualmente el sistema:

- no se encuentra preparado para uso productivo,
- puede contener errores o cambios incompatibles,
- depende de configuraciones locales específicas,
- y está orientado principalmente a experimentación, automatización interna y aprendizaje.

---

## 🎯 Objetivo del proyecto

Automatizar distintas etapas del armado semanal de boletines de vigilancia tecnológica, incluyendo:

- recolección de convocatorias y eventos,
- validación de enlaces,
- extracción de fechas,
- filtrado geográfico,
- generación automática de resúmenes con IA,
- categorización temática,
- y armado estructurado de fichas para boletines.

---

## 🚀 Funcionalidades implementadas

Actualmente el sistema permite:

- Recolección de propuestas desde:
  - Google Sheets / CSV
  - búsquedas web automáticas
- Scraping automático de contenido
- Validación de enlaces
- Extracción automática de fechas relevantes
- Filtrado geográfico orientado a oportunidades accesibles desde Argentina
- Generación automática de resúmenes mediante LLMs
- Clasificación automática por categorías
- Exportación estructurada en distintos formatos

---

## 📁 Estructura del proyecto

```text
├── config/
│   └── settings.yaml
│
├── src/
│   ├── main.py
│   ├── collector/
│   ├── validator/
│   ├── summarizer/
│   ├── categorizer/
│   ├── card_builder/
│   └── models/
│
├── output/
├── requirements.txt
└── README.md
