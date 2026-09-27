"""Visuels des posts : graphiques de 1600 × 900 pixels (16:9, affichés en entier dans le fil de X).

Même palette que le tableau de bord, en thème clair. Chaque image porte sa source et
l'adresse du site, pour qu'une capture partagée renvoie toujours au site.
"""

import re
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

SITE = "finances-etat-fr.streamlit.app"

SURFACE, ENCRE, ENCRE2, MUET = "#ffffff", "#0b0b0b", "#52514e", "#898781"
GRILLE, AXE = "#e1e0d9", "#c3c2b7"
BLEU, ORANGE, VERT = "#2a78d6", "#eb6834", "#1baf7a"  # ordre catégoriel validé (daltonisme, contraste)
GRIS, GRIS_CLAIR = "#898781", "#b8b7b0"
COULEURS_ADMIN = {"État et organismes centraux": BLEU, "Sécurité sociale": ORANGE,
                  "Collectivités locales": VERT, "Union européenne": GRIS}

LARGEUR, HAUTEUR, DPI = 8, 4.5, 200
LIGNE, POINT, ECART = 1.5, 6, 1.2  # épaisseurs en points : trait, marqueur, espace entre segments
ECART_ETIQUETTES = 12  # points entre deux valeurs finales de courbes
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})


def nombre(x: float, decimales: int = 1, separateur: str = "\u202f") -> str:
    texte = f"{abs(x):,.{decimales}f}".replace(",", separateur).replace(".", ",")
    return f"−{texte}" if round(x, decimales) < 0 else texte


def insecables(texte: str) -> str:
    """Espace insécable avant « : ; ? ! % Md€ » : ni la ponctuation ni l'unité ne commencent une ligne."""
    return re.sub(r" ([:;?!%]|Md€)", "\u00a0\\1", texte)


def canevas(titre: str, sous_titre: str, source: str, axes: bool = True):
    """Titre, sous-titre, pied (source et adresse du site) et zone de tracé."""
    fig = plt.figure(figsize=(LARGEUR, HAUTEUR), dpi=DPI, facecolor=SURFACE)
    fig.text(0.045, 0.94, insecables(titre), fontsize=17, fontweight="bold", color=ENCRE, va="top")
    lignes = textwrap.wrap(insecables(sous_titre), 92)
    fig.text(0.045, 0.855, "\n".join(lignes), fontsize=10, color=ENCRE2, va="top", linespacing=1.4)
    fig.text(0.045, 0.035, insecables(f"Source : {source}"), fontsize=7.5, color=MUET, va="bottom")
    fig.text(0.955, 0.035, SITE, fontsize=8.5, color=ENCRE2, fontweight="bold", ha="right", va="bottom")
    if not axes:
        return fig, None
    haut = 0.80 - 0.05 * len(lignes)
    ax = fig.add_axes((0.085, 0.14, 0.845, haut - 0.14))
    habiller(ax)
    return fig, ax


def habiller(ax) -> None:
    for cote in ("top", "right", "left"):
        ax.spines[cote].set_visible(False)
    ax.spines["bottom"].set_color(AXE)
    ax.spines["bottom"].set_linewidth(0.6)
    ax.tick_params(length=0, labelsize=8.5, labelcolor=ENCRE2, pad=5)
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRILLE, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: nombre(v, 0)))


def graduations_annees(ax, x: list) -> None:
    """Graduations entières, limitées à la période couverte (la marge de droite reste vierge)."""
    ax.set_xticks([t for t in ax.get_xticks() if x[0] <= t <= x[-1] and float(t).is_integer()])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda t, _: f"{t:.0f}"))


def enregistrer(fig, chemin: Path) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(chemin, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)
    return chemin


def etiquette(ax, x, y, texte: str, dessous: bool = False, **options) -> None:
    options = {"fontsize": 8.5, "color": ENCRE, "ha": "center", **options}
    ax.annotate(texte, (x, y), xytext=(0, -6 if dessous else 6), textcoords="offset points",
                va="top" if dessous else "bottom", **options)


# ---------------------------------------------------------------------------
# Formes
# ---------------------------------------------------------------------------
def proportions(chemin: Path, titre: str, sous_titre: str, source: str,
                parts: list[tuple[str, float, str]], unite: str = "€") -> Path:
    """Chiffres clés et bande de proportions : parts = (libellé, valeur sur 100, couleur)."""
    fig, _ = canevas(titre, sous_titre, source, axes=False)
    largeur = 0.91 / len(parts)
    for i, (libelle, valeur, couleur) in enumerate(parts):
        x = 0.045 + i * largeur
        fig.text(x, 0.56, f"{nombre(valeur, 0)} {unite}", fontsize=40, fontweight="bold", color=ENCRE, va="bottom")
        fig.add_artist(Ellipse((x + 0.007, 0.505), 0.012, 0.012 * LARGEUR / HAUTEUR, color=couleur,
                               transform=fig.transFigure))
        fig.text(x + 0.02, 0.505, libelle, fontsize=12, color=ENCRE2, va="center")
    bande = fig.add_axes((0.045, 0.27, 0.91, 0.12))
    bande.set_axis_off()
    debut = 0.0
    for _, valeur, couleur in parts:
        bande.barh(0, valeur, left=debut, height=1, color=couleur, edgecolor=SURFACE, linewidth=ECART * 2)
        debut += valeur
    bande.set_xlim(0, debut)
    bande.set_ylim(-0.5, 0.5)
    return enregistrer(fig, chemin)


def cascade(chemin: Path, titre: str, sous_titre: str, source: str,
            etapes: list[tuple[str, float, float, str]]) -> Path:
    """Colonnes flottantes : etapes = (libellé, bas, haut, couleur), valeur affichée = haut − bas."""
    fig, ax = canevas(titre, sous_titre, source)
    for i, (_, bas, haut, couleur) in enumerate(etapes):
        ax.bar(i, haut - bas, bottom=bas, width=0.42, color=couleur)
        etiquette(ax, i, haut, f"{nombre(haut - bas)} Md€", fontsize=11, fontweight="bold")
    ax.set_xticks(range(len(etapes)), [e[0] for e in etapes], fontsize=10, color=ENCRE)
    ax.set_ylim(0, max(e[2] for e in etapes) * 1.15)
    ax.set_ylabel("Md€", color=ENCRE2, fontsize=8.5)
    return enregistrer(fig, chemin)


def colonnes(chemin: Path, titre: str, sous_titre: str, source: str, x: list, y: list[float],
             a_etiqueter: list[int], unite: str = "Md€", format_valeur=None,
             reference: tuple[float, str] | None = None) -> Path:
    """Une série en colonnes ; seules les valeurs d'indice a_etiqueter sont écrites.
    Si toutes les valeurs sont négatives, elles sont écrites au-dessus de la ligne de zéro."""
    format_valeur = format_valeur or (lambda val: nombre(val))
    fig, ax = canevas(titre, sous_titre, source)
    ax.bar(x, y, width=0.6, color=BLEU, edgecolor=SURFACE, linewidth=ECART)
    negatif = max(y) <= 0
    for i in a_etiqueter:
        etiquette(ax, x[i], 0 if negatif else y[i], format_valeur(y[i]), dessous=y[i] < 0 and not negatif)
    bas, haut = min(0, min(y)), max(0, max(y))
    marge = (haut - bas) * 0.12
    ax.set_ylim(bas - (marge if bas < 0 else 0), haut + marge if haut > 0 or negatif else 0)
    if bas < 0:
        ax.axhline(0, color=AXE, linewidth=0.8)
        ax.spines["bottom"].set_visible(False)
    droite = x[-1] + 0.7
    if reference:
        valeur, texte = reference
        ax.axhline(valeur, color=ENCRE2, linewidth=0.8)
        ax.annotate(texte, (x[-1] + 0.8, valeur), va="center", ha="left", fontsize=8.5, color=ENCRE2)
        droite = x[-1] + 2.6
    ax.set_xlim(x[0] - 0.7, droite)
    graduations_annees(ax, x)
    ax.set_ylabel(unite, color=ENCRE2, fontsize=8.5)
    return enregistrer(fig, chemin)


def colonnes_empilees(chemin: Path, titre: str, sous_titre: str, source: str, x: list,
                      series: dict[str, list[float]], couleurs: dict[str, str],
                      au_dessus: dict[int, str]) -> Path:
    """Colonnes empilées avec légende ; au_dessus : texte écrit au-dessus de certaines colonnes."""
    fig, ax = canevas(titre, sous_titre, source)
    largeur = 0.62
    bas = [0.0] * len(x)
    for nom, valeurs in series.items():
        ax.bar(x, valeurs, bottom=bas, width=largeur, color=couleurs[nom], label=nom,
               edgecolor=SURFACE, linewidth=ECART)
        bas = [b + v for b, v in zip(bas, valeurs)]
    for i, texte in au_dessus.items():  # aux extrémités, le texte s'aligne sur le bord de la colonne
        alignement = "left" if i == 0 else "right" if i == len(x) - 1 else "center"
        decalage = {"left": -largeur / 2, "right": largeur / 2, "center": 0}[alignement]
        etiquette(ax, x[i] + decalage, bas[i], texte, fontweight="bold", ha=alignement)
    ax.set_ylim(0, max(bas) * 1.18)
    ax.set_xlim(x[0] - 0.7, x[-1] + 0.7)
    graduations_annees(ax, x)
    ax.set_ylabel("Md€", color=ENCRE2, fontsize=8.5)
    ax.legend(loc="upper left", ncols=len(series), frameon=False, fontsize=8.5, labelcolor=ENCRE2,
              handlelength=1, handleheight=1, borderaxespad=0)
    return enregistrer(fig, chemin)


def courbes(chemin: Path, titre: str, sous_titre: str, source: str, x: list,
            series: list[tuple[str, list[float | None], str]], unite: str = "Md€",
            etiquettes_x: list[str] | None = None, remplir: bool = False,
            reperes: list[int] | None = None, format_valeur=None) -> Path:
    """Courbes ; series = (nom, valeurs, couleur), la dernière est tracée au premier plan.
    Chaque courbe porte sa valeur finale (précédée de son nom si tous les noms sont courts) ; si des valeurs
    sont trop proches, elles sont écartées et reliées à leur point par un trait.
    reperes : indices de points à écrire en plus, sous le point (une seule série)."""
    format_valeur = format_valeur or (lambda val: nombre(val))
    fig, ax = canevas(titre, sous_titre, source)
    fins = []
    avec_noms = len(series) > 1 and all(len(nom) <= 8 for nom, _, _ in series)  # sinon, la légende suffit
    for nom, valeurs, couleur in series:
        points = [(xi, val) for xi, val in zip(x, valeurs) if val is not None]
        xs, ys = zip(*points)
        ax.plot(xs, ys, color=couleur, linewidth=LIGNE, solid_capstyle="round", solid_joinstyle="round",
                label=nom)
        if remplir:
            ax.fill_between(xs, ys, color=couleur, alpha=0.1, linewidth=0)
        ax.plot(xs[-1], ys[-1], "o", color=couleur, markersize=POINT, markeredgecolor=SURFACE,
                markeredgewidth=ECART)
        texte = f"{nom} : {format_valeur(ys[-1])}" if avec_noms else format_valeur(ys[-1])
        fins.append((ys[-1], xs[-1], texte))
        for i in reperes or []:
            if valeurs[i] is not None:
                ax.plot(x[i], valeurs[i], "o", color=couleur, markersize=POINT, markeredgecolor=SURFACE,
                        markeredgewidth=ECART)
                etiquette(ax, x[i], valeurs[i], f"{format_valeur(valeurs[i])} ({x[i]})", dessous=True,
                          ha="left" if i == 0 else "center")
    ax.margins(x=0.02, y=0.15)
    if remplir:
        ax.set_ylim(bottom=0)
    etendue = x[-1] - x[0]
    ax.set_xlim(x[0] - etendue * 0.02, x[-1] + etendue * 0.2)  # place pour les valeurs finales
    if etiquettes_x:
        ax.set_xticks(x, etiquettes_x)
    else:
        graduations_annees(ax, x)
    bas, haut = ax.get_ylim()
    ecart = (haut - bas) * ECART_ETIQUETTES / (ax.get_position().height * HAUTEUR * 72)
    place = None
    for y, xf, texte in sorted(fins, reverse=True):  # de haut en bas
        position = y if place is None else min(y, place - ecart)
        place = position
        relie = abs(position - y) > ecart / 4
        ax.annotate(texte, (xf, y), xytext=(xf + etendue * 0.035, position), textcoords="data", va="center",
                    fontsize=8.5, color=ENCRE,
                    arrowprops=dict(arrowstyle="-", color=AXE, linewidth=0.6, shrinkA=0, shrinkB=4) if relie else None)
    ax.set_ylabel(unite, color=ENCRE2, fontsize=8.5)
    if len(series) > 1:
        ax.legend(loc="upper left", ncols=len(series), frameon=False, fontsize=8.5, labelcolor=ENCRE2,
                  handlelength=1.5, borderaxespad=0)
    return enregistrer(fig, chemin)


def barres(chemin: Path, titre: str, sous_titre: str, source: str,
           libelles: list[str], valeurs: list[float], unite: str = "Md€") -> Path:
    """Barres horizontales triées, valeur au bout de chaque barre ; la marge s'adapte aux libellés."""
    fig, ax = canevas(titre, sous_titre, source)
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    y = list(range(len(libelles)))
    ax.barh(y, valeurs, height=0.6, color=BLEU)
    for yi, val in zip(y, valeurs):
        ax.annotate(f"{nombre(val)} {unite}", (val, yi), xytext=(5, 0), textcoords="offset points", va="center",
                    fontsize=8.5, color=ENCRE)
    ax.set_yticks(y, libelles, fontsize=9, color=ENCRE)
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.set_xlim(0, max(valeurs) * 1.18)
    fig.canvas.draw()
    marge = max(t.get_window_extent().width for t in ax.get_yticklabels()) / fig.bbox.width + 0.012
    position = ax.get_position()
    ax.set_position((0.045 + marge, position.y0, 0.955 - 0.045 - marge, position.height))
    return enregistrer(fig, chemin)
