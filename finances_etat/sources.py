"""Catalogue des sources open data utilisées.

Les pièces jointes Opendatasoft sont repérées par un motif sur leur titre plutôt
que par leur identifiant : la DGFiP remplace régulièrement les fichiers (le
fichier « 2024-xx » grossit chaque mois) et l'identifiant peut changer.
"""

from dataclasses import dataclass

ODS_API = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets"
ODS_PAGE = "https://data.economie.gouv.fr/explore/dataset"
SMB_DATASET = "situations-mensuelles-budgetaires-series-longues"
COMPTA_DATASET = "balances_des_comptes_etat"
EUROSTAT_API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


@dataclass(frozen=True)
class Source:
    cle: str
    titre: str
    producteur: str
    page: str
    extension: str
    url: str | None = None
    dataset: str | None = None
    motif_piece_jointe: str | None = None  # regex sur le titre, sans accents, en minuscules


SOURCES: list[Source] = [
    Source(
        cle="smb_2013_2023",
        titre="Situations mensuelles budgétaires de l'État, 2013-2023 (cumuls mensuels)",
        producteur="DGFiP",
        page=f"{ODS_PAGE}/{SMB_DATASET}/",
        extension="csv",
        dataset=SMB_DATASET,
        motif_piece_jointe=r"series? longues? smb.*2013",
    ),
    Source(
        cle="smb_2024",
        titre="Situations mensuelles budgétaires de l'État, 2024 à aujourd'hui (cumuls mensuels)",
        producteur="DGFiP",
        page=f"{ODS_PAGE}/{SMB_DATASET}/",
        extension="csv",
        dataset=SMB_DATASET,
        motif_piece_jointe=r"series? longues? smb.*2024",
    ),
    Source(
        cle="lois_2013_2023",
        titre="Lois de finances (LFI, dernière LFR) et exécution annuelle, 2013-2023",
        producteur="DGFiP",
        page=f"{ODS_PAGE}/{SMB_DATASET}/",
        extension="csv",
        dataset=SMB_DATASET,
        motif_piece_jointe=r"textes legislatifs.*2013",
    ),
    Source(
        cle="lois_2024",
        titre="Lois de finances (LFI, dernière LFR/LFG) et exécution annuelle, 2024 à aujourd'hui",
        producteur="DGFiP",
        page=f"{ODS_PAGE}/{SMB_DATASET}/",
        extension="csv",
        dataset=SMB_DATASET,
        motif_piece_jointe=r"textes legislatifs.*2024",
    ),
    Source(
        cle="compta_generale",
        titre="Balances de la comptabilité générale de l'État (bilan, compte de résultat), 2016-2025",
        producteur="DGFiP",
        page=f"{ODS_PAGE}/{COMPTA_DATASET}/",
        extension="parquet",
        url=f"{ODS_API}/{COMPTA_DATASET}/exports/parquet",
    ),
    Source(
        cle="eurostat_apu",
        titre="Déficit et dette publics au sens de Maastricht (toutes administrations publiques)",
        producteur="Eurostat",
        page="https://ec.europa.eu/eurostat/databrowser/view/gov_10dd_edpt1/default/table",
        extension="json",
        url=(
            f"{EUROSTAT_API}/gov_10dd_edpt1?geo=FR&sector=S13&na_item=B9&na_item=GD"
            "&unit=PC_GDP&unit=MIO_EUR&format=JSON&lang=fr"
        ),
    ),
    Source(
        cle="eurostat_impots",
        titre="Impôts et cotisations sociales par administration bénéficiaire (comptabilité nationale)",
        producteur="Eurostat",
        page="https://ec.europa.eu/eurostat/databrowser/view/gov_10a_taxag/default/table",
        extension="json",
        url=(
            f"{EUROSTAT_API}/gov_10a_taxag?geo=FR&unit=MIO_EUR&sinceTimePeriod=2010"
            "&sector=S13&sector=S1311&sector=S1313&sector=S1314&sector=S212"
            + "".join(f"&na_item={i}" for i in (
                "D21", "D211", "D214", "D214A", "D29", "D29A", "D51A", "D51B", "D59", "D91",
                "D611C", "D613C", "D2_D5_D91", "D2_D5_D91_D61_M_D611V_D612_M_M_D613V_D614_M_D995"))
            + "&format=JSON&lang=fr"
        ),
    ),
    Source(
        cle="eurostat_cofog",
        titre="Dépenses publiques par fonction (COFOG) et par administration",
        producteur="Eurostat",
        page="https://ec.europa.eu/eurostat/databrowser/view/gov_10a_exp/default/table",
        extension="json",
        url=(
            f"{EUROSTAT_API}/gov_10a_exp?geo=FR&unit=MIO_EUR&na_item=TE&sinceTimePeriod=2010"
            "&sector=S13&sector=S1311&sector=S1313&sector=S1314"
            + "".join(f"&cofog99=GF{i:02d}" for i in range(1, 11))
            + "&cofog99=TOTAL&format=JSON&lang=fr"
        ),
    ),
]

SOURCES_PAR_CLE = {s.cle: s for s in SOURCES}
