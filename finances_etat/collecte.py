"""Téléchargement des fichiers bruts.

Chaque fichier est conservé tel quel dans data/raw/<source>/<date>.<ext>.
Un nouveau fichier n'est écrit que si son contenu a changé (empreinte SHA-256) :
on garde ainsi l'historique des versions publiées, sans doublons.
"""

import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

from .config import RAW_DIR
from .sources import ODS_API, Source
from .texte import sans_accents

JOURNAL = RAW_DIR / "journal.csv"
TIMEOUT = 120
USER_AGENT = "finances-etat/0.1 (suivi open data des finances de l'Etat)"


@dataclass
class Telechargement:
    source: str
    url: str
    fichier: Path
    sha256: str
    octets: int
    nouveau: bool
    horodatage: datetime


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def resoudre_url(src: Source, http: requests.Session) -> str:
    if src.url:
        return src.url
    meta = http.get(f"{ODS_API}/{src.dataset}", timeout=TIMEOUT)
    meta.raise_for_status()
    pieces = meta.json().get("attachments", [])
    motif = re.compile(src.motif_piece_jointe)
    trouvees = [p for p in pieces if motif.search(sans_accents(p["title"]).lower())]
    if len(trouvees) != 1:
        titres = [p["title"] for p in pieces]
        raise RuntimeError(
            f"{src.cle} : {len(trouvees)} pièce(s) jointe(s) correspondent à "
            f"/{src.motif_piece_jointe}/ dans {src.dataset}. Disponibles : {titres}"
        )
    return trouvees[0]["url"]


def dernier_fichier(cle: str) -> Path | None:
    fichiers = sorted((RAW_DIR / cle).glob("*.*"))
    return fichiers[-1] if fichiers else None


def telecharger(src: Source, http: requests.Session) -> Telechargement:
    url = resoudre_url(src, http)
    rep = http.get(url, timeout=TIMEOUT)
    rep.raise_for_status()
    contenu = rep.content
    sha = hashlib.sha256(contenu).hexdigest()
    maintenant = datetime.now()

    precedent = dernier_fichier(src.cle)
    if precedent and hashlib.sha256(precedent.read_bytes()).hexdigest() == sha:
        return Telechargement(src.cle, url, precedent, sha, len(contenu), False, maintenant)

    dossier = RAW_DIR / src.cle
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / f"{maintenant:%Y%m%d-%H%M%S}.{src.extension}"
    fichier.write_bytes(contenu)
    return Telechargement(src.cle, url, fichier, sha, len(contenu), True, maintenant)


def journaliser(t: Telechargement) -> None:
    """Journal des collectes, conservé avec les fichiers bruts (la base est reconstruite à chaque fois)."""
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    nouveau_journal = not JOURNAL.exists()
    with JOURNAL.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nouveau_journal:
            w.writerow(["horodatage", "source", "url", "fichier", "sha256", "octets", "nouveau"])
        w.writerow([t.horodatage.isoformat(timespec="seconds"), t.source, t.url,
                    t.fichier.name, t.sha256, t.octets, t.nouveau])
