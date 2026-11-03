import pandas as pd
import pytest

from finances_etat.config import REF_DIR

DISPOSITIFS_SOCLE_PUBLIES = 405


@pytest.fixture(scope="module")
def aides() -> pd.DataFrame:
    return pd.read_csv(REF_DIR / "aides_entreprises.csv", dtype={"numero": str})


def test_referentiel_complet(aides):
    assert (aides["perimetre"] == "P1").sum() == DISPOSITIFS_SOCLE_PUBLIES
    assert aides["perimetre"].isin(["P1", "P2"]).all()
    assert not aides.duplicated(["annee", "dispositif", "rattachement"]).any()


def test_somme_des_lignes_egale_total_publie(aides):
    totaux = pd.read_csv(REF_DIR / "aides_entreprises_totaux.csv").set_index(["instrument", "perimetre"])["montant_md"]
    assert aides["montant_m"].sum() / 1e3 == pytest.approx(totaux[("ensemble", "elargi")], abs=0.05)


def test_montant_vide_seulement_si_la_source_ne_chiffre_pas(aides):
    assert set(aides.loc[aides["montant_m"].isna(), "montant_source"]) <= {"ε", "nc", "-"}
