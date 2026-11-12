from fastapi import FastAPI

from app.errors import register_exception_handlers
from app.routers import auth, categories, products, users

TAGS = [
    {"name": "Estado", "description": "Comprobación de que la API responde."},
    {"name": "Autenticación", "description": "Inicio de sesión (JWT) y usuario actual."},
    {"name": "Usuarios", "description": "Gestión de usuarios. Solo administradores."},
    {
        "name": "Categorías",
        "description": "Lectura: admin y operator. Escritura: solo admin. Borrar = `is_active=false`.",
    },
    {
        "name": "Productos",
        "description": (
            "Lectura: admin y operator. Escritura: solo admin. Borrar = `is_active=false`. "
            "El stock solo cambia con movimientos."
        ),
    },
]

app = FastAPI(
    title="StockWise API",
    description=(
        "API de gestión de inventarios con autenticación JWT y roles (admin, operator).\n\n"
        "Todos los errores tienen el formato `{\"detail\", \"code\", \"errors\"?}`."
    ),
    openapi_tags=TAGS,
)

register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(categories.router)
app.include_router(products.router)


@app.get("/", tags=["Estado"], summary="Estado de la API")
def root():
    return {"message": "StockWise API is running!"}
