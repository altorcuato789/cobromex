from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

boletos = []

class B(BaseModel):
    nombre: str
    asiento: int
    precio: float

@app.get("/")
def home():
    return FileResponse("index.html")

@app.post("/api/crear")
def crear(b: B):
    boleto = {
        "id": str(uuid.uuid4()),
        "nombre": b.nombre,
        "asiento": b.asiento,
        "precio": b.precio,
        "fecha": str(datetime.now())
    }
    boletos.append(boleto)
    return {"ok": True}

@app.get("/api/boletos")
def listar():
    return boletos
