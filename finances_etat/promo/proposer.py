"""Choix des posts du jour : écrit un fichier par post proposé, transformé en ticket GitHub à valider.

    uv run --group promo python -m finances_etat.promo.proposer --sortie data/propositions --en-attente 2

Règles :
- le fil de lancement est proposé une seule fois, avant tout le reste ;
- le point mensuel est proposé dès qu'une nouvelle situation mensuelle est parue ;
- le lundi et le jeudi, un post thématique, s'il y a moins de 3 posts en attente. Un modèle
  n'est reproposé que si ses données ont changé (et au moins 4 semaines après), ou au bout de 6 mois.
Les visuels retenus sont rangés dans promo/visuels et chaque proposition inscrite dans promo/journal.csv.
"""

import argparse
import csv
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import duckdb

from ..config import DB_PATH, ROOT
from .posts import CATALOGUE, Post, lancement, point_mensuel
from .publier import MARQUEUR_FIN, longueur_x

JOURNAL = ROOT / "promo" / "journal.csv"
CHEMIN_VISUELS = "promo/visuels"  # dans le dépôt : les tickets affichent les visuels depuis GitHub
VISUELS = ROOT / CHEMIN_VISUELS
JOURS_THEMATIQUES = {0, 3}  # lundi, jeudi
MAX_EN_ATTENTE = 3
DELAI_NOUVELLES_DONNEES = timedelta(weeks=4)
DELAI_RAPPEL = timedelta(weeks=26)
DEPOT = os.environ.get("GITHUB_REPOSITORY", "Wuzardor/finances-etat")

CONSIGNES = """___
**Publier** : ajoute l'étiquette `valide`. Le post partira au prochain créneau (du lundi au vendredi, vers 8 h 30 et 18 h 30).
**Modifier** : menu ⋯ → *Edit*, change le texte au-dessus du trait, puis ajoute `valide`. Dans un fil, une ligne `---` sépare deux posts.
**Refuser** : ferme le ticket.

Longueur pour X : {longueurs} (280 au plus ; €, … et → comptent double)."""


def lire_journal(chemin: Path) -> list[dict]:
    if not chemin.exists():
        return []
    with chemin.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def inscrire(lignes: list[dict], chemin: Path) -> None:
    if not lignes:
        return
    nouveau = not chemin.exists()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["date", "modele", "cle"], lineterminator="\n")
        if nouveau:
            w.writeheader()
        w.writerows(lignes)


def dernieres(journal: list[dict]) -> dict[str, tuple[date, str]]:
    """Dernière proposition de chaque modèle : (date, clé)."""
    resultat = {}
    for ligne in journal:
        resultat[ligne["modele"]] = (date.fromisoformat(ligne["date"]), ligne["cle"])
    return resultat


def thematique(con, jour: date, journal: list[dict], dossier: Path) -> Post | None:
    """Le modèle proposé depuis le plus longtemps (jamais proposé d'abord), s'il a quelque chose de neuf."""
    passe = dernieres(journal)
    ordre = sorted(range(len(CATALOGUE)), key=lambda i: (CATALOGUE[i].__name__ in passe,
                                                         passe.get(CATALOGUE[i].__name__, (date.min,))[0], i))
    for i in ordre:
        modele = CATALOGUE[i]
        derniere = passe.get(modele.__name__)
        if derniere and jour - derniere[0] < DELAI_NOUVELLES_DONNEES:
            continue
        post = modele(con, dossier, jour)
        if post is None:
            continue
        if derniere is None or post.cle != derniere[1] or jour - derniere[0] >= DELAI_RAPPEL:
            return post
    return None


def choisir(con, jour: date, journal: list[dict], en_attente: int, dossier: Path) -> list[Post]:
    passe = dernieres(journal)
    if "lancement" not in passe:
        return [lancement(con, dossier, jour)]
    posts = []
    mois = con.sql("SELECT strftime(max(date_arrete), '%Y-%m') FROM stg_smb").fetchone()[0]
    if passe.get("point_mensuel", (None, None))[1] != mois:
        posts.append(point_mensuel(con, dossier, jour))
    if jour.weekday() in JOURS_THEMATIQUES and en_attente + len(posts) < MAX_EN_ATTENTE:
        post = thematique(con, jour, journal, dossier)
        if post:
            posts.append(post)
    return posts


def corps_ticket(post: Post, depot: str = DEPOT) -> str:
    blocs = []
    for p in post.parties:
        bloc = p.texte
        if p.image:
            bloc += f"\n\n![{p.alt}](https://raw.githubusercontent.com/{depot}/main/{CHEMIN_VISUELS}/{p.image.name})"
        blocs.append(bloc)
    longueurs = " · ".join(f"post {i} : {longueur_x(p.texte)}" for i, p in enumerate(post.parties, 1))
    return "\n\n---\n\n".join(blocs) + f"\n\n{MARQUEUR_FIN}\n\n" + CONSIGNES.format(longueurs=longueurs)


def proposer(con, jour: date, en_attente: int, sortie: Path) -> list[Path]:
    journal = lire_journal(JOURNAL)
    with tempfile.TemporaryDirectory() as brouillons:
        posts = choisir(con, jour, journal, en_attente, Path(brouillons))
        for post in posts:  # seuls les visuels des posts retenus rejoignent le dépôt
            for p in post.parties:
                if p.image:
                    VISUELS.mkdir(parents=True, exist_ok=True)
                    p.image = Path(shutil.move(p.image, VISUELS / p.image.name))
    sortie.mkdir(parents=True, exist_ok=True)
    fichiers = []
    for i, post in enumerate(posts, 1):
        fichier = sortie / f"{i}-{post.modele}.md"
        fichier.write_text(f"Post X : {post.titre}\n\n{corps_ticket(post)}\n", encoding="utf-8")
        fichiers.append(fichier)
    inscrire([{"date": jour.isoformat(), "modele": m, "cle": c}
              for post in posts for m, c in [(post.modele, post.cle), *post.inclus]], JOURNAL)
    return fichiers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finances_etat.promo.proposer", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sortie", type=Path, required=True, help="dossier où écrire les propositions")
    parser.add_argument("--en-attente", type=int, default=0, help="posts déjà en attente de validation")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="date du jour (AAAA-MM-JJ)")
    args = parser.parse_args(argv)
    for flux in (sys.stdout, sys.stderr):
        flux.reconfigure(encoding="utf-8")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        fichiers = proposer(con, args.date, args.en_attente, args.sortie)
    finally:
        con.close()
    for fichier in fichiers:
        print(f"Proposé : {fichier.read_text(encoding='utf-8').splitlines()[0]}")
    if not fichiers:
        print("Rien à proposer aujourd'hui.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
