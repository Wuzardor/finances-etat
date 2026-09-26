"""Point d'entrée : collecte → construction de la base → contrôles.

    uv run python -m finances_etat              # collecte + construction
    uv run python -m finances_etat --hors-ligne # reconstruit depuis les fichiers déjà téléchargés
"""

import argparse
import logging
import sys

import duckdb

from .collecte import journaliser, session, telecharger
from .construction import construire
from .sources import SOURCES

log = logging.getLogger("finances_etat")


def collecter() -> int:
    http = session()
    echecs = 0
    for src in SOURCES:
        try:
            t = telecharger(src, http)
            journaliser(t)
            etat = "nouvelle version" if t.nouveau else "inchangé"
            log.info("%-16s %-16s %8.1f ko", src.cle, etat, t.octets / 1024)
        except Exception as e:  # une source en panne ne doit pas bloquer les autres
            echecs += 1
            log.error("%-16s échec : %s (la dernière version téléchargée sera utilisée)", src.cle, e)
    return echecs


def md(x: float) -> str:
    return f"{x / 1e9:+,.1f} Md€".replace(",", " ").replace(".", ",")


def resume(chemin) -> None:
    con = duckdb.connect(str(chemin), read_only=True)
    try:
        date, cumul, n1 = con.sql("""
            SELECT date_arrete, cumul, cumul_n1 FROM v_cumul_vs_n1
            WHERE code = 'solde_budgetaire' ORDER BY date_arrete DESC LIMIT 1
        """).fetchone()
        log.info("Dernière situation mensuelle : %s, solde budgétaire cumulé %s (même mois N-1 : %s)",
                 date.strftime("%d/%m/%Y"), md(cumul), md(n1) if n1 is not None else "n.d.")
        ok, connues, alertes = con.sql("""
            SELECT count(*) FILTER (WHERE statut = 'ok'), count(*) FILTER (WHERE statut = 'connue'),
                   count(*) FILTER (WHERE statut = 'alerte')
            FROM meta_controles
        """).fetchone()
        log.info("Contrôles qualité : %d ok, %d anomalie(s) connue(s) de la source, %d nouvelle(s) alerte(s)",
                 ok, connues, alertes)
        for jeu, controle, periode, ecart in con.sql("""
            SELECT jeu, controle, periode, ecart FROM meta_controles WHERE statut = 'alerte' ORDER BY jeu, periode
        """).fetchall():
            log.warning("  %s | %s | %s | écart %s", jeu, controle, periode, ecart)
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finances_etat", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hors-ligne", action="store_true",
                        help="ne rien télécharger, reconstruire depuis data/raw")
    args = parser.parse_args(argv)
    # Redirigée vers un fichier (tâche planifiée), la sortie serait sinon encodée en cp1252 sous Windows
    for flux in (sys.stdout, sys.stderr):
        flux.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    echecs = 0 if args.hors_ligne else collecter()
    chemin = construire()
    log.info("Base construite : %s", chemin)
    resume(chemin)
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
