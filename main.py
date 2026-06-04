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
        raise Exception("DATABASE_URL missing")
    return psycopg2.connect(DATABASE_URL)

TOKENS = set()

def verify(token: str = Header(None)):
    if token not in TOKENS:
        raise HTTPException(401)

@app.post("/api/login")
def login():
    token = str(uuid.uuid4())
    TOKENS.add(token)
    return {"token": token}

# INIT DB
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
    nombre:str
    asiento:int
    precio:float

@app.get("/")
def home():
    return FileResponse("index.html")

@app.post("/api/crear")
def crear(b:B, token:str=Depends(verify)):
    c=db()
    cur=c.cursor()

    cur.execute("SELECT id FROM boletos WHERE asiento=%s",(b.asiento,))
    if cur.fetchone():
        return {"error":"ocupado"}

    id=str(uuid.uuid4())
    fecha=datetime.now()

    cur.execute("""
    INSERT INTO boletos VALUES(%s,%s,%s,%s,%s,'activo')
    """,(id,b.nombre,b.asiento,b.precio,fecha))

    c.commit()
    c.close()
    return {"ok":True}

@app.get("/api/boletos")
def listar(token:str=Depends(verify)):
    c=db().cursor()
    c.execute("SELECT * FROM boletos")
    rows=c.fetchall()
    c.connection.close()

    return [
        {
            "id":r[0],
            "nombre":r[1],
            "asiento":r[2],
            "precio":r[3],
            "fecha":str(r[4]),
            "estado":r[5]
        }
        for r in rows
    ]

@app.delete("/api/eliminar/{id}")
def eliminar(id:str, token:str=Depends(verify)):
    c=db()
    cur=c.cursor()
    cur.execute("DELETE FROM boletos WHERE id=%s",(id,))
    c.commit()
    c.close()
    return {"ok":True}

@app.post("/api/devolucion/{id}")
def devolucion(id:str, token:str=Depends(verify)):
    c=db()
    cur=c.cursor()
    cur.execute("UPDATE boletos SET estado='devuelto' WHERE id=%s",(id,))
    c.commit()
    c.close()
    return {"ok":True}

@app.get("/api/stats")
def stats(token:str=Depends(verify)):
    c=db().cursor()

    c.execute("SELECT COUNT(*), COALESCE(SUM(precio),0) FROM boletos")
    total, ingresos = c.fetchone()

    c.execute("SELECT COUNT(*) FROM boletos WHERE estado='devuelto'")
    devueltos = c.fetchone()[0]

    return {
        "total":total,
        "ingresos":ingresos,
        "devueltos":devueltos
    }

@app.get("/api/ventas")
def ventas(token:str=Depends(verify)):
    c=db().cursor()
    c.execute("""
    SELECT DATE(fecha), SUM(precio)
    FROM boletos
    GROUP BY DATE(fecha)
    ORDER BY DATE(fecha)
    """)
    rows=c.fetchall()

    return {
        "labels":[r[0] for r in rows],
        "data":[float(r[1]) for r in rows]
    }

@app.get("/api/qr/{id}")
def qr(id:str):
    img=qrcode.make(id)
    buf=io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(),media_type="image/png")

@app.get("/api/pdf/{id}")
def pdf(id:str):
    c=db().cursor()
    c.execute("SELECT * FROM boletos WHERE id=%s",(id,))
    b=c.fetchone()

    buf=io.BytesIO()
    p=canvas.Canvas(buf)

    p.drawString(100,750,f"{b[1]} asiento {b[2]}")
    p.drawString(100,730,f"${b[3]}")
    p.drawString(100,710,f"{b[4]}")
    p.drawString(100,690,f"estado {b[5]}")

    p.save()
    buf.seek(0)

    return Response(buf.getvalue(),media_type="application/pdf")
