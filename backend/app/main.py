from fastapi import FastAPI

from app.routers import auth, users

app = FastAPI(
    title="StockWise API",
    description="API de gestión de inventarios con autenticación JWT y roles (admin, operator).",
)

app.include_router(auth.router)
app.include_router(users.router)


@app.get("/", tags=["Estado"], summary="Estado de la API")
def root():
    return {"message": "StockWise API is running!"}
