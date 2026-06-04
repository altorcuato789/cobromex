from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
import os, psycopg2, uuid
from datetime import datetime
import io
import qrcode
from reportlab.pdfgen import canvas

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get("DATABASE_URL")

def db():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL no configurada")
    return psycopg2.connect(DATABASE_URL)

TOKENS = set()

def verify(token: str = Header(None)):
    if token not in TOKENS:
        raise HTTPException(status_code=401, detail="No autorizado")

@app.post("/api/login")
def login():
    token = str(uuid.uuid4())
    TOKENS.add(token)
    return {"token": token}

# ---------------- DB INIT ----------------
def init():
    c = db()
    cur = c.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS boletos(
        id TEXT PRIMARY KEY,
        nombre TEXT,
        asiento INT,
        precio FLOAT,
        fecha TIMESTAMP,
        estado TEXT
    )
    """)
    c.commit()
    c.close()

init()

class B(BaseModel):
    nombre: str
    asiento: int
    precio: float

@app.get("/")
def home():
    return FileResponse("index.html")

# ---------------- CREAR ----------------
@app.post("/api/crear")
def crear(b: B, token: str = Depends(verify)):
    try:
        c = db()
        cur = c.cursor()

        cur.execute("SELECT id FROM boletos WHERE asiento=%s", (b.asiento,))
        if cur.fetchone():
            return {"error": "asiento ocupado"}

        id = str(uuid.uuid4())
        fecha = datetime.now()

        cur.execute("""
            INSERT INTO boletos (id, nombre, asiento, precio, fecha, estado)
            VALUES (%s,%s,%s,%s,%s,'activo')
        """, (id, b.nombre, b.asiento, b.precio, fecha))

        c.commit()
        c.close()

        return {"ok": True}

    except Exception as e:
        return {"error": str(e)}

# ---------------- LISTAR ----------------
@app.get("/api/boletos")
def listar(token: str = Depends(verify)):
    c = db().cursor()
    c.execute("SELECT * FROM boletos ORDER BY fecha DESC")
    rows = c.fetchall()
    c.connection.close()

    return [
        {
            "id": r[0],
            "nombre": r[1],
            "asiento": r[2],
            "precio": r[3],
            "fecha": str(r[4]),
            "estado": r[5]
        }
        for r in rows
    ]

# ---------------- ELIMINAR ----------------
@app.delete("/api/eliminar/{id}")
def eliminar(id: str, token: str = Depends(verify)):
    c = db()
    cur = c.cursor()
    cur.execute("DELETE FROM boletos WHERE id=%s", (id,))
    c.commit()
    c.close()
    return {"ok": True}

# ---------------- DEVOLUCIÓN ----------------
@app.post("/api/devolucion/{id}")
def devolucion(id: str, token: str = Depends(verify)):
    c = db()
    cur = c.cursor()
    cur.execute("UPDATE boletos SET estado='devuelto' WHERE id=%s", (id,))
    c.commit()
    c.close()
    return {"ok": True}

# ---------------- STATS ----------------
@app.get("/api/stats")
def stats(token: str = Depends(verify)):
    c = db().cursor()

    c.execute("SELECT COUNT(*), COALESCE(SUM(precio),0) FROM boletos")
    total, ingresos = c.fetchone()

    c.execute("SELECT COUNT(*) FROM boletos WHERE estado='devuelto'")
    devueltos = c.fetchone()[0]

    c.connection.close()

    return {
        "total": total,
        "ingresos": ingresos,
        "devueltos": devueltos
    }

# ---------------- QR ----------------
@app.get("/api/qr/{id}")
def qr(id: str):
    img = qrcode.make(id)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/png")

# ---------------- PDF ----------------
@app.get("/api/pdf/{id}")
def pdf(id: str):
    c = db().cursor()
    c.execute("SELECT * FROM boletos WHERE id=%s", (id,))
    b = c.fetchone()

    buf = io.BytesIO()
    p = canvas.Canvas(buf)

    p.drawString(100, 750, f"{b[1]} - Asiento {b[2]}")
    p.drawString(100, 730, f"Precio: ${b[3]}")
    p.drawString(100, 710, f"Fecha: {b[4]}")
    p.drawString(100, 690, f"Estado: {b[5]}")

    p.save()
    buf.seek(0)

    return Response(buf.getvalue(), media_type="application/pdf")
