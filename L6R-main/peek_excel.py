import pandas as pd
import json

path = r"G:\.shortcut-targets-by-id\1aTmljYyGPrs_Bzd3EYv5Wb8gCefh6Ox1\Projeto CSN\CSN\1. ALERTAS DE CALOR\PP3.3.23 CONTROLE DE ALERTA CSN.xlsx"

xl = pd.ExcelFile(path)

for sheet in xl.sheet_names:
    print(f"\n--- Sheet: {sheet} ---")
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    header_row = -1
    for idx, row in df.iterrows():
        row_str = ' '.join([str(x).upper() for x in row.values if pd.notna(x)])
        if 'CÓDIGO' in row_str or 'PROPRIEDADE' in row_str or 'CODIGO' in row_str:
            header_row = idx
            break
    
    if header_row != -1:
        print(f"Found header at row {header_row}")
        df_real = pd.read_excel(path, sheet_name=sheet, header=header_row)
        print(df_real.head().to_string())
    else:
        print("Header not found")
