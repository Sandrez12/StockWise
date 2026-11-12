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
- [x] Modelos SQLAlchemy (usuarios con rol, categorías, productos, movimientos de stock) y migración inicial con Alembic
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
    models.py      Modelos: User, Category, Product, StockMovement
  alembic/         Entorno y migraciones (versions/)
  alembic.ini
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

## Base de datos y migraciones

El esquema lo gestiona Alembic; la URL se toma de las variables `POSTGRES_*` (`app/config.py`). Desde `backend/`:

```bash
alembic upgrade head      # aplicar migraciones
alembic downgrade -1      # deshacer la última
alembic check             # falla si los modelos tienen cambios sin migración
```

Las migraciones se escriben y revisan a mano (no se confía ciegamente en `--autogenerate`).

Reglas de integridad en la base de datos:

- `products.sku` y `users.email` únicos.
- `products.stock >= 0` y `products.price >= 0` (CHECK).
- Movimientos: `entrada` y `salida` con cantidad positiva; `ajuste` con cantidad distinta de cero y con signo.
- Las claves foráneas son `RESTRICT`: no se puede borrar un producto, usuario o categoría con registros asociados.
- Roles (`admin`, `operator`) y tipos de movimiento (`entrada`, `salida`, `ajuste`) son enums de PostgreSQL.

## Pruebas

Desde `backend/`, con el entorno virtual activo:

```bash
pytest                       # todas
pytest -m "not integration"  # solo las unitarias, sin base de datos
```

Las pruebas **nunca leen `backend/.env`**: `tests/conftest.py` sobrescribe las variables `POSTGRES_*` antes de importar la aplicación.

- **Unitarias**: no necesitan base de datos ni archivos de entorno.
- **Integración** (`tests/integration`): usan una base de pruebas PostgreSQL; las de migraciones recrean el esquema `public` de esa base, migran hasta `head` y verifican las restricciones. Para ejecutarlas en local:

  ```bash
  docker compose up -d
  cp .env.test.example .env.test   # ajusta TEST_POSTGRES_PASSWORD
  pytest
  ```

  El usuario debe poder crear bases de datos (el de `docker-compose.yml` puede). Las pruebas crean la base si no existe y **se niegan a ejecutarse si su nombre no termina en `_test`**, para no tocar datos reales. Sin credenciales de prueba, estas pruebas se omiten con un mensaje explicativo. `.env.test` está ignorado por git; también se pueden definir las variables `TEST_POSTGRES_*` en el entorno.

## Integración continua

`.github/workflows/ci.yml` se ejecuta en cada push a `main` y a las ramas `semana-*`, y en los pull requests hacia `main`. Levanta un servicio `postgres:16`, instala `requirements-dev.txt` con Python 3.11, aplica las migraciones sobre una base vacía (`alembic upgrade head` y `alembic check`) y ejecuta `pytest` completo.

## Tecnologías

Python, FastAPI, SQLAlchemy 2, psycopg 3, PostgreSQL 16, Alembic, Docker Compose, pytest, GitHub Actions.
