"""Construction de la base DuckDB à partir des fichiers bruts.

La base est reconstruite entièrement à chaque fois dans un fichier temporaire,
puis substituée à l'ancienne : un tableau de bord ouvert ne voit jamais une
base à moitié chargée, et tout reste reproductible depuis data/raw.
"""

import os
from pathlib import Path

import duckdb
import pandas as pd

from .collecte import JOURNAL, dernier_fichier
from .config import DB_PATH, REF_DIR, SQL_DIR
from .controles import executer_controles
from .lecture import lire_jsonstat, lire_lois, lire_smb
from .sources import SOURCES
from .texte import cle_libelle

COLONNES_JOURNAL = ["horodatage", "source", "url", "fichier", "sha256", "octets", "nouveau"]


def referentiel() -> pd.DataFrame:
    ref = pd.read_csv(REF_DIR / "lignes_budget.csv", dtype=str, keep_default_na=False)
    ref["parent"] = ref["parent"].replace("", None)
    ref["ordre"] = ref["ordre"].astype(int)
    return ref


def _empiler(tables: list[pd.DataFrame], cle: list[str]) -> pd.DataFrame:
    """Concatène plusieurs fichiers ; en cas de recouvrement, le dernier de la liste l'emporte."""
    df = pd.concat(tables, ignore_index=True)
    df["_ligne"] = df["code"].fillna(df["libelle_source"])
    return df.drop_duplicates(subset=["_ligne", *cle], keep="last").drop(columns="_ligne")


def _creer(con: duckdb.DuckDBPyConnection, nom: str, df: pd.DataFrame) -> None:
    con.register("_df", df)
    con.execute(f"CREATE TABLE {nom} AS SELECT * FROM _df")
    con.unregister("_df")


def construire(chemin_base: Path = DB_PATH) -> Path:
    fichiers = {s.cle: dernier_fichier(s.cle) for s in SOURCES}
    manquants = [cle for cle, f in fichiers.items() if f is None]
    if manquants:
        raise RuntimeError(f"Aucun fichier brut pour : {', '.join(manquants)}. Lancez d'abord la collecte.")

    ref = referentiel()
    codes = {cle_libelle(lib): code for lib, code in zip(ref["libelle_source"], ref["code"])}

    smb = _empiler([lire_smb(fichiers[k], codes).assign(source=k) for k in ("smb_2013_2023", "smb_2024")],
                   ["date_arrete"])
    lois = _empiler([lire_lois(fichiers[k], codes).assign(source=k) for k in ("lois_2013_2023", "lois_2024")],
                    ["annee", "texte_code"])
    eurostat = {cle: lire_jsonstat(fichiers[cle]).rename(columns={"time": "annee"}).astype({"annee": int})
                for cle in ("eurostat_apu", "eurostat_impots", "eurostat_cofog")}
    sources = pd.DataFrame([{**vars(s), "fichier": fichiers[s.cle].name} for s in SOURCES])
    journal = pd.read_csv(JOURNAL) if JOURNAL.exists() else pd.DataFrame(columns=COLONNES_JOURNAL)

    chemin_base.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin_base.with_suffix(".tmp")
    temporaire.unlink(missing_ok=True)
    con = duckdb.connect(str(temporaire))
    try:
        for nom, df in [("ref_lignes", ref),
                        ("ref_administrations", pd.read_csv(REF_DIR / "administrations.csv")),
                        ("ref_fonctions", pd.read_csv(REF_DIR / "fonctions_cofog.csv")),
                        ("stg_smb", smb), ("stg_lois", lois),
                        ("stg_eurostat", eurostat["eurostat_apu"]),
                        ("stg_eurostat_impots", eurostat["eurostat_impots"]),
                        ("stg_eurostat_cofog", eurostat["eurostat_cofog"]),
                        ("meta_sources", sources), ("meta_collectes", journal)]:
            _creer(con, nom, df)

        parquet = str(fichiers["compta_generale"]).replace("'", "''")
        con.execute(f"""
            CREATE TABLE stg_compta_generale AS
            SELECT
                year(annee)             AS annee,
                categorie,
                postes                  AS poste,
                sous_postes             AS sous_poste,
                indicateurs_de_synthese AS indicateur_synthese,
                indicateurs_de_detail   AS indicateur_detail,
                mission                 AS code_mission,
                libellemission          AS mission,
                programme,
                libelle_ministere       AS ministere,
                compte,
                nature_budgetaire,
                balance_sortie          AS solde
            FROM read_parquet('{parquet}')
        """)

        con.execute((SQL_DIR / "vues.sql").read_text(encoding="utf-8"))
        _creer(con, "meta_controles", executer_controles(con))
        con.execute("CREATE TABLE meta_construction AS SELECT current_localtimestamp() AS construite_le")
    finally:
        con.close()

    try:
        os.replace(temporaire, chemin_base)
    except PermissionError as e:
        raise RuntimeError(
            f"Impossible de remplacer {chemin_base} : fichier verrouillé par un autre programme "
            "(client SQL, DBeaver…). Fermez-le puis relancez."
        ) from e
    return chemin_base
