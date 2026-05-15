# 🗞️ Boletín de Vigilancia Tecnológica — CIEV/UNER

Sistema de automatización para la generación de boletines de vigilancia tecnológica del CIEV (Centro de Investigación y Estudios en Vigilancia Tecnológica) de la Facultad de Ingeniería de la UNER.

## 🚀 Inicio rápido

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Configurar

Editá `config/settings.yaml` con tus credenciales y preferencias:

- **Google Sheets:** Configurá el `spreadsheet_id` y las credenciales del Service Account
- **CSV alternativo:** Si no usás Google Sheets, exportá tu planilla como CSV y configurá `csv_fallback_path`
- **LLM:** Configurá tu proveedor de IA preferido (Gemini, OpenAI o Ollama)

### 3. Ejecutar

```bash
# Boletín de emprendedurismo
python -m src.main --boletin emprendedurismo --fecha-envio 2026-05-06

# Boletín de tecnologías médicas
python -m src.main --boletin tecnologias_medicas --fecha-envio 2026-05-13

# Solo validar links y fechas (sin generar resúmenes)
python -m src.main --boletin emprendedurismo --fecha-envio 2026-05-06 --solo-validar

# Usando un CSV en lugar de Google Sheets
python -m src.main --boletin emprendedurismo --fecha-envio 2026-05-06 --csv-input datos.csv

# Agregar URLs extra (encontradas en redes sociales, etc.)
python -m src.main --boletin emprendedurismo --fecha-envio 2026-05-06 --urls-extra "https://ejemplo.com/beca1,https://ejemplo.com/curso2"
```

## 📁 Estructura del proyecto

```
├── config/
│   ├── settings.yaml              # Configuración general
│   └── credentials/               # Credenciales Google API (gitignored)
├── src/
│   ├── main.py                    # CLI principal
│   ├── collector/
│   │   ├── sheets_collector.py    # Lee links desde Google Sheets / CSV
│   │   └── web_scraper.py         # Extrae contenido de páginas web
│   ├── validator/
│   │   ├── link_validator.py      # Valida que los links funcionen
│   │   └── date_validator.py      # Extrae y valida fechas
│   ├── summarizer/
│   │   └── ai_summarizer.py       # Genera resúmenes con IA
│   ├── categorizer/
│   │   └── categorizer.py         # Clasifica en categorías del boletín
│   ├── card_builder/
│   │   └── card_builder.py        # Arma fichas y genera output
│   └── models/
│       └── proposal.py            # Modelo de datos
├── output/                        # Fichas generadas
├── requirements.txt
└── README.md
```

## 🔧 Pipeline de procesamiento

```
Google Sheets / CSV
        │
        ▼
  1. Recolección de URLs
        │
        ▼
  2. Validación de links (HTTP status)
        │
        ▼
  3. Scraping de contenido web
        │
        ▼
  4. Extracción y validación de fechas
        │
        ▼
  5. Generación de resúmenes (IA)
        │
        ▼
  6. Categorización automática
        │
        ▼
  7. Armado de fichas (JSON + Markdown + CSV)
```

## 📋 Formato de salida

Cada ficha tiene el formato de 2 columnas × 5 filas:

| Campo | Detalle |
|---|---|
| **Título** | Nombre de la propuesta |
| **Resumen** | 5-8 líneas basadas en el contenido real |
| **País/Institución** | Origen de la propuesta |
| **Fecha** | Tipo y fecha (ej: "Inscripción: 30/06/2026") |
| **Enlace** | URL de la propuesta |

## ⚙️ Configuración del LLM

El sistema soporta tres proveedores de IA:

| Proveedor | Variable de entorno | Modelo por defecto |
|---|---|---|
| Google Gemini | `GOOGLE_API_KEY` | gemini-2.0-flash |
| OpenAI | `OPENAI_API_KEY` | gpt-4o-mini |
| Ollama (local) | — | llama3 |

## 📊 Categorías del boletín

🎓 Becas · 📢 Convocatorias · 📚 Cursos · 🎪 Eventos · 💰 Financiamiento · 📜 Normas · 📰 Noticias · 🔬 Patentes · 💻 Webinars

#Proyecto en desarrollo
