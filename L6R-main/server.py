# -*- coding: utf-8 -*-
"""
GEOPORTAL CSN - Servidor Backend & Proxy NASA FIRMS (FastAPI)
- Proxy para arquivo CSV estático de 7 dias da NASA FIRMS
- Versão simplificada para rodar perfeitamente na Hostgator (sem geopandas/shapely)
"""
import os
import sys
import datetime
from pathlib import Path

import requests
from fastapi import FastAPI, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, Response

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

app = FastAPI(title="GEOPORTAL CSN - Backend & NASA FIRMS Proxy", version="3.2.0")

# Habilitar CORS irrestrito
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FIRMS_KEY = "9ae335e3f3fa02559ba3872c841c2ec6"

# Resolução Dinâmica de Diretório
BASE_DIR = Path(__file__).resolve().parent
if not (BASE_DIR / "public").exists() and (BASE_DIR / "L6R" / "L6R-main" / "public").exists():
    BASE_DIR = BASE_DIR / "L6R" / "L6R-main"

LAYERS_DIR = BASE_DIR / "public" / "layers"

@app.get("/api/status")
def get_status():
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    brasilia_tz = datetime.timezone(datetime.timedelta(hours=-3))
    brt_now = utc_now.astimezone(brasilia_tz)
    
    return {
        "status": "online",
        "service": "GEOPORTAL CSN Proxy & Backend",
        "time_utc": utc_now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "time_brasilia": brt_now.strftime("%Y-%m-%d %H:%M:%S BRT"),
        "firms_key_configured": bool(FIRMS_KEY)
    }

@app.get("/api/focos/7d_csv")
@app.get("/geoportal/api/focos/7d_csv")
@app.get("/api-geoportal/api/focos/7d_csv")
def proxy_nasa_7d_csv():
    """
    Proxy simples para contornar o bloqueio de CORS no arquivo CSV estático de 7 dias da NASA.
    """
    url = f"https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_South_America_7d.csv"
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return Response(content=resp.content, media_type="text/csv")
    except Exception as e:
        return Response(content=f"Error fetching NASA CSV: {str(e)}", status_code=502)

# Rotas Fallback para as Camadas Locais (GeoJSON/QMD)
@app.get("/api/layers/{camada_nome}")
def serve_layer(camada_nome: str):
    file_path = LAYERS_DIR / camada_nome
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path), media_type="application/json")
    return JSONResponse(status_code=404, content={"error": "Camada não encontrada"})

# Montar pasta pública de estáticos
if (BASE_DIR / "public").exists():
    app.mount("/public", StaticFiles(directory=str(BASE_DIR / "public")), name="public")

@app.get("/data_aoi.js")
def serve_data_aoi():
    p = BASE_DIR / "data_aoi.js"
    if p.exists():
        return Response(content=p.read_bytes(), media_type="application/javascript")
    p_pub = LAYERS_DIR / "data_aoi.js"
    if p_pub.exists():
        return Response(content=p_pub.read_bytes(), media_type="application/javascript")
    return JSONResponse(status_code=404, content={"error": "data_aoi.js não encontrado"})

@app.get("/favicon.ico")
def serve_favicon():
    return JSONResponse(status_code=204, content={})

@app.get("/")
def serve_root():
    index_path = BASE_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding='utf-8'))
    return JSONResponse(status_code=404, content={"error": "index.html não encontrado"})

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*70)
    print("🚀 GEOPORTAL CSN - SERVIDOR & PROXY NASA FIRMS ONLINE")
    print("👉 Acesse o WebGIS no navegador: http://localhost:8000")
    print("👉 Documentação Interativa da API: http://localhost:8000/docs")
    print("="*70 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
