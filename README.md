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
- [x] Catálogo: endpoints de categorías y productos (permisos por rol, paginación, búsqueda y filtros)
- [x] Autenticación JWT con roles (`admin`, `operator`) y gestión de usuarios
- [x] Integración continua con GitHub Actions (pruebas unitarias y de integración con PostgreSQL)

## Estructura

```
backend/
  app/
    main.py        Aplicación FastAPI
    config.py      Lectura y validación de variables de entorno
    database.py    Motor, sesión, Base declarativa y dependencia get_db
    models.py      Modelos: User, Category, Product, StockMovement
    security.py    Hash argon2 de contraseñas y tokens JWT
    deps.py        get_current_user y require_role
    schemas.py     Esquemas Pydantic de entrada y salida
    routers/       auth, users, categories y products
    errors.py      Formato de error único de la API
    cli.py         Comandos de consola (create-admin)
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
# 1. Levantar la base de datos (después de crear backend/.env, paso 3)
docker compose --env-file backend/.env up -d

# 2. Crear el entorno e instalar dependencias
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt   # incluye las de ejecución

# 3. Configurar variables de entorno (edita POSTGRES_PASSWORD)
cp .env.example .env
# edita POSTGRES_PASSWORD y SECRET_KEY (obligatoria, mínimo 32 caracteres):
#   python -c "import secrets; print(secrets.token_hex(32))"

# 3b. Aplicar migraciones y crear el primer administrador
alembic upgrade head
python -m app.cli create-admin   # pide correo y contraseña (sin eco)

# 4. Iniciar la API
fastapi dev app/main.py
```

`docker-compose.yml` toma `POSTGRES_USER`, `POSTGRES_PASSWORD` y `POSTGRES_DB` de `backend/.env` mediante `--env-file` (por eso el comando lo incluye). Esas tres son las únicas variables que llegan al contenedor de Postgres: `SECRET_KEY` y el resto del `.env` solo las lee la API. Sin `--env-file`, compose falla con un mensaje que lo indica. Si ya existía un volumen de Postgres creado con otra contraseña, la nueva no se aplicará: usa la anterior o recrea el volumen (`docker compose down -v`, que borra los datos).

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
- Categorías y productos tienen `is_active` para el borrado lógico; los productos tienen además `min_stock >= 0` (umbral de stock bajo).
- Roles (`admin`, `operator`) y tipos de movimiento (`entrada`, `salida`, `ajuste`) son enums de PostgreSQL.

## Catálogo: categorías y productos

Lectura para `admin` y `operator`; escritura solo `admin`. La documentación interactiva está en `/docs`.

| Endpoint | Rol |
|---|---|
| `GET /categories`, `GET /categories/{id}` | admin, operator |
| `POST /categories`, `PATCH /categories/{id}`, `DELETE /categories/{id}` | admin |
| `GET /products`, `GET /products/{id}` | admin, operator |
| `POST /products`, `PATCH /products/{id}`, `DELETE /products/{id}` | admin |

- **Borrar = `is_active=false`** (borrado lógico, idempotente); se restaura con `PATCH` y `is_active=true`. Los inactivos no aparecen en las listas ni (para el `operator`) en el detalle; el `admin` los ve con `include_inactive=true`. No se puede desactivar una categoría con productos activos (409).
- **El stock no se edita por la API de productos.** Nace en 0 y solo cambiará con movimientos de stock; enviar `stock` al crear o actualizar devuelve 422.
- **Paginación**: `limit` (1-100, 20 por defecto) y `offset`. La respuesta es `{items, total, limit, offset}`.
- **Búsqueda y filtros de productos**: `q` (texto en nombre o SKU, sin distinguir mayúsculas; `%` y `_` se tratan como texto), `category_id` y `low_stock=true` (productos con `stock <= min_stock`; el umbral `min_stock`, 0 por defecto, es propio de cada producto y se edita con `PATCH`). Las categorías admiten `q` por nombre.
- **SKU**: se normaliza a mayúsculas, admite letras, dígitos, `.`, `-` y `_`, y es único (409 si se repite). El precio admite como máximo 2 decimales y no puede ser negativo. Un producto solo puede asignarse a una categoría existente y activa (422).
- **Formato de error único**: `{"detail": "mensaje", "code": "not_found", "errors": [{"field": "body.price", "message": "..."}]}`. `errors` solo aparece en validaciones (422) y nunca incluye los valores enviados. Códigos: `bad_request`, `unauthorized`, `forbidden`, `not_found`, `method_not_allowed`, `conflict`, `validation_error`.

## Autenticación y roles

- `POST /auth/login`: formulario OAuth2 (`username` = correo, `password`). Devuelve un token JWT de acceso (HS256) que expira a los 30 minutos por defecto (`ACCESS_TOKEN_EXPIRE_MINUTES`). El error es el mismo si el correo no existe, la contraseña falla o el usuario está inactivo.
- `GET /auth/me`: usuario autenticado.
- Envía el token en la cabecera `Authorization: Bearer <token>`.
- **No hay registro público.** El primer administrador se crea con `python -m app.cli create-admin`; después, los administradores gestionan usuarios:

| Endpoint | Rol |
|---|---|
| `POST /users` crear usuario | admin |
| `GET /users` listar (`limit` 1-100, `offset`) | admin |
| `PATCH /users/{id}/role` cambiar rol | admin |
| `PATCH /users/{id}/active` activar o desactivar | admin |

Permisos previstos: el `admin` gestiona usuarios, categorías y productos; el `operator` solo consulta y registra movimientos de stock.

Detalles de seguridad:

- **Límite de intentos de login:** tras 5 intentos fallidos en 15 minutos para la misma combinación IP + correo, `POST /auth/login` responde `429` con `code: "too_many_requests"` y la cabecera `Retry-After` (segundos). Cuenta igual si el correo existe o no, bloquea también la contraseña correcta mientras dure y un login correcto reinicia el contador. **Limitación:** es una implementación propia en memoria (sin dependencias), así que el contador no se comparte entre varias instancias ni sobrevive a un reinicio, y la IP es la de la conexión directa (detrás de un proxy inverso habría que configurarlo para que informe la IP real). Para varias instancias haría falta un almacén compartido, como Redis.

- Contraseñas con argon2id (`pwdlib`), de 12 a 128 caracteres; nunca se guardan ni se devuelven (las respuestas no incluyen el hash).
- `SECRET_KEY` es obligatoria, sin valor por defecto y de al menos 32 caracteres; la aplicación no arranca si falta o es corta.
- El rol y el estado del usuario se leen de la base en cada petición: desactivar a alguien o cambiarle el rol surte efecto de inmediato, aunque conserve un token.
- Un administrador no puede cambiar su propio rol ni desactivarse (evita quedarse sin administradores).

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
  docker compose --env-file backend/.env up -d
  cp .env.test.example .env.test   # ajusta TEST_POSTGRES_PASSWORD
  pytest
  ```

  El usuario debe poder crear bases de datos (el de `docker-compose.yml` puede). Las pruebas crean la base si no existe y **se niegan a ejecutarse si su nombre no termina en `_test`**, para no tocar datos reales. Sin credenciales de prueba, estas pruebas se omiten con un mensaje explicativo. `.env.test` está ignorado por git; también se pueden definir las variables `TEST_POSTGRES_*` en el entorno.

## Integración continua

`.github/workflows/ci.yml` se ejecuta en cada push a `main` y a las ramas `semana-*`, y en los pull requests hacia `main`. Levanta un servicio `postgres:16`, instala `requirements-dev.txt` con Python 3.11, aplica las migraciones sobre una base vacía (`alembic upgrade head` y `alembic check`) y ejecuta `pytest` completo.

## Tecnologías

Python, FastAPI, SQLAlchemy 2, psycopg 3, PostgreSQL 16, Alembic, PyJWT, pwdlib (argon2), Docker Compose, pytest, GitHub Actions.
