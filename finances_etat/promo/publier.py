"""Publication sur X d'un post validé, à partir du texte de son ticket GitHub.

    uv run --group promo python -m finances_etat.promo.publier corps.md           # publie, affiche le lien
    uv run --group promo python -m finances_etat.promo.publier corps.md --essai   # vérifie sans publier

Le ticket contient les posts du fil séparés par une ligne « --- ». Tout ce qui suit le
marqueur de fin (les consignes de validation) est ignoré. Les images doivent être des
visuels du dépôt (promo/visuels) : on ne publie jamais une image venue d'ailleurs.
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from ..config import ROOT

API = "https://api.x.com/2"
LIMITE = 280
MARQUEUR_FIN = "<!-- fin du post : rien de ce qui suit n'est publié -->"
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
IMAGE_DU_DEPOT = re.compile(r"https://raw\.githubusercontent\.com/[^/]+/[^/]+/[^/]+/(promo/visuels/[\w.\-]+\.png)")
URL = re.compile(r"https?://\S+")
CLES = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")


@dataclass
class PartieLue:
    texte: str
    images: list[tuple[Path, str]]  # (fichier, texte alternatif)


def longueur_x(texte: str) -> int:
    """Longueur au sens de X : un lien compte 23 caractères, la plupart des caractères latins 1,
    les autres 2 (dont €, …, → et les émojis)."""
    longueur = 23 * len(URL.findall(texte))
    for c in URL.sub("", texte):
        n = ord(c)
        simple = n <= 4351 or 8192 <= n <= 8205 or 8208 <= n <= 8223 or 8242 <= n <= 8247
        longueur += 1 if simple else 2
    return longueur


def lire_ticket(corps: str, racine: Path = ROOT) -> list[PartieLue]:
    corps = corps.replace("\r\n", "\n").split(MARQUEUR_FIN)[0]
    parties = []
    for bloc in re.split(r"^\s*---\s*$", corps, flags=re.M):
        images = []
        for alt, url in IMAGE.findall(bloc):
            trouve = IMAGE_DU_DEPOT.fullmatch(url)
            if not trouve:
                raise ValueError(f"Image refusée (seuls les visuels du dépôt sont publiés) : {url}")
            chemin = racine / trouve.group(1)
            if not chemin.exists():
                raise ValueError(f"Image introuvable dans le dépôt : {trouve.group(1)}")
            images.append((chemin, alt))
        texte = re.sub(r"\n{3,}", "\n\n", IMAGE.sub("", bloc)).strip()
        if texte or images:
            parties.append(PartieLue(texte, images))
    return parties


def verifier(parties: list[PartieLue]) -> None:
    if not parties:
        raise ValueError("Le ticket ne contient aucun post.")
    for i, p in enumerate(parties, 1):
        if longueur_x(p.texte) > LIMITE:
            raise ValueError(f"Post {i} trop long : {longueur_x(p.texte)} caractères pour X, {LIMITE} au plus.")
        if len(p.images) > 4:
            raise ValueError(f"Post {i} : 4 images au plus.")


def session_x():
    cles = [os.environ.get(k) for k in CLES]
    if not all(cles):
        raise RuntimeError("Clés de l'API X absentes : ajoutez les secrets " + ", ".join(CLES)
                           + " dans GitHub (Settings → Secrets and variables → Actions).")
    from requests_oauthlib import OAuth1Session
    return OAuth1Session(*cles)


def _reponse(r, action: str) -> dict:
    if r.status_code >= 400:
        raise RuntimeError(f"{action} : erreur {r.status_code} de l'API X : {r.text[:500]}")
    return r.json()["data"]


def televerser(http, chemin: Path, alt: str) -> str:
    with chemin.open("rb") as f:
        media = _reponse(http.post(f"{API}/media/upload", files={"media": (chemin.name, f, "image/png")},
                                   data={"media_category": "tweet_image"}, timeout=60), "Envoi de l'image")
    if alt:
        _reponse(http.post(f"{API}/media/metadata", timeout=30,
                           json={"id": media["id"], "metadata": {"alt_text": {"text": alt[:1000]}}}),
                 "Texte alternatif")
    return media["id"]


def publier(parties: list[PartieLue], http) -> list[str]:
    """Publie le fil, chaque post en réponse au précédent ; renvoie les identifiants des posts."""
    publies = []
    for i, p in enumerate(parties, 1):
        try:
            corps = {"text": p.texte}
            if p.images:
                corps["media"] = {"media_ids": [televerser(http, chemin, alt) for chemin, alt in p.images]}
            if publies:
                corps["reply"] = {"in_reply_to_tweet_id": publies[-1]}
            publies.append(_reponse(http.post(f"{API}/tweets", json=corps, timeout=30), "Publication")["id"])
        except Exception as e:
            deja = f" Déjà publiés : {', '.join(publies)}." if publies else ""
            raise RuntimeError(f"Post {i} sur {len(parties)} : {e}.{deja}") from e
    return publies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finances_etat.promo.publier", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("corps", type=Path, help="texte du ticket (fichier Markdown)")
    parser.add_argument("--essai", action="store_true", help="vérifier et afficher, sans publier")
    args = parser.parse_args(argv)
    for flux in (sys.stdout, sys.stderr):
        flux.reconfigure(encoding="utf-8")
    try:
        parties = lire_ticket(args.corps.read_text(encoding="utf-8"))
        verifier(parties)
        if args.essai:
            for i, p in enumerate(parties, 1):
                images = "".join(f"\n  [image] {c.name}" for c, _ in p.images)
                print(f"--- post {i} ({longueur_x(p.texte)}/{LIMITE})\n{p.texte}{images}")
            return 0
        ids = publier(parties, session_x())
    except Exception as e:
        print(e, file=sys.stderr)
        return 1
    print(f"https://x.com/i/status/{ids[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
