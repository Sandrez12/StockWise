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
- [x] Pruebas automatizadas de la configuración y del endpoint raíz
- [ ] Modelos de productos, categorías y movimientos de stock
- [ ] Endpoints CRUD
- [ ] Autenticación
- [ ] Integración continua (CI)

## Estructura

```
backend/
  app/
    main.py        Aplicación FastAPI
    config.py      Lectura y validación de variables de entorno
    database.py    Motor, sesión, Base declarativa y dependencia get_db
  tests/           Pruebas con pytest
  pytest.ini
  requirements.txt       Dependencias de ejecución
  requirements-dev.txt   Añade pytest y httpx
  .env.example
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
pytest
```

Las pruebas fijan sus propias variables de entorno y no necesitan la base de datos ni un `.env`.

## Tecnologías

Python, FastAPI, SQLAlchemy 2, psycopg 3, PostgreSQL 16, Docker Compose, pytest.
