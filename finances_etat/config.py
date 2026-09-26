"""Chemins du projet. FINANCES_ETAT_DATA permet de déplacer les données ailleurs."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("FINANCES_ETAT_DATA", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "finances_etat.duckdb"
REF_DIR = ROOT / "ref"
SQL_DIR = ROOT / "sql"
