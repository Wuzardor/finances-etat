"""Contrôles de cohérence, exécutés à chaque construction de la base.

Ils ne bloquent pas le chargement : les résultats sont enregistrés dans
meta_controles et affichés dans l'onglet « Qualité » du tableau de bord.
Statuts : ok, alerte, ou connue (anomalie de la source déjà analysée,
documentée dans ref/anomalies_connues.csv).
"""

import duckdb
import pandas as pd

from .config import REF_DIR

TOLERANCE_EUROS = 1e6  # écarts d'arrondi admis sur les agrégats publiés

TITRES = ["dep_t1_pouvoirs_publics", "dep_t2_personnel", "dep_t3_fonctionnement", "dep_t4_charge_dette",
          "dep_t5_investissement", "dep_t6_intervention", "dep_t7_operations_financieres"]
SOLDE_HORS_FDC = {"rec_bg_nettes": 1, "dep_bg_total": -1, "psr_total": -1,
                  "solde_comptes_speciaux": 1, "solde_budgets_annexes": 1}

# (code, libellé, ligne totale, composantes et signes)
IDENTITES = [
    ("recettes_fiscales", "Recettes fiscales = IR + IS + TVA + TICPE + autres", "rec_fiscales",
     {"rec_ir": 1, "rec_is": 1, "rec_tva": 1, "rec_ticpe": 1, "rec_autres_fiscales": 1}),
    ("recettes_nettes", "Recettes nettes = fiscales + non fiscales", "rec_bg_nettes",
     {"rec_fiscales": 1, "rec_non_fiscales": 1}),
    ("depenses_titres", "Dépenses du budget général = somme des titres 1 à 7", "dep_bg_total",
     {t: 1 for t in TITRES}),
    ("psr", "Prélèvements sur recettes = collectivités + Union européenne", "psr_total",
     {"psr_collectivites": 1, "psr_ue": 1}),
]
# En exécution, les dépenses incluent celles financées par fonds de concours : il faut
# ajouter ces recettes pour retrouver le solde. En LFI/LFR, elles ne sont pas votées.
IDENTITE_SOLDE_EXECUTION = (
    "solde", "Solde = recettes + fonds de concours − dépenses − PSR + comptes spéciaux + budgets annexes",
    "solde_budgetaire", {**SOLDE_HORS_FDC, "rec_fonds_concours": 1})
IDENTITE_SOLDE_PREVISION = (
    "solde", "Solde = recettes − dépenses − PSR + comptes spéciaux + budgets annexes",
    "solde_budgetaire", SOLDE_HORS_FDC)


def _identites(large: pd.DataFrame, jeu: str, identites: list) -> list[dict]:
    resultats = []
    for code, nom, total, composantes in identites:
        colonnes = [total, *composantes]
        if not set(colonnes) <= set(large.columns):
            continue
        sous = large[colonnes].dropna()
        ecarts = sous[total] - sum(signe * sous[c] for c, signe in composantes.items())
        resultats += [{"jeu": jeu, "code": code, "controle": nom, "periode": str(p), "ecart": float(e),
                       "unite": "€", "tolerance": TOLERANCE_EUROS} for p, e in ecarts.items()]
    return resultats


def _mois_manquants(con: duckdb.DuckDBPyConnection) -> list[dict]:
    mois = con.sql("SELECT DISTINCT year(date_arrete) AS a, month(date_arrete) AS m FROM stg_smb").df()
    derniere = mois["a"].max()
    resultats = []
    for annee, groupe in mois.groupby("a"):
        attendus = set(range(1, (groupe["m"].max() if annee == derniere else 12) + 1))
        manquants = sorted(attendus - set(groupe["m"]))
        resultats.append({"jeu": "smb", "code": "mois_manquants", "controle": "Aucun mois manquant",
                          "periode": str(annee), "ecart": float(len(manquants)),
                          "unite": "mois", "tolerance": 0.0,
                          "detail": ", ".join(map(str, manquants)) or None})
    return resultats


def executer_controles(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    r: list[dict] = []

    smb = con.sql("SELECT date_arrete, code, cumul FROM stg_smb WHERE code IS NOT NULL").df()
    r += _identites(smb.pivot(index="date_arrete", columns="code", values="cumul"), "smb",
                    [*IDENTITES, IDENTITE_SOLDE_EXECUTION])

    lois = con.sql("SELECT annee, texte_code, code, montant FROM stg_lois WHERE code IS NOT NULL").df()
    for texte, solde in [("lfi", IDENTITE_SOLDE_PREVISION), ("lfr", IDENTITE_SOLDE_PREVISION),
                         ("execution", IDENTITE_SOLDE_EXECUTION)]:
        large = lois[lois["texte_code"] == texte].pivot(index="annee", columns="code", values="montant")
        r += _identites(large, texte, [*IDENTITES, solde])

    for annee, code, ecart in con.sql("""
        SELECT l.annee, l.code, l.montant - m.cumul
        FROM stg_lois l
        JOIN v_execution_mensuelle m ON m.code = l.code AND m.annee = l.annee AND m.mois = 12
        WHERE l.texte_code = 'execution'
    """).fetchall():
        r.append({"jeu": "execution_vs_smb", "code": "execution_vs_smb",
                  "controle": "Exécution annuelle identique au cumul de décembre des SMB",
                  "periode": str(annee), "ecart": ecart, "unite": "€", "tolerance": TOLERANCE_EUROS,
                  "detail": code})

    for annee, ecart in con.sql("SELECT annee, sum(solde) FROM stg_compta_generale GROUP BY annee").fetchall():
        r.append({"jeu": "compta", "code": "balance_equilibree",
                  "controle": "Balance équilibrée (total des débits = total des crédits)",
                  "periode": str(annee), "ecart": ecart, "unite": "€", "tolerance": TOLERANCE_EUROS})

    for annee, ecart in con.sql("""
        SELECT v.annee, v.impots - t.valeur * 1e6
        FROM (SELECT annee, sum(montant) AS impots FROM v_prelevements
              WHERE administration <> 'Union européenne' AND prelevement <> 'Cotisations sociales'
              GROUP BY annee) v
        JOIN stg_eurostat_impots t ON t.annee = v.annee AND t.sector = 'S13' AND t.na_item = 'D2_D5_D91'
    """).fetchall():
        r.append({"jeu": "eurostat", "code": "prelevements_total",
                  "controle": "Somme des catégories d'impôts = total des impôts des administrations",
                  "periode": str(annee), "ecart": ecart, "unite": "€", "tolerance": 0.5e9})

    for annee, administration, ecart in con.sql("""
        SELECT f.annee, f.administration, f.total - t.valeur * 1e6
        FROM (SELECT annee, administration, sum(montant) AS total FROM v_depenses_fonction GROUP BY ALL) f
        JOIN ref_administrations a USING (administration)
        JOIN stg_eurostat_cofog t ON t.annee = f.annee AND t.sector = a.sector AND t.cofog99 = 'TOTAL'
    """).fetchall():
        r.append({"jeu": "eurostat", "code": "cofog_total",
                  "controle": "Somme des fonctions = total des dépenses de l'administration",
                  "periode": str(annee), "ecart": ecart, "unite": "€", "tolerance": 0.5e9,
                  "detail": administration})

    r += _mois_manquants(con)

    for jeu, table in [("smb", "stg_smb"), ("lois", "stg_lois")]:
        inconnus = con.sql(f"SELECT DISTINCT libelle_source FROM {table} WHERE code IS NULL").fetchall()
        r.append({"jeu": jeu, "code": "libelles_references",
                  "controle": "Tous les libellés sont référencés dans ref/lignes_budget.csv",
                  "periode": "toutes", "ecart": float(len(inconnus)), "unite": "libellés", "tolerance": 0.0,
                  "detail": " | ".join(lib for (lib,) in inconnus) or None})

    df = pd.DataFrame(r)
    df["statut"] = (df["ecart"].abs() <= df["tolerance"]).map({True: "ok", False: "alerte"})

    connues = pd.read_csv(REF_DIR / "anomalies_connues.csv", dtype=str)
    df = df.merge(connues, on=["jeu", "code", "periode"], how="left")
    df.loc[(df["statut"] == "alerte") & df["explication"].notna(), "statut"] = "connue"
    return df
