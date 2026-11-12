# StockWise

Backend para la gestión de inventarios, construido con **FastAPI**, **SQLAlchemy** y **PostgreSQL**. Proyecto en desarrollo: por ahora contiene la base de la API y la conexión a la base de datos.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

## Estado actual

- [x] API base con FastAPI
- [x] Conexión a PostgreSQL con SQLAlchemy (sesión y motor configurados por variables de entorno)
- [x] Base de datos PostgreSQL en Docker Compose
- [x] Configuración validada por variables de entorno (`app/config.py`)
- [x] Pruebas unitarias (configuración y endpoint raíz) y de integración (`get_db` contra PostgreSQL)
- [ ] Modelos de productos, categorías y movimientos de stock
- [ ] Endpoints CRUD
- [ ] Autenticación
- [x] Integración continua con GitHub Actions (pruebas unitarias y de integración con PostgreSQL)

## Estructura

```
backend/
  app/
    main.py        Aplicación FastAPI
    config.py      Lectura y validación de variables de entorno
    database.py    Motor, sesión, Base declarativa y dependencia get_db
  tests/           Pruebas con pytest
    integration/   Pruebas contra PostgreSQL real
  pytest.ini
  requirements.txt       Dependencias de ejecución
  requirements-dev.txt   Añade pytest y httpx2
  .env.example
  .env.test.example
.github/workflows/ci.yml   Integración continua
docker-compose.yml   PostgreSQL 16
```

## Cómo ejecutarlo

Requisitos: Python 3.11+ y Docker.

```bash
# 1. Levantar la base de datos
docker compose up -d

# 2. Crear el entorno e instalar dependencias
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt   # incluye las de ejecución

# 3. Configurar variables de entorno (edita POSTGRES_PASSWORD)
cp .env.example .env

# 4. Iniciar la API
fastapi dev app/main.py
```

`docker-compose.yml` lee las credenciales de `backend/.env`, así que levanta la base de datos después de crear ese archivo. Si ya existía un volumen de Postgres creado con otra contraseña, la nueva no se aplicará: usa la anterior o recrea el volumen (`docker compose down -v`, que borra los datos).

Si falta alguna variable `POSTGRES_*`, la aplicación se detiene con un mensaje que indica cuáles.

La API queda en `http://127.0.0.1:8000` y la documentación interactiva (Swagger) en `http://127.0.0.1:8000/docs`.

## Pruebas

Desde `backend/`, con el entorno virtual activo:

```bash
pytest                       # todas
pytest -m "not integration"  # solo las unitarias, sin base de datos
```

Las pruebas **nunca leen `backend/.env`**: `tests/conftest.py` sobrescribe las variables `POSTGRES_*` antes de importar la aplicación.

- **Unitarias**: no necesitan base de datos ni archivos de entorno.
- **Integración** (`tests/integration`): usan una base de pruebas PostgreSQL. Para ejecutarlas en local:

  ```bash
  docker compose up -d
  cp .env.test.example .env.test   # ajusta TEST_POSTGRES_PASSWORD
  pytest
  ```

  El usuario debe poder crear bases de datos (el de `docker-compose.yml` puede). Las pruebas crean la base si no existe y **se niegan a ejecutarse si su nombre no termina en `_test`**, para no tocar datos reales. Sin credenciales de prueba, estas pruebas se omiten con un mensaje explicativo. `.env.test` está ignorado por git; también se pueden definir las variables `TEST_POSTGRES_*` en el entorno.

## Integración continua

`.github/workflows/ci.yml` se ejecuta en cada push a `main` y a las ramas `semana-*`, y en los pull requests hacia `main`. Levanta un servicio `postgres:16`, instala `requirements-dev.txt` con Python 3.11 y ejecuta `pytest` completo.

## Tecnologías

Python, FastAPI, SQLAlchemy 2, psycopg 3, PostgreSQL 16, Docker Compose, pytest, GitHub Actions.
