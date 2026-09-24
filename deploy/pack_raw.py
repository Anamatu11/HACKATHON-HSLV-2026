"""Comprime los .txt crudos de DATOS/ en deploy/raw/*.txt.gz para el despliegue.

Railway limita `railway up` a ~40 MB; los crudos (~196 MB) quedan en ~21 MB.
Uso:  python deploy/pack_raw.py
"""
import gzip
import shutil
from pathlib import Path

RAW_DIR = Path("DATOS")
OUT_DIR = Path("deploy/raw")

OUT_DIR.mkdir(parents=True, exist_ok=True)
total = 0
for src in sorted(RAW_DIR.glob("*.txt")):
    dst = OUT_DIR / f"{src.name}.gz"
    with src.open("rb") as f_in, gzip.open(dst, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out, 1 << 20)
    total += dst.stat().st_size
    print(f"{src.name:28s} -> {dst.stat().st_size / 1e6:5.1f} MB")
print(f"Total: {total / 1e6:.1f} MB")
