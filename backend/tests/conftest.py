import os

# Se sobrescriben (no setdefault) para que las pruebas nunca dependan de un
# .env local ni del entorno del desarrollador. Debe ejecutarse antes de
# importar app.database, que crea el motor al importarse.
os.environ["POSTGRES_USER"] = "test_user"
os.environ["POSTGRES_PASSWORD"] = "test_password"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["POSTGRES_DB"] = "test_db"
