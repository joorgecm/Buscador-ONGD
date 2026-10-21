# Buscador de ONGD (IEI)

Proyecto de Integración de Sistemas de Información (**IEI**) para la extracción, limpieza, almacenamiento y búsqueda geográfica de Organizaciones No Gubernamentales para el Desarrollo (**ONGD**) procedentes de tres fuentes:
- **Comunitat Valenciana** (`CSV`)
- **Catalunya** (`XML`)
- **Canarias** (`JSON`)

---

## 🛠️ Stack Tecnológico

| Capa | Tecnología | Función |
| :--- | :--- | :--- |
| **Lenguaje Back-end** | Python 3.12 (`uv`) | Extractores, scraper, wrappers y APIs en un solo lenguaje |
| **Extractores** | `csv`/`pandas` (CV), `lxml` (CAT), `json` (CAN) | Leer cada fuente y producir el formato común, errores y reparaciones |
| **Scraper** | `selenium` (Chrome headless) | Obtener código postal y coordenadas con caché en archivo |
| **Respaldo Scraper** | `httpx` (CartoCiudad / Nominatim) | Fallback automático si Selenium falla |
| **Coordenadas** | `pyproj` | Conversión y verificación local `EPSG:25830` a `WGS84` |
| **LLM** | `groq` | Clasificación del ámbito de las entidades de Catalunya |
| **APIs (Carga y Búsqueda)** | `FastAPI` | Endpoints `/carga`, `/almacen`, `/entidades` y OpenAPI en `/docs` |
| **Base de Datos** | `PostgreSQL 17` + `SQLAlchemy 2.0` + `psycopg 3` | Almacén de datos (`provincia`, `localidad`, `entidad`) |
| **Front-end** | `React 19` + `Vite 8` + `TypeScript` | Pantallas de carga del almacén y buscador de entidades |
| **Mapa** | `OpenLayers` (`ol`) | Visualización y búsqueda por área visible (bounding box) |

---

## 📁 Estructura del Proyecto

```text
iei-2/
├── docker-compose.yml          # Contenedor PostgreSQL 17 para el almacén de datos
├── backend/                    # Proyecto Python gestionado con uv
│   ├── pyproject.toml          # Dependencias y configuración de Ruff / Pytest
│   ├── .env.example            # Plantilla de variables de entorno (DB, GROQ_API_KEY)
│   ├── cache/                  # Caché en disco para consultas de Selenium y Groq
│   ├── data/                   # Fuentes de datos originales (CSV, XML, JSON)
│   ├── tests/                  # Tests unitarios e integración con pytest
│   └── app/
│       ├── main.py             # Punto de entrada FastAPI y configuración CORS
│       ├── core/               # Configuración global (pydantic-settings)
│       ├── db/                 # Motor y sesiones SQLAlchemy 2.0 + psycopg v3
│       ├── models/             # Modelos del almacén (Provincia, Localidad, Entidad)
│       ├── schemas/            # Esquemas Pydantic (formato común, errores, reparaciones)
│       ├── extractors/         # Extractores por fuente (CV, CAT, CAN)
│       ├── scraper/            # Scraper Selenium + pyproj + respaldos
│       ├── llm/                # Cliente Groq para clasificar ámbito en Catalunya
│       ├── wrappers/           # Wrappers de consulta por fuente sobre el almacén
│       └── api/                # Routers de carga y búsqueda
└── frontend/                   # Aplicación React + TypeScript + Vite
    ├── package.json            # Dependencias (React 19, OpenLayers 10, Vite 8)
    ├── vite.config.ts          # Configuración de Vite y proxy hacia FastAPI (:8000)
    └── src/
        ├── components/         # Componentes reutilizables (Mapa OpenLayers, etc.)
        ├── pages/              # Pantallas de Carga y Búsqueda
        ├── services/           # Cliente HTTP hacia la API
        └── types/              # Definiciones TypeScript
```

---

## 🚀 Puesta en Marcha Rápida

### 1. Base de Datos (PostgreSQL)

Levanta el contenedor de PostgreSQL mediante Docker Compose desde la raíz del proyecto:

```powershell
docker compose up -d
```

### 2. Back-end (FastAPI + Python)

1. Entra en el directorio `backend/` y crea tu archivo `.env` a partir de la plantilla:
   ```powershell
   cd backend
   Copy-Item .env.example .env
   ```
   *(Recuerda añadir tu `GROQ_API_KEY` en `backend/.env` cuando vayas a usar el clasificador LLM).*

2. Inicia el servidor de desarrollo de FastAPI usando `uv`:
   ```powershell
   uv run fastapi dev app/main.py
   ```
   - API disponible en: `http://127.0.0.1:8000`
   - Documentación interactiva OpenAPI (Swagger): `http://127.0.0.1:8000/docs`

### 3. Front-end (React + Vite)

En otra terminal, entra en `frontend/` y arranca el servidor de desarrollo:

```powershell
cd frontend
npm run dev
```
- Aplicación disponible en: `http://localhost:5173` *(con proxy configurado hacia `:8000`)*.
