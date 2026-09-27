"""Images du profil X : bannière (1500 × 500) et photo de profil (400 × 400).

    uv run --group promo python -m finances_etat.promo.kit
"""

import sys

import duckdb
import matplotlib.pyplot as plt

from ..config import DB_PATH, ROOT
from . import visuels as v

DOSSIER = ROOT / "promo" / "kit"


def banniere(con) -> None:
    """Titre à gauche, solde budgétaire annuel à droite. X pose la photo de profil en bas à gauche."""
    solde = con.sql("SELECT annee, execution / 1e9 FROM v_budget_annuel "
                    "WHERE code = 'solde_budgetaire' AND execution IS NOT NULL ORDER BY annee").fetchall()
    fig = plt.figure(figsize=(7.5, 2.5), dpi=v.DPI, facecolor=v.SURFACE)
    fig.text(0.05, 0.78, "Finances de l'État", fontsize=24, fontweight="bold", color=v.ENCRE, va="top")
    fig.text(0.05, 0.53, "Tableau de bord indépendant,\nmis à jour chaque jour depuis\nles données publiques",
             fontsize=10.5, color=v.ENCRE2, va="top", linespacing=1.4)
    ax = fig.add_axes((0.55, 0.2, 0.41, 0.62))
    ax.set_axis_off()
    ax.bar([a for a, _ in solde], [m for _, m in solde], width=0.6, color=v.BLEU)
    ax.axhline(0, color=v.AXE, linewidth=0.8)
    fig.text(0.96, 0.9, f"Solde budgétaire de l'État, {solde[0][0]}-{solde[-1][0]}", fontsize=7.5, color=v.MUET,
             ha="right", va="top")
    fig.text(0.96, 0.08, v.SITE, fontsize=7.5, color=v.ENCRE2, fontweight="bold", ha="right", va="bottom")
    v.enregistrer(fig, DOSSIER / "banniere.png")


def avatar() -> None:
    """Trois colonnes blanches sur fond bleu ; X découpe l'image en cercle, le motif reste au centre."""
    fig = plt.figure(figsize=(2, 2), dpi=v.DPI, facecolor=v.BLEU)
    ax = fig.add_axes((0.24, 0.26, 0.52, 0.46))
    ax.set_axis_off()
    ax.bar([0, 1, 2], [0.45, 0.7, 1], width=0.62, color=v.SURFACE)
    ax.set_xlim(-0.5, 2.5)
    ax.set_ylim(0, 1)
    fig.savefig(DOSSIER / "avatar.png", dpi=v.DPI, facecolor=v.BLEU)
    plt.close(fig)


def main() -> int:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        banniere(con)
    finally:
        con.close()
    avatar()
    print(f"Images écrites dans {DOSSIER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
