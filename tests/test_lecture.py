import gzip
import json
from datetime import date

import pandas as pd
import pytest

from finances_etat.controles import IDENTITES, _identites
from finances_etat.lecture import code_texte, lire_jsonstat, lire_lois, lire_smb, nombre
from finances_etat.texte import cle_libelle

CODES = {cle_libelle("Solde budgétaire"): "solde_budgetaire",
         cle_libelle("Charges de la dette de l'Etat"): "dep_t4_charge_dette"}

ENTETE = "Niveau hiérarchique;Niveau hiérarchique de la ligne;Catégorie;Sous-catégorie;Ligne d'information"


def ecrire_dgfip(chemin, texte: str, compresser: bool = False):
    """Reproduit le format DGFiP : UTF-16 avec BOM, parfois compressé en gzip."""
    brut = texte.replace("\n", "\r\n").encode("utf-16")
    chemin.write_bytes(gzip.compress(brut) if compresser else brut)
    return chemin


def test_nombre_virgule_decimale_et_vide():
    assert nombre("-25741980707,95") == -25741980707.95
    assert nombre(" 1 137 842 143 ") == 1137842143
    assert nombre("") is None


def test_cle_libelle_unifie_apostrophes_accents_et_espaces():
    assert cle_libelle("Charges de la dette de l’Etat  ") == cle_libelle("Charges de la dette de l'État")


@pytest.mark.parametrize("compresser", [False, True])
def test_lire_smb_format_long(tmp_path, compresser):
    chemin = ecrire_dgfip(tmp_path / "smb.csv", "\n".join([
        f"{ENTETE};31/01/2024;29/02/2024;;",
        "0;Nul;Solde budgétaire;Solde budgétaire;Solde budgétaire;-25741980707,95;-44031786980,67;;",
        ";;;;;;;;",
        "2;Sous-total;Dépenses;Budget général;Charges de la dette de l’Etat  ;1000;;;",
        "2;Sous-total;Dépenses;Budget général;Ligne inconnue;5;6;;",
    ]), compresser)
    df = lire_smb(chemin, CODES)

    assert len(df) == 5  # la valeur vide de février n'est pas créée
    solde = df[df["code"] == "solde_budgetaire"].sort_values("date_arrete")
    assert solde["date_arrete"].tolist() == [date(2024, 1, 31), date(2024, 2, 29)]
    assert solde["cumul"].tolist() == [-25741980707.95, -44031786980.67]
    assert df.loc[df["libelle_source"] == "Charges de la dette de l’Etat", "code"].iloc[0] == "dep_t4_charge_dette"
    assert df.loc[df["libelle_source"] == "Ligne inconnue", "code"].isna().all()


def test_lire_lois_code_des_textes(tmp_path):
    chemin = ecrire_dgfip(tmp_path / "lois.csv", "\n".join([
        f"{ENTETE};Texte législatif;2024;2025; ; ",
        "0;Nul;Solde budgétaire;Solde budgétaire;Solde budgétaire;LFI;-146891455306,548;-138995864047,872",
        "0;Nul;Solde budgétaire;Solde budgétaire;Solde budgétaire;Dernière LFR/LFG;-168790047566,387;-133063696693",
        "0;Nul;Solde budgétaire;Solde budgétaire;Solde budgétaire;Exécution;-155929972365,41;-124205673501,55",
    ]))
    df = lire_lois(chemin, CODES)
    assert sorted(df["texte_code"].unique()) == ["execution", "lfi", "lfr"]
    assert df.set_index(["annee", "texte_code"]).loc[(2025, "execution"), "montant"] == -124205673501.55


def test_code_texte():
    assert code_texte("Dernière LFR") == "lfr"
    assert code_texte("Dernière LFR/LFG") == "lfr"
    assert code_texte("Exécution") == "execution"
    assert code_texte("LFI") == "lfi"


def test_lire_jsonstat(tmp_path):
    cube = {
        "id": ["unit", "time"], "size": [2, 2],
        "dimension": {"unit": {"category": {"index": {"PC_GDP": 0, "MIO_EUR": 1}}},
                      "time": {"category": {"index": {"2023": 0, "2024": 1}}}},
        "value": {"0": -5.4, "1": -5.8, "3": -169100.0},  # valeur manquante à l'index 2
    }
    chemin = tmp_path / "cube.json"
    chemin.write_text(json.dumps(cube), encoding="utf-8")
    df = lire_jsonstat(chemin).set_index(["unit", "time"])["valeur"]
    assert df[("PC_GDP", "2024")] == -5.8
    assert df[("MIO_EUR", "2024")] == -169100.0
    assert ("MIO_EUR", "2023") not in df.index


def test_identite_detecte_un_ecart():
    large = pd.DataFrame({"psr_total": [69.0, 70.0], "psr_collectivites": [46.0, 46.0], "psr_ue": [23.0, 23.0]},
                         index=[2024, 2025])
    psr = [i for i in IDENTITES if i[0] == "psr"]
    ecarts = {r["periode"]: r["ecart"] for r in _identites(large, "test", psr)}
    assert ecarts == {"2024": 0.0, "2025": 1.0}
