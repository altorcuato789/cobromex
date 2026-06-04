from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
import os
import psycopg2
import uuid
from datetime import datetime
import io
import qrcode
from reportlab.pdfgen import canvas

app = FastAPI()

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- DATABASE ----------------
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# ---------------- AUTH SIMPLE ----------------
ADMIN_USER = "admin"
ADMIN_PASS = "1234"
TOKENS = set()

def verify_token(token: str = Header(None)):
    if token not in TOKENS:
        raise HTTPException(status_code=401, detail="No autorizado")

# ---------------- INIT DB ----------------
def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS boletos (
            id TEXT PRIMARY KEY,
            nombre TEXT,
            asiento INT,
            precio FLOAT,
            fecha TEXT,
            pagado INT DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- MODELS ----------------
class Login(BaseModel):
    user: str
    password: str

class Boleto(BaseModel):
    nombre: str
    asiento: int
    precio: float

# ---------------- FRONT ----------------
@app.get("/")
def home():
    return FileResponse("index.html")

# ---------------- LOGIN ----------------
@app.post("/api/login")
def login(data: Login):
    if data.user == ADMIN_USER and data.password == ADMIN_PASS:
        token = str(uuid.uuid4())
        TOKENS.add(token)
        return {"token": token}
    raise HTTPException(status_code=401, detail="Credenciales incorrectas")

# ---------------- CREAR BOLETO ----------------
@app.post("/api/crear")
def crear(data: Boleto, token: str = Depends(verify_token)):
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT id FROM boletos WHERE asiento=%s", (data.asiento,))
    if c.fetchone():
        conn.close()
        return {"error": "Asiento ocupado"}

    boleto_id = str(uuid.uuid4())
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute("""
        INSERT INTO boletos (id, nombre, asiento, precio, fecha, pagado)
        VALUES (%s, %s, %s, %s, %s, 0)
    """, (boleto_id, data.nombre, data.asiento, data.precio, fecha))

    conn.commit()
    conn.close()

    return {"ok": True}

# ---------------- LISTAR ----------------
@app.get("/api/boletos")
def listar(token: str = Depends(verify_token)):
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT * FROM boletos")
    rows = c.fetchall()

    conn.close()

    return [
        {
            "id": r[0],
            "nombre": r[1],
            "asiento": r[2],
            "precio": r[3],
            "fecha": r[4],
            "pagado": r[5]
        }
        for r in rows
    ]

# ---------------- PAGAR ----------------
@app.post("/api/pagar/{id}")
def pagar(id: str, token: str = Depends(verify_token)):
    conn = get_conn()
    c = conn.cursor()

    c.execute("UPDATE boletos SET pagado=1 WHERE id=%s", (id,))

    conn.commit()
    conn.close()

    return {"ok": True}

# ---------------- ELIMINAR ----------------
@app.delete("/api/eliminar/{id}")
def eliminar(id: str, token: str = Depends(verify_token)):
    conn = get_conn()
    c = conn.cursor()

    c.execute("DELETE FROM boletos WHERE id=%s", (id,))

    conn.commit()
    conn.close()

    return {"ok": True}

# ---------------- STATS ----------------
@app.get("/api/stats")
def stats(token: str = Depends(verify_token)):
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM boletos")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM boletos WHERE pagado=1")
    pagados = c.fetchone()[0]

    c.execute("SELECT SUM(precio) FROM boletos WHERE pagado=1")
    ingresos = c.fetchone()[0] or 0

    conn.close()

    return {
        "total_boletos": total,
        "pagados": pagados,
        "pendientes": total - pagados,
        "ingresos": ingresos
    }

# ---------------- QR ----------------
@app.get("/api/qr/{id}")
def qr(id: str):
    img = qrcode.make(id)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(buf.getvalue(), media_type="image/png")

# ---------------- PDF ----------------
@app.get("/api/pdf/{id}")
def pdf(id: str):
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT * FROM boletos WHERE id=%s", (id,))
    b = c.fetchone()

    conn.close()

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)

    p.drawString(100, 750, f"Nombre: {b[1]}")
    p.drawString(100, 730, f"Asiento: {b[2]}")
    p.drawString(100, 710, f"Precio: ${b[3]}")
    p.drawString(100, 690, f"Fecha: {b[4]}")
    p.drawString(100, 670, f"Estado: {'Pagado' if b[5] else 'Pendiente'}")

    p.save()
    buffer.seek(0)

    return Response(buffer.getvalue(), media_type="application/pdf")
