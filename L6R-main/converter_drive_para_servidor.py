# -*- coding: utf-8 -*-
"""
Script de Conversao e Sincronizacao Espacial (Google Drive -> Servidor WebGIS)
- Le a pasta: G:\.shortcut-targets-by-id\1aTmljYyGPrs_Bzd3EYv5Wb8gCefh6Ox1\Projeto CSN\Shapes Gerais\DADOS para deskbord
- Trata espacos e caminhos no Windows
- Converte GPKG, Shapefile, KML para GeoJSON WGS84 (EPSG:4326)
- Salva na pasta publica do servidor
"""
import os
import sys
import json
import traceback
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import geopandas as gpd
from shapely.geometry import mapping

# Caminhos suportados (com espacos)
DRIVE_DIR_1 = Path(r"G:\.shortcut-targets-by-id\1aTmljYyGPrs_Bzd3EYv5Wb8gCefh6Ox1\Projeto CSN\Shapes Gerais\DADOS para deskbord")
DRIVE_DIR_2 = Path(r"G:\.shortcut-targets-by-id\1aTmljYyGPrs_Bzd3EYv5Wb8gCefh6Ox1\Projeto CSN\Shapes Gerais\DADOS")

def sincronizar_drive():
    print("\n" + "="*70)
    print("📂 [GEOPORTAL CSN] INICIANDO SINCRONIZAÇÃO DE ARQUIVOS DO GOOGLE DRIVE")
    print("="*70)

    # 1. Identificar pasta de origem
    source_dir = None
    if DRIVE_DIR_1.exists() and DRIVE_DIR_1.is_dir():
        source_dir = DRIVE_DIR_1
        print(f"✅ [DRIVE ENCONTRADO] Pasta principal: '{source_dir}'")
    elif DRIVE_DIR_2.exists() and DRIVE_DIR_2.is_dir():
        source_dir = DRIVE_DIR_2
        print(f"⚠️ [DRIVE FALLBACK] Pasta alternativa: '{source_dir}'")
    else:
        print(f"❌ [ERRO CRÍTICO] Nenhuma das pastas do Drive foi encontrada!")
        print(f"   Tentado: '{DRIVE_DIR_1}'")
        print(f"   Tentado: '{DRIVE_DIR_2}'")
        return {"status": "error", "message": "Diretorio do Google Drive nao encontrado"}

    # Criar pastas de saida em ambos os locais possiveis
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / "public" / "layers"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 [DESTINO] Pasta pública do servidor: '{output_dir}'")

    catalog = []
    all_features = []

    # 2. Listar arquivos
    spatial_extensions = ('.gpkg', '.shp', '.kml', '.kmz', '.geojson')
    files_found = [f for f in source_dir.iterdir() if f.suffix.lower() in spatial_extensions]
    
    print(f"\n🔍 [VERIFICAÇÃO] Encontrados {len(files_found)} arquivos espaciais para processar:")
    for f in files_found:
        print(f"   • {f.name} ({f.stat().st_size:,} bytes)")
    print("-" * 70)

    if not files_found:
        print("⚠️ [AVISO] Nenhum arquivo espacial (.gpkg, .shp, .kml) foi encontrado na pasta.")
        return {"status": "warning", "message": "Nenhum arquivo espacial encontrado"}

    # 3. Processar cada arquivo
    for file_path in sorted(files_found):
        base_name = file_path.stem.replace(" ", "_").replace("-", "_")
        print(f"\n⚙️ [PROCESSANDO] {file_path.name} ...")
        
        try:
            # Leitura com GeoPandas
            gdf = gpd.read_file(str(file_path))
            num_feats = len(gdf)
            orig_crs = gdf.crs.to_string() if gdf.crs else "Nenhum (Indefinido)"
            print(f"   - Feições lidas: {num_feats}")
            print(f"   - CRS Original: {orig_crs}")

            # Ajuste de CRS para EPSG:4326 (WGS 84)
            if gdf.crs is None:
                print(f"   - ⚠️ Sem projeção definida. Assumindo EPSG:31982 e convertendo para EPSG:4326...")
                gdf = gdf.set_crs("EPSG:31982").to_crs("EPSG:4326")
            elif gdf.crs.to_string() != "EPSG:4326":
                print(f"   - 🔄 Reprojetando de {gdf.crs.to_string()} para EPSG:4326 (WGS84)...")
                gdf = gdf.to_crs("EPSG:4326")

            # Sanitizar colunas de data/hora para formato string
            for col in gdf.columns:
                if 'datetime' in str(gdf[col].dtype):
                    gdf[col] = gdf[col].astype(str)

            # Salvar GeoJSON individual
            out_geojson = output_dir / f"{base_name}.geojson"
            gdf.to_file(str(out_geojson), driver="GeoJSON")
            
            geom_type = str(gdf.geometry.geom_type.iloc[0]) if num_feats > 0 else "Vazio"
            print(f"   - ✅ Salvo em: {out_geojson.name} ({geom_type})")

            catalog.append({
                "id": base_name,
                "original_file": file_path.name,
                "name": file_path.stem,
                "features_count": num_feats,
                "file_path": f"/public/layers/{base_name}.geojson",
                "geometry_type": geom_type
            })

            # Adicionar à lista unificada se for Área / Fazenda / Limite / Aceiro
            fn_lower = file_path.name.lower()
            is_aoi = any(k in fn_lower for k in ["area", "fazenda", "floriano", "sbs", "serra", "aceiro", "limite"])
            if is_aoi:
                for _, row in gdf.iterrows():
                    geom = mapping(row.geometry) if row.geometry is not None else None
                    if geom:
                        props = row.drop('geometry').to_dict()
                        props['source_layer'] = file_path.name
                        all_features.append({
                            "type": "Feature",
                            "properties": props,
                            "geometry": geom
                        })

        except Exception as e:
            print(f"   - ❌ ERRO ao processar {file_path.name}: {e}")
            traceback.print_exc(limit=2)

    # 4. Salvar Catálogo e Camada Unificada
    cat_file = output_dir / "catalog.json"
    with open(cat_file, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    unified_geojson = {
        "type": "FeatureCollection",
        "features": all_features
    }
    
    uni_file = output_dir / "aoi_unificadas.geojson"
    with open(uni_file, "w", encoding="utf-8") as f:
        json.dump(unified_geojson, f, ensure_ascii=False)

    # Atualizar data_aoi.js no script_dir
    data_aoi_file = script_dir / "data_aoi.js"
    with open(data_aoi_file, "w", encoding="utf-8") as f:
        f.write("window.AOI_GEOJSON = " + json.dumps(unified_geojson, ensure_ascii=False) + ";")

    # Copiar também para a pasta do Drive se for diferente
    if source_dir != script_dir:
        try:
            with open(source_dir / "data_aoi.js", "w", encoding="utf-8") as f:
                f.write("window.AOI_GEOJSON = " + json.dumps(unified_geojson, ensure_ascii=False) + ";")
        except Exception:
            pass

    print("\n" + "="*70)
    print(f"🎉 [SINCRONIZAÇÃO CONCLUÍDA COM SUCESSO]")
    print(f"   • {len(catalog)} camadas GeoJSON geradas em '{output_dir}'")
    print(f"   • {len(all_features)} polígonos de Áreas de Interesse (AOIs) consolidados.")
    print("="*70 + "\n")

    return {
        "status": "success",
        "layers_count": len(catalog),
        "total_aoi_polygons": len(all_features),
        "catalog": catalog
    }

if __name__ == "__main__":
    sincronizar_drive()
