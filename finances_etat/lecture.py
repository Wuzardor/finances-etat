"""Lecture des fichiers bruts et mise au format long (une ligne = une valeur).

Particularités des CSV DGFiP gérées ici : encodage UTF-16, fichier parfois
compressé en gzip sans le signaler, séparateur « ; », virgule décimale,
colonnes vides en fin de ligne, lignes vides intercalées.
"""

import csv
import gzip
import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .texte import cle_libelle

NB_COLONNES_LIBELLE = 5  # niveau, type de niveau, catégorie, sous-catégorie, ligne


def lire_texte(chemin: Path) -> str:
    brut = Path(chemin).read_bytes()
    if brut[:2] == b"\x1f\x8b":
        brut = gzip.decompress(brut)
    if brut[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return brut.decode("utf-16")
    try:
        return brut.decode("utf-8-sig")
    except UnicodeDecodeError:
        return brut.decode("cp1252")


def lire_csv(chemin: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(lire_texte(chemin)), delimiter=";"))


def nombre(s: str) -> float | None:
    s = s.strip().replace(" ", "").replace(" ", "").replace(",", ".")
    return float(s) if s else None


def _colonnes_valeurs(entete: list[str], debut: int) -> list[tuple[int, str]]:
    return [(i, c.strip()) for i, c in enumerate(entete) if i >= debut and c.strip()]


def _libelles(ligne: list[str], codes: dict[str, str]) -> dict:
    libelle = ligne[4].strip()
    return {
        "code": codes.get(cle_libelle(libelle)),
        "categorie": ligne[2].strip(),
        "sous_categorie": ligne[3].strip(),
        "libelle_source": libelle,
    }


def lire_smb(chemin: Path, codes: dict[str, str]) -> pd.DataFrame:
    """Situations mensuelles budgétaires : montants cumulés depuis le 1er janvier, par date d'arrêté."""
    entete, *lignes = lire_csv(chemin)
    dates = [(i, datetime.strptime(c, "%d/%m/%Y").date())
             for i, c in _colonnes_valeurs(entete, NB_COLONNES_LIBELLE)]
    enregistrements = []
    for ligne in lignes:
        if len(ligne) <= NB_COLONNES_LIBELLE or not ligne[4].strip():
            continue
        libelles = _libelles(ligne, codes)
        for i, date_arrete in dates:
            valeur = nombre(ligne[i]) if i < len(ligne) else None
            if valeur is not None:
                enregistrements.append({**libelles, "date_arrete": date_arrete, "cumul": valeur})
    return pd.DataFrame(enregistrements)


def code_texte(texte: str) -> str:
    """LFI → lfi ; « Dernière LFR » ou « Dernière LFR/LFG » → lfr ; « Exécution » → execution."""
    cle = cle_libelle(texte)
    if cle.startswith("derniere lfr"):
        return "lfr"
    if cle.startswith("execution"):
        return "execution"
    return cle


def lire_lois(chemin: Path, codes: dict[str, str]) -> pd.DataFrame:
    """Montants annuels par texte : LFI, dernière LFR/LFG, exécution."""
    entete, *lignes = lire_csv(chemin)
    annees = [(i, int(c)) for i, c in _colonnes_valeurs(entete, NB_COLONNES_LIBELLE + 1)]
    enregistrements = []
    for ligne in lignes:
        if len(ligne) <= NB_COLONNES_LIBELLE or not ligne[4].strip():
            continue
        libelles = _libelles(ligne, codes)
        texte = ligne[NB_COLONNES_LIBELLE].strip()
        for i, annee in annees:
            valeur = nombre(ligne[i]) if i < len(ligne) else None
            if valeur is not None:
                enregistrements.append({**libelles, "annee": annee, "texte": texte,
                                        "texte_code": code_texte(texte), "montant": valeur})
    return pd.DataFrame(enregistrements)


def lire_jsonstat(chemin: Path) -> pd.DataFrame:
    """Format JSON-stat 2.0 d'Eurostat : cube aplati, une colonne par dimension."""
    d = json.loads(lire_texte(chemin))
    dimensions, tailles = d["id"], d["size"]
    positions = []
    for dim in dimensions:
        index = d["dimension"][dim]["category"]["index"]
        if isinstance(index, list):
            index = {code: pos for pos, code in enumerate(index)}
        positions.append({pos: code for code, pos in index.items()})

    enregistrements = []
    for k, valeur in d["value"].items():
        k, coord = int(k), []
        for taille in reversed(tailles):
            coord.append(k % taille)
            k //= taille
        coord.reverse()
        enregistrements.append(
            {dim: positions[n][c] for n, (dim, c) in enumerate(zip(dimensions, coord))} | {"valeur": valeur}
        )
    return pd.DataFrame(enregistrements)
