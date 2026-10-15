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
- [ ] Modelos de productos, categorías y movimientos de stock
- [ ] Endpoints CRUD
- [ ] Autenticación
- [ ] Pruebas automatizadas

## Estructura

```
backend/
  app/
    main.py        Aplicación FastAPI
    database.py    Motor y sesión de SQLAlchemy
  requirements.txt
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
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env

# 4. Iniciar la API
fastapi dev app/main.py
```

La API queda en `http://127.0.0.1:8000` y la documentación interactiva (Swagger) en `http://127.0.0.1:8000/docs`.

## Tecnologías

Python, FastAPI, SQLAlchemy 2, psycopg 3, PostgreSQL 16, Docker Compose.
