# -*- coding: utf-8 -*-
"""
GEOPORTAL CSN - Servidor Backend & Proxy NASA FIRMS (FastAPI)
- Monitoramento de Focos de Queimadas (VIIRS 375m NOAA-21 / 24h)
- Abordagem 1 (Principal): API REST CSV da NASA FIRMS (VIIRS_NOAA21_NRT / BBOX América do Sul)
- Abordagem 2 (Fallback KMZ): Download, descompactação em memória (.kmz -> .kml) e conversão para GeoJSON
- Fallback CSV Adicional: Feed consolidado South America 24h
- Cruzamento Espacial Rápido com Áreas de Interesse (AOIs) e Geração de GeoJSON
"""
import os
import sys
import io
import csv
import json
import time
import datetime
import traceback
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, mapping
from fastapi import FastAPI, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, Response

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

app = FastAPI(title="GEOPORTAL CSN - Backend & NASA FIRMS Proxy", version="3.1.0")

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
UNIFIED_AOI_PATH = LAYERS_DIR / "aoi_unificadas.geojson"

aoi_gdf = None

def carregar_aois():
    global aoi_gdf
    if UNIFIED_AOI_PATH.exists():
        try:
            aoi_gdf = gpd.read_file(str(UNIFIED_AOI_PATH))
            print(f"✅ [BACKEND] {len(aoi_gdf)} polígonos de AOI carregados na memória com sucesso!")
        except Exception as e:
            print(f"❌ [BACKEND] Erro ao carregar AOIs: {e}")
    else:
        print(f"⚠️ [BACKEND] aoi_unificadas.geojson não encontrado em '{UNIFIED_AOI_PATH}'")

carregar_aois()

def extrair_focos_do_kmz(kmz_bytes: bytes):
    """
    Descompacta o KMZ em memória, extrai o KML e converte os Placemarks em lista de focos.
    """
    focos = []
    pontos = []
    with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as z:
        for filename in z.namelist():
            if filename.endswith(".kml"):
                kml_data = z.read(filename)
                root = ET.fromstring(kml_data)
                ns = {'kml': 'http://earth.google.com/kml/2.1'}
                
                for pm in root.findall('.//kml:Placemark', ns):
                    coords_text = pm.findtext('.//kml:coordinates', '', ns).strip()
                    desc_text = pm.findtext('kml:description', '', ns) or ''
                    
                    lat, lon = None, None
                    if coords_text:
                        parts = coords_text.split(',')
                        if len(parts) >= 2:
                            try:
                                lon = float(parts[0])
                                lat = float(parts[1])
                            except ValueError:
                                pass
                                
                    if lat is not None and lon is not None:
                        frp = 5.0
                        acq_date = datetime.date.today().isoformat()
                        acq_time = "00:00"
                        if "FRP:" in desc_text:
                            try:
                                frp_part = desc_text.split("FRP:")[1].split("<")[0].strip()
                                frp = float(frp_part)
                            except Exception:
                                pass
                        if "Detection Time:" in desc_text:
                            try:
                                dt_part = desc_text.split("Detection Time:")[1].split("<")[0].strip()
                                dt_tokens = dt_part.split()
                                if len(dt_tokens) >= 2:
                                    acq_date = dt_tokens[0]
                                    acq_time = dt_tokens[1]
                            except Exception:
                                pass

                        foco = {
                            "latitude": lat,
                            "longitude": lon,
                            "bright_ti4": 300.0,
                            "frp": frp,
                            "confidence": "nominal",
                            "acq_date": acq_date,
                            "acq_time": acq_time,
                            "daynight": "D",
                            "satellite": "VIIRS NOAA-21",
                            "dentro_aoi": False,
                            "aoi_nome": None,
                            "aoi_municipio": None
                        }
                        focos.append(foco)
                        pontos.append(Point(lon, lat))
                break
    return focos, pontos

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
        "aoi_polygons_loaded": len(aoi_gdf) if aoi_gdf is not None else 0,
        "firms_key_configured": bool(FIRMS_KEY)
    }

@app.get("/api/focos/24h")
def get_focos_24h(
    min_frp: float = 0.0,
    bbox: str = "-85,-60,-30,15",
    sensor: str = "VIIRS_NOAA21_NRT"
):
    """
    Proxy NASA FIRMS com processamento do satélite NOAA-21 (VIIRS 375m / 24h).
    - Abordagem 1: API REST CSV da NASA FIRMS
    - Fallback 1: Feed CSV South America
    - Abordagem 2 (Fallback 2): Descompactação em memória do KMZ oficial da NASA e conversão para GeoJSON
    - Realiza Spatial Join com as AOIs da CSN e retorna GeoJSON FeatureCollection completo.
    """
    global aoi_gdf
    if aoi_gdf is None:
        carregar_aois()

    url_api = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/{sensor}/{bbox}/1"
    url_csv_sa = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_South_America_24h.csv"
    url_kmz_sa = "https://firms.modaps.eosdis.nasa.gov/api/kml_fire_footprints/south_america/24h/noaa-21-viirs-c2/FirespotArea_south_america_noaa-21-viirs-c2_24h.kmz"

    csv_text = None
    source_used = None
    t0 = time.time()

    focos_propriedades = []
    focos_pontos = []

    print(f"\n📡 [NASA PROXY] Buscando focos NOAA-21 (24h)...")

    # 1. Abordagem 1 (Recomendada): API REST CSV da NASA FIRMS
    try:
        resp = requests.get(url_api, timeout=12)
        if resp.status_code == 200 and "latitude" in resp.text:
            csv_text = resp.text
            source_used = "NASA_FIRMS_API_AREA_CSV"
            print(f"   ✅ [Abordagem 1] API REST CSV retornou com sucesso ({round(time.time() - t0, 2)}s)")
    except Exception as e:
        print(f"   ⚠️ [Abordagem 1] Falha ou timeout na API REST: {e}")

    # Fallback 1: Feed CSV Consolidado South America
    if not csv_text:
        print(f"   🔄 Tentando Fallback CSV South America...")
        try:
            resp_sa = requests.get(url_csv_sa, timeout=15)
            if resp_sa.status_code == 200 and "latitude" in resp_sa.text:
                csv_text = resp_sa.text
                source_used = "NASA_FIRMS_SOUTH_AMERICA_CSV_24H"
                print(f"   ✅ Feed CSV South America retornou com sucesso ({round(time.time() - t0, 2)}s)")
        except Exception as e:
            print(f"   ⚠️ Fallback CSV falhou: {e}")

    # Processar CSV obtido
    if csv_text:
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            try:
                lat = float(row['latitude'])
                lon = float(row['longitude'])
                frp = float(row.get('frp', 0.0))
                
                if frp < min_frp:
                    continue

                foco_obj = {
                    "latitude": lat,
                    "longitude": lon,
                    "bright_ti4": float(row.get('bright_ti4', row.get('brightness', 0.0))),
                    "frp": frp,
                    "confidence": row.get('confidence', 'nominal'),
                    "acq_date": row.get('acq_date', ''),
                    "acq_time": row.get('acq_time', ''),
                    "daynight": row.get('daynight', 'D'),
                    "satellite": "VIIRS NOAA-21",
                    "dentro_aoi": False,
                    "aoi_nome": None,
                    "aoi_municipio": None
                }
                focos_propriedades.append(foco_obj)
                focos_pontos.append(Point(lon, lat))
            except (ValueError, KeyError):
                continue
    else:
        # 2. Abordagem 2: Processamento do Arquivo KMZ no Servidor
        print(f"   🔄 [Abordagem 2] Baixando e descompactando KMZ South America 24h...")
        try:
            resp_kmz = requests.get(url_kmz_sa, timeout=15)
            if resp_kmz.status_code == 200 and resp_kmz.content:
                focos_propriedades, focos_pontos = extrair_focos_do_kmz(resp_kmz.content)
                source_used = "NASA_FIRMS_SOUTH_AMERICA_KMZ_UNZIPPED"
                print(f"   ✅ [Abordagem 2] KMZ descompactado e convertido: {len(focos_propriedades)} focos extraídos.")
        except Exception as e_kmz:
            print(f"   ❌ Erro ao processar KMZ da NASA: {e_kmz}")
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY,
                content={"error": "Falha na obtenção dos dados da NASA FIRMS em todas as rotas."}
            )

    # 3. Spatial Join no Servidor com GeoPandas
    focos_na_aoi_count = 0
    max_frp = 0.0
    max_frp_aoi = 0.0
    max_frp_fora = 0.0

    if focos_pontos and aoi_gdf is not None and not aoi_gdf.empty:
        try:
            focos_gdf = gpd.GeoDataFrame(focos_propriedades, geometry=focos_pontos, crs="EPSG:4326")
            if aoi_gdf.crs != focos_gdf.crs:
                aoi_gdf = aoi_gdf.to_crs(focos_gdf.crs)

            joined = gpd.sjoin(focos_gdf, aoi_gdf, how="left", predicate="intersects")
            for idx, row in joined.iterrows():
                if idx < len(focos_propriedades):
                    prop = focos_propriedades[idx]
                    if pd.notna(row.get('index_right')):
                        prop['dentro_aoi'] = True
                        prop['aoi_nome'] = str(row.get('FAZENDA') or row.get('name') or row.get('COD') or 'Área CSN')
                        prop['aoi_municipio'] = str(row.get('Municipio') or row.get('UF') or '-')
                        focos_na_aoi_count += 1
                        if prop['frp'] > max_frp_aoi:
                            max_frp_aoi = prop['frp']
                    else:
                        if prop['frp'] > max_frp_fora:
                            max_frp_fora = prop['frp']
        except Exception as e:
            print(f"⚠️ [BACKEND] Erro no Spatial Join: {e}")

    for p in focos_propriedades:
        if p['frp'] > max_frp:
            max_frp = p['frp']

    # 4. Gerar GeoJSON FeatureCollection Válido
    features = []
    for f in focos_propriedades:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [f["longitude"], f["latitude"]]
            },
            "properties": f
        })

    geojson_output = {
        "type": "FeatureCollection",
        "features": features
    }

    utc_now = datetime.datetime.now(datetime.timezone.utc)
    brasilia_tz = datetime.timezone(datetime.timedelta(hours=-3))
    brt_now = utc_now.astimezone(brasilia_tz)

    print(f"✅ [NASA PROXY] {len(focos_propriedades)} focos retornados ({source_used}) | {focos_na_aoi_count} nas AOIs | FRP Máx: {max_frp:.1f} MW")

    return {
        "status": "success",
        "source": source_used,
        "sensor": sensor,
        "timestamp_utc": utc_now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "timestamp_brasilia": brt_now.strftime("%Y-%m-%d %H:%M:%S BRT"),
        "total_focos": len(focos_propriedades),
        "focos_na_aoi": focos_na_aoi_count,
        "focos_fora": len(focos_propriedades) - focos_na_aoi_count,
        "max_frp": round(max_frp, 1),
        "max_frp_aoi": round(max_frp_aoi, 1),
        "max_frp_fora": round(max_frp_fora, 1),
        "alerta_critico": (focos_na_aoi_count > 0 or max_frp >= 10.0),
        "geojson": geojson_output,
        "focos": focos_propriedades
    }

@app.get("/api/layers")
def get_layers():
    cat_file = LAYERS_DIR / "catalog.json"
    if cat_file.exists():
        try:
            with open(cat_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

@app.get("/api/layers/{layer_id}")
def get_layer_geojson(layer_id: str):
    file_path = LAYERS_DIR / f"{layer_id}.geojson"
    if file_path.exists():
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
