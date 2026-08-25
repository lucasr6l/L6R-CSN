import pandas as pd
import json
import os
import time
import subprocess
import re
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

EXCEL_PATH = r"G:\.shortcut-targets-by-id\1aTmljYyGPrs_Bzd3EYv5Wb8gCefh6Ox1\Projeto CSN\CSN\1. ALERTAS DE CALOR\PP3.3.23 CONTROLE DE ALERTA CSN.xlsx"
JSON_OUT_PATH = r"c:\DADOS para deskbord\L6R\L6R-main\public\reports_data.json"
GIT_REPO_DIR = r"c:\DADOS para deskbord\L6R\L6R-main"

CLASS_MAP = {
    "Incêndio Iminente": 5,
    "Crítico": 4,
    "Atenção": 3,
    "Favorável": 2,
    "Sem classificação": 1
}

def get_class_weight(c):
    if pd.isna(c): return 1
    c_str = str(c).strip()
    for k, v in CLASS_MAP.items():
        if k.lower() == c_str.lower():
            return v
    return 1

def process_excel():
    print("Processing Excel...")
    try:
        xl = pd.ExcelFile(EXCEL_PATH)
    except Exception as e:
        print("Error reading excel (might be open/locked):", e)
        return False
        
    all_reports = {}
    
    for sheet in xl.sheet_names:
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet, header=None)
        header_row = -1
        for idx, row in df.iterrows():
            row_str = ' '.join([str(x).upper() for x in row.values if pd.notna(x)])
            if 'CÓDIGO' in row_str or 'PROPRIEDADE' in row_str or 'CODIGO' in row_str:
                header_row = idx
                break
        
        if header_row != -1:
            df = pd.read_excel(EXCEL_PATH, sheet_name=sheet, header=header_row)
            cols = [c.upper().strip() if isinstance(c, str) else str(c) for c in df.columns]
            df.columns = cols
            
            codigo_col = next((c for c in cols if 'CÓDIGO' in c or 'CODIGO' in c), None)
            data_col = next((c for c in cols if 'DATA' in c), None)
            focos_col = next((c for c in cols if 'FOCOS' in c), None)
            prop_col = next((c for c in cols if 'PROPRIEDADE' in c), None)
            class_col = next((c for c in cols if 'CLASSIFICAÇÃO' in c or 'CLASSIFICACAO' in c), None)
            
            if not all([codigo_col, prop_col]):
                continue
                
            for _, row in df.iterrows():
                codigo = row[codigo_col]
                if pd.isna(codigo): continue
                codigo = str(codigo).strip()
                
                dt = row[data_col] if data_col and not pd.isna(row[data_col]) else ""
                if isinstance(dt, pd.Timestamp):
                    dt = dt.strftime("%d/%m/%Y")
                else:
                    dt = str(dt).strip()
                    
                focos = row[focos_col] if focos_col and not pd.isna(row[focos_col]) else 0
                try: focos = float(focos)
                except: focos = 0
                
                cls = row[class_col] if class_col and not pd.isna(row[class_col]) else "Sem classificação"
                cls = str(cls).strip()
                cls_w = get_class_weight(cls)
                
                prop_str = row[prop_col] if not pd.isna(row[prop_col]) else ""
                prop_str = str(prop_str).strip()
                
                props = re.split(r'[.,;]| e ', prop_str)
                props = [p.strip() for p in props if p.strip()]
                
                if codigo not in all_reports:
                    all_reports[codigo] = {
                        "codigo": codigo,
                        "data": dt,
                        "focos": focos,
                        "classificacao": cls,
                        "_max_weight": cls_w,
                        "propriedades": set(props)
                    }
                else:
                    if cls_w > all_reports[codigo]["_max_weight"]:
                        all_reports[codigo]["classificacao"] = cls
                        all_reports[codigo]["_max_weight"] = cls_w
                    all_reports[codigo]["propriedades"].update(props)
                    all_reports[codigo]["focos"] = max(all_reports[codigo]["focos"], focos)

    property_reports = {}
    for req in all_reports.values():
        props = list(req["propriedades"])
        del req["propriedades"]
        del req["_max_weight"]
        for p in props:
            # normalize for matching: remove accents, lowercase, trim
            p_norm = p.upper().strip()
            # For simplicity, we just use uppercase
            if p_norm not in property_reports:
                property_reports[p_norm] = []
            property_reports[p_norm].append(req)
            
    try:
        with open(JSON_OUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(property_reports, f, ensure_ascii=False, indent=2)
        print(f"JSON generated successfully at {JSON_OUT_PATH}")
        return True
    except Exception as e:
        print("Error saving JSON:", e)
        return False

def git_commit_push():
    print("Committing and pushing to git...")
    try:
        subprocess.run(["git", "add", "public/reports_data.json"], cwd=GIT_REPO_DIR, check=True)
        res = subprocess.run(["git", "commit", "-m", "Auto-update reports_data.json"], cwd=GIT_REPO_DIR, capture_output=True, text=True)
        if "nothing to commit" in res.stdout.lower() or "nothing added" in res.stdout.lower():
            print("No changes to commit.")
            return
        subprocess.run(["git", "push"], cwd=GIT_REPO_DIR, check=True)
        print("Pushed to GitHub successfully!")
    except Exception as e:
        print("Git error:", e)

class ExcelHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_run = 0
        
    def on_modified(self, event):
        # some systems might trigger on ~$.xlsx files or other temp files.
        if "PP3.3.23 CONTROLE DE ALERTA CSN.xlsx" in event.src_path and not event.src_path.split('\\')[-1].startswith('~'):
            now = time.time()
            if now - self.last_run > 5:
                self.last_run = now
                print(f"Excel modified: {event.src_path}")
                time.sleep(2)
                if process_excel():
                    git_commit_push()

if __name__ == "__main__":
    if process_excel():
        git_commit_push()
        
    print(f"Watching for changes in: {EXCEL_PATH}")
    observer = Observer()
    handler = ExcelHandler()
    watch_dir = os.path.dirname(EXCEL_PATH)
    observer.schedule(handler, path=watch_dir, recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
