from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import auth, records

app = FastAPI(title="Веб-платформа медичних записів API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # Дозволяємо всі методи (GET, POST, PUT, DELETE)
    allow_headers=["*"],  # Дозволяємо всі заголовки (включаючи Authorization)
)

app.include_router(auth.router)
app.include_router(records.router)


@app.get("/")
def read_root():
    return {"message": "Бекенд медичної платформи успішно запущено!"}
