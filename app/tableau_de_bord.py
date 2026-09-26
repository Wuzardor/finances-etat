"""Tableau de bord des finances de l'État.

    uv run streamlit run app/tableau_de_bord.py
"""

import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# L'hébergeur n'installe pas forcément le paquet du projet : on le rend importable depuis la racine du dépôt
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finances_etat.config import DB_PATH, RAW_DIR, REF_DIR, SQL_DIR  # noqa: E402
from finances_etat.construction import construire  # noqa: E402

st.set_page_config(page_title="Finances de l'État", page_icon=":material/account_balance:", layout="wide")

# Liens du projet. Un lien vide masque le bouton correspondant.
URL_DEPOT = "https://github.com/Wuzardor/finances-etat"
URL_SOUTIEN = ""  # page de soutien : Patreon, Ko-fi, Liberapay…

# ---------------------------------------------------------------------------
# Couleurs : palette catégorielle de référence, dans son ordre validé
# (séparation daltonisme et contraste vérifiés en clair et en sombre).
# Une série garde toujours la même couleur, quel que soit le filtre.
# ---------------------------------------------------------------------------
SOMBRE = st.context.theme.type == "dark"
SERIES = (["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"] if SOMBRE
          else ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"])
C = {
    "surface": "#0e1117" if SOMBRE else "#ffffff",  # fond Streamlit : sert d'espace entre segments empilés
    "encre": "#ffffff" if SOMBRE else "#0b0b0b",
    "encre2": "#c3c2b7" if SOMBRE else "#52514e",
    "grille": "#2c2c2a" if SOMBRE else "#e1e0d9",
    "axe": "#383835" if SOMBRE else "#c3c2b7",
    "n1": "#898781",                                 # neutre ; années précédentes en retrait
    "n2": "#5f5e5a" if SOMBRE else "#b8b7b0",
    "hausse": "#3987e5" if SOMBRE else "#2a78d6",    # paire divergente bleu / rouge
    "baisse": "#e66767" if SOMBRE else "#e34948",
}
COULEURS_ADMIN = {"État et organismes centraux": SERIES[0], "Sécurité sociale": SERIES[1],
                  "Collectivités locales": SERIES[2], "Union européenne": C["n1"]}
COURT_ADMIN = {"État et organismes centraux": "État", "Sécurité sociale": "Sécurité sociale",
               "Collectivités locales": "Collectivités", "Union européenne": "Union européenne"}
AVEC_ARTICLE = {"État et organismes centraux": "l'État et ses organismes", "Sécurité sociale": "la Sécurité sociale",
                "Collectivités locales": "les collectivités locales", "Union européenne": "l'Union européenne"}
POLICE = 'system-ui, -apple-system, "Segoe UI", sans-serif'

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
MOIS_LONG = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
             "octobre", "novembre", "décembre"]


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------
def nombre(x: float, decimales: int = 1) -> str:
    return f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")


def md(x: float, signe: bool = False) -> str:
    s = nombre(x / 1e9)
    return (f"+{s}" if signe and x > 0 else s) + " Md€"


def pct(part: float) -> str:
    return f"{round(part * 100)} %"


def date_longue(d) -> str:
    return f"{d.day} {MOIS_LONG[d.month - 1]} {d.year}"


def rgba(couleur: str, alpha: float) -> str:
    h = couleur.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# Accès aux données : connexion en lecture seule, ouverte le temps d'une requête.
# Le cache est invalidé dès que la base est reconstruite (date de modification).
#
# La base n'est pas versionnée : elle est reconstruite à partir des fichiers bruts
# dès qu'elle manque ou que l'un de ses fichiers d'origine (brut, référentiel, vues)
# est plus récent, par exemple après un déploiement ou une mise à jour des données.
# ---------------------------------------------------------------------------
def version_sources() -> float:
    fichiers = [*RAW_DIR.rglob("*.*"), *REF_DIR.glob("*.csv"), *SQL_DIR.glob("*.sql")]
    return max((f.stat().st_mtime for f in fichiers), default=0.0)


@st.cache_resource(show_spinner="Préparation des données…")
def _construire(version: float) -> None:  # une seule construction à la fois, même avec plusieurs visiteurs
    construire()


version = version_sources()
if not DB_PATH.exists() or DB_PATH.stat().st_mtime < version:
    try:
        _construire(version)
    except Exception as e:  # une base ancienne vaut mieux qu'une page d'erreur
        if not DB_PATH.exists():
            st.error(f"Base introuvable et impossible à construire : {e}")
            st.code("uv run python -m finances_etat", language="bash")
            st.stop()
        st.warning(f"Les données n'ont pas pu être actualisées, la version précédente est affichée ({e}).")


@st.cache_data(show_spinner=False)
def _requete(sql: str, params: tuple, version: float) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(sql, list(params)).df()
    finally:
        con.close()


def requete(sql: str, *params) -> pd.DataFrame:
    return _requete(sql, params, DB_PATH.stat().st_mtime)


# ---------------------------------------------------------------------------
# Graphiques
# ---------------------------------------------------------------------------
def habiller(fig: go.Figure, hauteur: int = 360, unite: str = "Md€", legende: bool = True,
             survol: str = "x unified") -> go.Figure:
    fig.update_layout(
        height=hauteur,
        margin=dict(l=72, r=56, t=36 if legende else 12, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=POLICE, size=13, color=C["encre2"]),
        separators=", ",
        hovermode=survol,
        hoverlabel=dict(bgcolor=C["surface"], bordercolor=C["axe"], font=dict(color=C["encre"], family=POLICE)),
        showlegend=legende,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        bargap=0.3,
        barcornerradius=4,
    )
    fig.update_xaxes(showgrid=False, linecolor=C["axe"], ticks="", zeroline=False, automargin=True)
    fig.update_yaxes(title=dict(text=unite, standoff=12), gridcolor=C["grille"], gridwidth=1, zeroline=True,
                     zerolinecolor=C["axe"], zerolinewidth=1, ticks="", automargin=True)
    return fig


def etiquette_fin(fig: go.Figure, x, y: float, texte: str) -> None:
    fig.add_annotation(x=x, y=y, text=texte, showarrow=False, xanchor="left", xshift=8,
                       font=dict(color=C["encre2"], size=12))


def afficher(fig: go.Figure, donnees: pd.DataFrame | None = None) -> None:
    st.plotly_chart(fig, theme=None, config={"displayModeBar": False})
    if donnees is not None:
        with st.expander("Voir les données"):
            st.dataframe(donnees, hide_index=True)


def graphique_cumul(code: str, nb_annees: int = 3) -> None:
    """Cumul depuis le 1er janvier : année en cours mise en avant, années précédentes en retrait."""
    df = requete("""
        SELECT annee, mois, cumul / 1e9 AS cumul
        FROM v_execution_mensuelle
        WHERE code = ? AND annee > (SELECT max(annee) FROM v_execution_mensuelle) - ?
        ORDER BY annee, mois
    """, code, nb_annees)
    derniere = int(df["annee"].max())
    couleurs = {derniere: SERIES[0], derniere - 1: C["n1"], derniere - 2: C["n2"]}
    fig = go.Figure()
    for annee in sorted(df["annee"].unique()):  # l'année en cours est tracée en dernier, au-dessus
        d = df[df["annee"] == annee]
        x = [MOIS[m - 1] for m in d["mois"]]
        fig.add_scatter(x=x, y=d["cumul"], name=str(annee), mode="lines",
                        line=dict(color=couleurs.get(annee, C["n2"]), width=2),
                        hovertemplate="%{y:,.1f} Md€")
        etiquette_fin(fig, x[-1], d["cumul"].iloc[-1], str(annee))
    fig.update_xaxes(categoryorder="array", categoryarray=MOIS)
    habiller(fig)
    tableau = df.pivot(index="mois", columns="annee", values="cumul").round(1)
    tableau.index = [MOIS_LONG[m - 1] for m in tableau.index]
    tableau.columns = [str(c) for c in tableau.columns]
    afficher(fig, tableau.reset_index(names="mois"))


def graphique_empile(df: pd.DataFrame, ordre: list[str], couleurs: dict[str, str] | None = None) -> None:
    """Barres annuelles empilées ; df : annee, serie, md. La couleur suit la série."""
    couleurs = couleurs or dict(zip(ordre, SERIES))
    fig = go.Figure()
    for serie in ordre:
        d = df[df["serie"] == serie]
        if d.empty:
            continue
        fig.add_bar(x=d["annee"], y=d["md"], name=serie, hovertemplate="%{y:,.1f} Md€",
                    marker=dict(color=couleurs[serie], line=dict(color=C["surface"], width=2)))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(dtick=1)
    habiller(fig, hauteur=400)
    tableau = df.pivot_table(index="annee", columns="serie", values="md", aggfunc="sum")
    tableau = tableau[[s for s in ordre if s in tableau.columns]].round(1)
    tableau["Total"] = tableau.sum(axis=1).round(1)
    afficher(fig, tableau.reset_index())


def barres_simples(x, y, unite: str, hauteur: int = 320, format_survol: str = "%{y:,.1f} Md€") -> go.Figure:
    fig = go.Figure(go.Bar(x=x, y=y, marker_color=SERIES[0], hovertemplate=format_survol, name=""))
    fig.update_xaxes(dtick=1)
    return habiller(fig, hauteur=hauteur, unite=unite, legende=False)


ECART_NOEUDS = 16  # px entre deux nœuds d'une même colonne


def _positions(totaux: list[float], colonnes: list[int], abscisses: list[float], hauteur: int,
               puits: set[int], en_bas: set[int]):
    """Place les nœuds colonne par colonne, dans l'ordre de la liste (y = centre du nœud, 0 en haut).

    Sans positions imposées, Plotly renvoie tout nœud sans flux sortant (puits) dans la dernière
    colonne : les remboursements et dégrèvements se retrouveraient parmi les dépenses. Plotly
    calcule pourtant la hauteur des nœuds avec ce regroupement-là : l'échelle en tient compte.
    Les colonnes de en_bas sont alignées sur le bas plutôt que sur le haut.
    """
    ecart = ECART_NOEUDS / (hauteur - 16)
    derniere = max(colonnes)

    def groupes(colonne_de) -> dict[int, list[int]]:
        g = defaultdict(list)
        for i in range(len(totaux)):
            g[colonne_de(i)].append(i)
        return g

    nos_colonnes = groupes(lambda i: colonnes[i])
    echelle = min((1 - ecart * (len(g) - 1)) / sum(totaux[i] for i in g)
                  for regroupement in (nos_colonnes, groupes(lambda i: derniere if i in puits else colonnes[i]))
                  for g in regroupement.values())
    y = [0.0] * len(totaux)
    for c, g in nos_colonnes.items():
        haut = 1 - (sum(totaux[i] for i in g) * echelle + ecart * (len(g) - 1)) if c in en_bas else 0.0
        for i in g:
            h = totaux[i] * echelle
            y[i] = min(max(haut + h / 2, 0.001), 0.999)  # Plotly ignore les positions nulles
            haut += h + ecart
    return [abscisses[c] for c in colonnes], y


def sankey(noeuds: list[tuple], liens: list[tuple[int, int, float, str]], hauteur: int,
           colonnes: list[int] | None = None, abscisses: list[float] | None = None,
           en_bas: set[int] = frozenset()) -> go.Figure:
    """Diagramme de flux.

    noeuds : (libellé court, couleur) ou (libellé court, couleur, texte de survol) ;
    liens : (source, cible, montant en Md€, couleur). Les libellés restent courts pour que
    ceux de la colonne du milieu ne chevauchent pas ceux de la dernière colonne.
    colonnes / abscisses / en_bas : colonne de chaque nœud, abscisse de chaque colonne (0 à 1)
    et colonnes alignées en bas, pour imposer la disposition ; sinon Plotly la calcule.
    """
    entrees, sorties = defaultdict(float), defaultdict(float)
    for s, c, v, _ in liens:
        sorties[s] += v
        entrees[c] += v
    totaux = [max(entrees[i], sorties[i]) for i in range(len(noeuds))]
    position = {}
    if colonnes:
        puits = {i for i in range(len(noeuds)) if not sorties[i]}
        position = dict(zip(("x", "y"), _positions(totaux, colonnes, abscisses, hauteur, puits, en_bas)))
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=[f"{n[0]} · {nombre(t)} Md€" for n, t in zip(noeuds, totaux)],
                  color=[n[1] for n in noeuds], pad=ECART_NOEUDS, thickness=14, line=dict(width=0),
                  customdata=[n[2] if len(n) > 2 else n[0] for n in noeuds],
                  hovertemplate="%{customdata}<br>%{value:,.1f} Md€<extra></extra>", **position),
        link=dict(source=[l[0] for l in liens], target=[l[1] for l in liens], value=[l[2] for l in liens],
                  color=[l[3] for l in liens],
                  customdata=[f"{noeuds[s][0]} → {noeuds[c][0]}" for s, c, _, _ in liens],  # libellés courts
                  hovertemplate="%{customdata}<br>%{value:,.1f} Md€<extra></extra>"),
        textfont=dict(color=C["encre"], size=12, family=POLICE, shadow="none"),
    ))
    fig.update_layout(height=hauteur, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                      separators=", ", font=dict(family=POLICE),
                      hoverlabel=dict(bgcolor=C["surface"], bordercolor=C["axe"], font=dict(color=C["encre"])))
    return fig


def tableau_flux(noeuds, liens) -> pd.DataFrame:
    nom = [n[2] if len(n) > 2 else n[0] for n in noeuds]
    return pd.DataFrame([{"de": nom[s], "vers": nom[c], "Md€": round(v, 2)} for s, c, v, _ in liens])


# ---------------------------------------------------------------------------
# En-tête et barre latérale
# ---------------------------------------------------------------------------
dernier_arrete = requete("SELECT max(date_arrete) AS d FROM stg_smb")["d"].iloc[0]
# Date de la dernière nouveauté collectée (la base elle-même est reconstruite à chaque démarrage de l'hébergeur)
mise_a_jour = requete("SELECT max(CAST(horodatage AS TIMESTAMP)) AS d FROM meta_collectes WHERE nouveau")["d"].iloc[0]
annee_courante = dernier_arrete.year
fin_mois = f"fin {MOIS_LONG[dernier_arrete.month - 1]}"

st.title("Finances de l'État")
st.caption(f"Exécution budgétaire au {date_longue(dernier_arrete)} · données open data DGFiP et Eurostat, "
           f"mises à jour le {mise_a_jour:%d/%m/%Y}")

INDEPENDANT = "**Site indépendant, gratuit et sans publicité**, sans lien avec l'administration."


def bouton_soutien(conteneur, width: str = "stretch") -> None:
    conteneur.link_button("Soutenir le projet", URL_SOUTIEN, type="primary", icon=":material/favorite:", width=width)


with st.container(border=True):
    if URL_SOUTIEN:
        texte, soutien, code = st.columns([4, 1.3, 1.3], vertical_alignment="center")
        texte.markdown(f"{INDEPENDANT} Il vit grâce à ses lecteurs : votre soutien finance sa mise à jour "
                       "et la création d'un site plus complet.")
        bouton_soutien(soutien)
    else:
        texte, code = st.columns([4, 1.3], vertical_alignment="center")
        texte.markdown(f"{INDEPENDANT} Le code et les données sont ouverts : chacun peut vérifier les calculs "
                       "et contribuer.")
    code.link_button("Contribuer sur GitHub", URL_DEPOT, icon=":material/code:", width="stretch")

with st.sidebar:
    st.subheader("Le projet")
    st.markdown(f"{INDEPENDANT} Construit à partir des données publiques de la DGFiP et d'Eurostat : "
                "la méthode est détaillée dans l'onglet « Méthodologie ».")
    if URL_SOUTIEN:
        bouton_soutien(st)
    st.markdown(f"[Code source et contributions]({URL_DEPOT}) · [Signaler une erreur]({URL_DEPOT}/issues/new)")
    st.subheader("Repères")
    st.markdown("""
**Solde budgétaire** : recettes moins dépenses de l'**État** seul, en caisse (encaissements et décaissements).

**Déficit public (Maastricht)** : toutes les administrations publiques (État, Sécurité sociale,
collectivités), en droits constatés. Il ne se déduit pas du solde budgétaire.

**Recettes nettes** : après remboursements et dégrèvements d'impôts (restitutions de TVA, crédits d'impôt…).

**Impôts partagés** : une partie de la TVA, de la TICPE ou de l'IS est affectée à la Sécurité sociale et
aux collectivités. Les recettes de l'État n'en montrent que sa part.

**PSR** : prélèvements sur recettes, versés directement aux collectivités et à l'Union européenne.

**LFI / LFR / LFG** : loi de finances initiale, rectificative, de fin de gestion.

**Comptabilité générale** : vision patrimoniale (charges, produits, bilan), en droits constatés,
avec provisions et amortissements.
""")

NOMS_ONGLETS = ["Vue d'ensemble", "Circuits de l'argent", "Recettes", "Dépenses", "Prévu vs réalisé",
                "Comptes de l'État", "Qualité et sources", "Méthodologie"]
onglet = dict(zip(NOMS_ONGLETS, st.tabs(NOMS_ONGLETS)))

# ---------------------------------------------------------------------------
# Vue d'ensemble
# ---------------------------------------------------------------------------
with onglet["Vue d'ensemble"]:
    kpi = requete("""
        SELECT code, cumul, cumul_n1 FROM v_cumul_vs_n1
        WHERE date_arrete = (SELECT max(date_arrete) FROM stg_smb)
          AND code IN ('solde_budgetaire', 'rec_bg_nettes', 'dep_bg_total',
                       'rec_fiscales', 'rd_impots_etat', 'rd_impots_locaux')
    """).set_index("code")
    kpi.loc["impots_bruts"] = kpi.loc[["rec_fiscales", "rd_impots_etat", "rd_impots_locaux"]].sum()
    maas = requete("SELECT * FROM v_maastricht WHERE dette_pct_pib IS NOT NULL ORDER BY annee")
    derniere_maas, precedente_maas = maas.iloc[-1], maas.iloc[-2]

    st.caption(f"État, cumul du 1er janvier au {date_longue(dernier_arrete)}, comparé à {fin_mois} {annee_courante - 1}.")
    k1, k2, k3, k4, k5 = st.columns(5)
    for col, code, titre, couleur, aide in [
        (k1, "solde_budgetaire", "Solde budgétaire", "normal", "Recettes moins dépenses de l'État."),
        (k2, "impots_bruts", "Impôts bruts", "normal",
         "Impôts encaissés par l'État avant remboursements et dégrèvements (crédits de TVA, crédits d'impôt…)."),
        (k3, "rec_bg_nettes", "Recettes nettes", "normal",
         "Impôts nets des remboursements et dégrèvements, plus recettes non fiscales : ce que l'État garde."),
        (k4, "dep_bg_total", "Dépenses nettes", "inverse", "Dépenses du budget général."),
    ]:
        ligne = kpi.loc[code]
        col.metric(titre, md(ligne["cumul"]), delta=f"{md(ligne['cumul'] - ligne['cumul_n1'], signe=True)} sur un an",
                   delta_color=couleur, border=True, help=f"{aide} Cumul à {fin_mois} {annee_courante}.")
    ecart_dette = derniere_maas["dette_pct_pib"] - precedente_maas["dette_pct_pib"]
    k5.metric(f"Dette publique {int(derniere_maas['annee'])}", f"{nombre(derniere_maas['dette_pct_pib'])} % du PIB",
              delta=f"{'+' if ecart_dette > 0 else ''}{nombre(ecart_dette)} pt sur un an", delta_color="inverse",
              border=True, help="Toutes administrations publiques, au sens de Maastricht (Eurostat).")

    st.subheader("Solde budgétaire cumulé depuis le 1er janvier")
    st.caption("Le solde se creuse en cours d'année puis se redresse en fin d'exercice : "
               "comparer à la même date des années précédentes, pas au solde annuel.")
    graphique_cumul("solde_budgetaire")

    st.subheader("Solde budgétaire annuel exécuté")
    solde = requete("""
        SELECT annee, execution / 1e9 AS md FROM v_budget_annuel
        WHERE code = 'solde_budgetaire' AND execution IS NOT NULL ORDER BY annee
    """)
    afficher(barres_simples(solde["annee"], solde["md"], "Md€"), solde.rename(columns={"md": "solde (Md€)"}).round(1))

    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Déficit public, toutes administrations")
        st.caption("Solde au sens de Maastricht, en % du PIB (Eurostat).")
        afficher(barres_simples(maas["annee"], maas["solde_pct_pib"], "% du PIB", 300, "%{y:,.1f} % du PIB"),
                 maas[["annee", "solde_pct_pib", "solde"]].assign(solde=lambda d: (d["solde"] / 1e9).round(1))
                 .rename(columns={"solde_pct_pib": "% du PIB", "solde": "Md€"}))
    with g2:
        st.subheader("Dette publique, toutes administrations")
        st.caption("Dette brute consolidée au sens de Maastricht, en % du PIB (Eurostat).")
        fig = go.Figure(go.Scatter(x=maas["annee"], y=maas["dette_pct_pib"], mode="lines",
                                   line=dict(color=SERIES[0], width=2), hovertemplate="%{y:,.1f} % du PIB", name=""))
        fig.update_xaxes(dtick=5)
        afficher(habiller(fig, 300, "% du PIB", legende=False),
                 maas[["annee", "dette_pct_pib", "dette"]].assign(dette=lambda d: (d["dette"] / 1e9).round(0))
                 .rename(columns={"dette_pct_pib": "% du PIB", "dette": "Md€"}))

# ---------------------------------------------------------------------------
# Circuits de l'argent
# ---------------------------------------------------------------------------
with onglet["Circuits de l'argent"]:
    st.subheader("Qui encaisse les impôts, et comment chaque administration dépense")
    TOUS = "Tous les prélèvements obligatoires"
    annees_po = requete("""
        SELECT DISTINCT annee FROM v_prelevements
        WHERE annee IN (SELECT annee FROM v_depenses_fonction) ORDER BY annee DESC
    """)["annee"].tolist()
    f1, f2, f3 = st.columns([3, 1, 2], vertical_alignment="bottom")
    annee_po = f2.selectbox("Année", annees_po, key="annee_po")
    totaux_po = requete("""
        SELECT prelevement, sum(montant) AS t FROM v_prelevements WHERE annee = ? GROUP BY 1 ORDER BY t DESC
    """, annee_po)
    options_po = [TOUS, *totaux_po["prelevement"]]
    choix_po = f1.selectbox("Prélèvement", options_po, index=options_po.index("TVA"), key="choix_po")
    prorata = f3.toggle("Montrer comment chaque administration dépense", value=True)

    po = requete("""
        SELECT prelevement, administration, ordre_administration, montant / 1e9 AS md
        FROM v_prelevements WHERE annee = ? ORDER BY ordre_administration
    """, annee_po)
    if choix_po != TOUS:
        po = po[po["prelevement"] == choix_po]
    total_po = po["md"].sum()
    par_admin = po.groupby("administration", sort=False)["md"].sum().sort_values(ascending=False)

    objet = "prélèvements obligatoires" if choix_po == TOUS else choix_po if choix_po == "TVA" else choix_po.lower()
    detail = " ; ".join(f"{nombre(v)} Md€ ({pct(v / total_po)}) pour {AVEC_ARTICLE[a]}" for a, v in par_admin.items())
    st.markdown(f"**En {annee_po}, les administrations publiques ont encaissé {nombre(total_po)} Md€ de {objet}** : "
                f"{detail}.")

    seuil = total_po * 0.001
    sources_po = list(po.groupby("prelevement")["md"].sum().sort_values(ascending=False).index)
    admins = list(par_admin.sort_index(key=lambda s: s.map(lambda a: list(COULEURS_ADMIN).index(a))).index)
    noeuds = [(s, C["n1"]) for s in sources_po] + [(COURT_ADMIN[a], COULEURS_ADMIN[a], a) for a in admins]
    liens = [(sources_po.index(r.prelevement), len(sources_po) + admins.index(r.administration), r.md,
              rgba(COULEURS_ADMIN[r.administration], 0.45))
             for r in po.itertuples() if r.md > seuil]
    if prorata:
        fonctions = requete("""
            SELECT administration, fonction, precision, ordre_fonction, part FROM v_depenses_fonction
            WHERE annee = ? ORDER BY ordre_fonction
        """, annee_po)
        precisions = dict(zip(fonctions["fonction"], fonctions["precision"]))
        noms_fonctions = list(precisions)
        debut = len(noeuds)
        noeuds += [(f, C["n1"], f"{f} ({precisions[f]})") for f in noms_fonctions]
        for r in fonctions.itertuples():
            if r.administration in par_admin and par_admin[r.administration] * r.part > seuil:
                liens.append((len(sources_po) + admins.index(r.administration), debut + noms_fonctions.index(r.fonction),
                              par_admin[r.administration] * r.part, rgba(COULEURS_ADMIN[r.administration], 0.45)))
    hauteur = 720 if choix_po == TOUS else 560
    afficher(sankey(noeuds, liens, hauteur), tableau_flux(noeuds, liens))
    if prorata:
        st.info("**Un impôt ne finance pas une dépense précise** : chaque administration verse ses recettes dans un "
                "pot commun. La dernière colonne répartit l'argent reçu **au prorata de l'ensemble des dépenses** de "
                "chaque administration. C'est une clé de lecture, pas un fléchage. Les transferts entre "
                "administrations (dotations de l'État aux collectivités, par exemple) figurent en « services généraux » "
                "chez celle qui les verse. Les dépenses dépassent les prélèvements : l'écart est couvert par "
                "d'autres recettes et par l'emprunt.", icon=":material/info:")

    st.subheader(f"Répartition dans le temps : {objet}")
    evo = requete("""
        SELECT annee, administration AS serie, sum(montant) / 1e9 AS md FROM v_prelevements
        WHERE ? OR prelevement = ? GROUP BY ALL ORDER BY annee
    """, choix_po == TOUS, choix_po)
    graphique_empile(evo, [a for a in COULEURS_ADMIN if a in set(evo["serie"])], COULEURS_ADMIN)
    st.caption("Source : Eurostat, comptabilité nationale (gov_10a_taxag, gov_10a_exp). Les montants peuvent différer "
               "légèrement du budget de l'État (champ « État et organismes centraux », droits constatés).")

    st.divider()
    st.subheader("Le budget de l'État : d'où vient l'argent, où il va")
    annees_budget = requete("""
        SELECT DISTINCT annee FROM v_budget_annuel
        WHERE code = 'solde_budgetaire' AND execution IS NOT NULL ORDER BY annee DESC
    """)["annee"].tolist()
    periode_courante = f"{annee_courante} (cumul à {fin_mois})"
    periodes = [periode_courante, *annees_budget]
    periode = st.selectbox("Période", periodes, index=1, key="periode_budget")
    if periode == periode_courante:
        valeurs = requete("""
            SELECT code, cumul / 1e9 AS v FROM v_execution_mensuelle
            WHERE date_arrete = (SELECT max(date_arrete) FROM stg_smb)
        """)
    else:
        valeurs = requete("SELECT code, execution / 1e9 AS v FROM v_budget_annuel WHERE annee = ?", periode)
    v = defaultdict(float, zip(valeurs["code"], valeurs["v"]))

    impots = [("Impôt sur le revenu", v["rec_ir"]), ("Impôt sur les sociétés", v["rec_is"]),
              ("TVA (part de l'État)", v["rec_tva"]), ("TICPE (part de l'État)", v["rec_ticpe"]),
              ("Autres impôts", v["rec_autres_fiscales"])]
    rendus = v["rd_impots_etat"] + v["rd_impots_locaux"]
    impots_nets = sum(m for _, m in impots)
    impots_bruts = impots_nets + rendus  # recettes fiscales brutes = nettes + remboursements et dégrèvements
    entrees = [("Recettes non fiscales", v["rec_non_fiscales"], "autre"),
               ("Fonds de concours", v["rec_fonds_concours"], "autre")]
    sorties = [("Personnel", v["dep_t2_personnel"]), ("Fonctionnement", v["dep_t3_fonctionnement"]),
               ("Charge de la dette", v["dep_t4_charge_dette"]), ("Investissement", v["dep_t5_investissement"]),
               ("Intervention (aides, transferts…)", v["dep_t6_intervention"]),
               ("Autres dépenses", v["dep_t1_pouvoirs_publics"] + v["dep_t7_operations_financieres"]),
               ("Prélèvement pour les collectivités", v["psr_collectivites"]),
               ("Prélèvement pour l'Union européenne", v["psr_ue"])]
    for code, nom in [("solde_comptes_speciaux", "comptes spéciaux"), ("solde_budgets_annexes", "budgets annexes")]:
        if v[code] > 0:
            entrees.append((f"Excédent des {nom}", v[code], "autre"))
        elif v[code] < 0:
            sorties.append((f"Déficit des {nom}", -v[code]))
    if v["solde_budgetaire"] < 0:
        entrees.append(("Emprunt (déficit)", -v["solde_budgetaire"], "emprunt"))
    else:
        sorties.append(("Excédent", v["solde_budgetaire"]))

    # Colonnes : ressources | impôts nets et montants rendus | budget | emplois
    couleur_type = {"impot": SERIES[0], "autre": C["n1"], "emprunt": C["baisse"]}
    bleu, gris = rgba(SERIES[0], 0.45), rgba(C["n1"], 0.35)
    noeuds = [("Impôts bruts", SERIES[0], "Impôts encaissés par l'État, avant remboursements et dégrèvements")]
    noeuds += [(nom, couleur_type[t]) for nom, _, t in entrees]
    colonnes = [0] * len(noeuds)
    i_rendus = len(noeuds)
    noeuds.append(("Rendus aux contribuables", C["n1"],
                   "Remboursements et dégrèvements : crédits de TVA remboursés, restitutions d'impôt sur les sociétés, "
                   "crédits d'impôt, dégrèvements d'impôts locaux pris en charge par l'État"))
    i_impots = len(noeuds)
    noeuds += [(nom, SERIES[0]) for nom, _ in impots]
    colonnes += [1] * (1 + len(impots))
    centre = len(noeuds)
    noeuds.append(("Budget de l'État", C["encre2"]))
    noeuds += [(nom, C["n1"]) for nom, _ in sorties]
    colonnes += [2] + [3] * len(sorties)

    liens = [(0, i_rendus, rendus, gris)]
    for k, (_, m) in enumerate(impots):
        if m > 0:  # un impôt peut être négatif en début d'année (restitutions supérieures aux encaissements)
            liens += [(0, i_impots + k, m, bleu), (i_impots + k, centre, m, bleu)]
    liens += [(1 + k, centre, m, rgba(couleur_type[t], 0.45)) for k, (_, m, t) in enumerate(entrees) if m > 0]
    liens += [(centre, centre + 1 + j, m, gris) for j, (_, m) in enumerate(sorties) if m > 0]

    total = impots_nets + sum(m for _, m, _ in entrees)
    part_impots = round(impots_nets / total * 100)
    part_emprunt = round(sum(m for _, m, t in entrees if t == "emprunt") / total * 100)
    libelle_periode = f"En {periode}" if periode != periode_courante else f"Du 1er janvier à {fin_mois} {annee_courante}"
    st.markdown(f"**{libelle_periode}, l'État a encaissé {nombre(impots_bruts)} Md€ d'impôts bruts, dont "
                f"{nombre(rendus)} Md€ rendus aux contribuables : il en a gardé {nombre(impots_nets)} Md€.** "
                f"Avec les autres recettes et l'emprunt, il a mobilisé {nombre(total)} Md€. Sur 100 € : "
                f"{part_impots} € d'impôts, {100 - part_impots - part_emprunt} € d'autres recettes et "
                f"{part_emprunt} € d'emprunt.")
    # Budget aligné en bas : l'emprunt et les autres recettes y arrivent sous les impôts, sans croiser leurs nœuds
    afficher(sankey(noeuds, liens, 560, colonnes, [0.001, 0.27, 0.55, 0.999], en_bas={2}), tableau_flux(noeuds, liens))
    st.caption("Impôts bruts = impôts nets + remboursements et dégrèvements. Les montants rendus sont surtout des "
               "crédits de TVA remboursés aux entreprises, des restitutions d'impôt sur les sociétés, des crédits "
               "d'impôt et des dégrèvements. Les « prélèvements sur recettes » sont versés directement aux collectivités "
               "et à l'Union européenne. Source : DGFiP, situations mensuelles budgétaires.")

# ---------------------------------------------------------------------------
# Recettes
# ---------------------------------------------------------------------------
IMPOTS = {"rec_ir": "Impôt sur le revenu", "rec_is": "Impôt sur les sociétés", "rec_tva": "TVA (part de l'État)",
          "rec_ticpe": "TICPE (part de l'État)", "rec_autres_fiscales": "Autres recettes fiscales"}

with onglet["Recettes"]:
    st.subheader("Recettes fiscales nettes de l'État par impôt")
    st.caption("Part de l'État seulement. Depuis 2018, une part croissante de la TVA est affectée à la Sécurité "
               "sociale et aux collectivités : la TVA totale a augmenté, c'est la part de l'État qui a baissé. "
               "Voir l'onglet « Circuits de l'argent ».")
    rec = requete(f"""
        SELECT annee, code, execution / 1e9 AS md FROM v_budget_annuel
        WHERE code IN ({", ".join("?" * len(IMPOTS))}) AND execution IS NOT NULL
    """, *IMPOTS)
    rec["serie"] = rec["code"].map(IMPOTS)
    graphique_empile(rec, list(IMPOTS.values()))

    st.subheader(f"Suivi mensuel {annee_courante}")
    lignes_rec = {"rec_bg_nettes": "Recettes nettes du budget général", "rec_fiscales": "Recettes fiscales nettes",
                  **IMPOTS, "rec_non_fiscales": "Recettes non fiscales", "rd_impots_etat": "Remboursements et dégrèvements"}
    choix = st.selectbox("Recette", list(lignes_rec), format_func=lignes_rec.get, key="rec")
    graphique_cumul(choix)

# ---------------------------------------------------------------------------
# Dépenses
# ---------------------------------------------------------------------------
TITRES = {"dep_t2_personnel": "Personnel", "dep_t3_fonctionnement": "Fonctionnement",
          "dep_t4_charge_dette": "Charge de la dette", "dep_t5_investissement": "Investissement",
          "dep_t6_intervention": "Intervention",
          "dep_t1_pouvoirs_publics": "Autres (pouvoirs publics, opérations financières)",
          "dep_t7_operations_financieres": "Autres (pouvoirs publics, opérations financières)"}

with onglet["Dépenses"]:
    st.subheader("Dépenses nettes du budget général par nature")
    st.caption("Titres budgétaires. Les interventions regroupent les transferts aux ménages, entreprises et collectivités.")
    dep = requete(f"""
        SELECT annee, code, execution / 1e9 AS md FROM v_budget_annuel
        WHERE code IN ({", ".join("?" * len(TITRES))}) AND execution IS NOT NULL
    """, *TITRES)
    dep["serie"] = dep["code"].map(TITRES)
    dep = dep.groupby(["annee", "serie"], as_index=False)["md"].sum()
    graphique_empile(dep, list(dict.fromkeys(TITRES.values())))

    st.subheader("Prélèvements sur recettes")
    psr = requete("""
        SELECT annee, libelle AS serie, execution / 1e9 AS md FROM v_budget_annuel
        WHERE code IN ('psr_collectivites', 'psr_ue') AND execution IS NOT NULL
    """)
    graphique_empile(psr, ["PSR collectivités", "PSR Union européenne"])

    st.subheader(f"Suivi mensuel {annee_courante}")
    lignes_dep = {"dep_bg_total": "Dépenses nettes du budget général",
                  **{k: val for k, val in TITRES.items() if not val.startswith("Autres")},
                  "psr_total": "Prélèvements sur recettes"}
    choix = st.selectbox("Dépense", list(lignes_dep), format_func=lignes_dep.get, key="dep")
    graphique_cumul(choix)

# ---------------------------------------------------------------------------
# Prévu vs réalisé
# ---------------------------------------------------------------------------
with onglet["Prévu vs réalisé"]:
    lignes = requete("SELECT DISTINCT code, libelle, ordre FROM v_budget_annuel WHERE lfi IS NOT NULL ORDER BY ordre")
    libelles = dict(zip(lignes["code"], lignes["libelle"]))
    choix = st.selectbox("Ligne budgétaire", list(libelles), format_func=libelles.get, key="pvr")
    df = requete("""
        SELECT annee, lfi / 1e9 AS lfi, derniere_lfr / 1e9 AS lfr, execution / 1e9 AS execution
        FROM v_budget_annuel WHERE code = ? ORDER BY annee
    """, choix)
    derniere_lfi = int(df.dropna(subset=["lfi"])["annee"].max())
    if derniere_lfi < annee_courante:
        st.info(f"La LFI {annee_courante} n'est pas encore publiée dans le jeu de données DGFiP "
                f"(dernière disponible : {derniere_lfi}).")

    st.subheader(f"{libelles[choix]} : prévision et exécution")
    fig = go.Figure()
    for col, nom, couleur in [("execution", "Exécution", SERIES[0]), ("lfi", "Loi de finances initiale", SERIES[1]),
                              ("lfr", "Dernière loi rectificative", SERIES[2])]:
        d = df.dropna(subset=[col])
        fig.add_scatter(x=d["annee"], y=d[col], name=nom, mode="lines+markers",
                        line=dict(color=couleur, width=2),
                        marker=dict(size=8, color=couleur, line=dict(color=C["surface"], width=2)),
                        hovertemplate="%{y:,.1f} Md€")
    fig.update_xaxes(dtick=1)
    afficher(habiller(fig, 380))

    st.subheader("Écart entre l'exécution et la loi de finances initiale")
    st.caption("Bleu : exécution supérieure à la LFI ; rouge : inférieure. Pour le solde, un écart positif "
               "signifie un déficit moins élevé que prévu ; pour une dépense, un dépassement.")
    ecart = df.dropna(subset=["lfi", "execution"]).assign(ecart=lambda d: d["execution"] - d["lfi"],
                                                          ecart_pct=lambda d: (d["execution"] / d["lfi"] - 1) * 100)
    fig = go.Figure(go.Bar(x=ecart["annee"], y=ecart["ecart"], customdata=ecart["ecart_pct"], name="",
                           marker_color=[C["hausse"] if e >= 0 else C["baisse"] for e in ecart["ecart"]],
                           hovertemplate="%{y:+,.1f} Md€ (%{customdata:+,.1f} %)"))
    fig.update_xaxes(dtick=1)
    afficher(habiller(fig, 300, legende=False),
             ecart.round(1).rename(columns={"lfi": "LFI (Md€)", "lfr": "dernière LFR (Md€)", "execution": "exécution (Md€)",
                                            "ecart": "écart exécution − LFI (Md€)", "ecart_pct": "écart (%)"}))

# ---------------------------------------------------------------------------
# Comptes de l'État (comptabilité générale)
# ---------------------------------------------------------------------------
with onglet["Comptes de l'État"]:
    st.caption("Comptabilité générale en droits constatés (Compte général de l'État) : les charges incluent "
               "amortissements et provisions, et ne se comparent pas directement aux dépenses budgétaires en caisse.")
    cr = requete("SELECT * FROM v_compte_resultat ORDER BY annee")
    bilan = requete("SELECT * FROM v_bilan ORDER BY annee")
    exercice = st.selectbox("Exercice", sorted(cr["annee"].tolist(), reverse=True), key="exercice")
    cri, bi = cr.set_index("annee"), bilan.set_index("annee")

    def delta(serie: pd.DataFrame, col: str) -> str | None:
        if exercice - 1 not in serie.index:
            return None
        return f"{md(serie.loc[exercice, col] - serie.loc[exercice - 1, col], signe=True)} sur un an"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Charges", md(cri.loc[exercice, "charges"]), delta(cri, "charges"), delta_color="inverse", border=True)
    m2.metric("Produits", md(cri.loc[exercice, "produits"]), delta(cri, "produits"), border=True)
    m3.metric("Résultat patrimonial", md(cri.loc[exercice, "resultat"]), delta(cri, "resultat"), border=True)
    m4.metric("Dettes financières", md(bi.loc[exercice, "dettes_financieres"]), delta(bi, "dettes_financieres"),
              delta_color="inverse", border=True)

    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Charges et produits")
        fig = go.Figure()
        for col, nom, couleur in [("charges", "Charges", SERIES[0]), ("produits", "Produits", SERIES[1])]:
            fig.add_scatter(x=cr["annee"], y=cr[col] / 1e9, name=nom, mode="lines",
                            line=dict(color=couleur, width=2), hovertemplate="%{y:,.1f} Md€")
            etiquette_fin(fig, cr["annee"].iloc[-1], cr[col].iloc[-1] / 1e9, nom)
        fig.update_xaxes(dtick=1)
        habiller(fig, 320)
        fig.update_layout(margin=dict(r=80))
        afficher(fig, (cr.set_index("annee") / 1e9).round(1).reset_index())
    with g2:
        st.subheader("Résultat patrimonial")
        afficher(barres_simples(cr["annee"], cr["resultat"] / 1e9, "Md€"))

    st.subheader(f"Charges par mission, {exercice}")
    missions = requete("SELECT mission, charges / 1e9 AS md FROM v_charges_par_mission WHERE annee = ? ORDER BY md DESC",
                       exercice)
    top = missions.head(15)
    graph = pd.concat([top, pd.DataFrame([{"mission": f"{len(missions) - 15} autres missions",
                                           "md": missions.iloc[15:]["md"].sum()}])])
    fig = go.Figure(go.Bar(x=graph["md"], y=graph["mission"], orientation="h", marker_color=SERIES[0], name="",
                           hovertemplate="%{x:,.1f} Md€"))
    habiller(fig, 560, legende=False, survol="closest")
    fig.update_xaxes(title="Md€", gridcolor=C["grille"], showgrid=True)
    fig.update_yaxes(title=None, autorange="reversed", showgrid=False, zeroline=False)
    afficher(fig, missions.round(2).rename(columns={"md": "charges (Md€)"}))

    st.subheader("Bilan de l'État")
    fig = go.Figure()
    for col, nom, couleur in [("actif", "Actif", SERIES[0]), ("passif", "Passif", SERIES[1]),
                              ("dettes_financieres", "dont dettes financières", SERIES[2])]:
        fig.add_scatter(x=bilan["annee"], y=bilan[col] / 1e9, name=nom, mode="lines",
                        line=dict(color=couleur, width=2), hovertemplate="%{y:,.0f} Md€")
        etiquette_fin(fig, bilan["annee"].iloc[-1], bilan[col].iloc[-1] / 1e9, nom)
    fig.update_xaxes(dtick=1)
    habiller(fig, 360)
    fig.update_layout(margin=dict(r=160))
    afficher(fig, (bilan.set_index("annee") / 1e9).round(0).reset_index())

    st.subheader(f"Compte de résultat détaillé, {exercice}")
    detail = requete("""
        SELECT categorie, poste, sous_poste, montant / 1e9 AS md FROM v_compte_resultat_postes
        WHERE annee = ? ORDER BY categorie, poste, md DESC
    """, exercice)
    st.dataframe(detail.round(2).rename(columns={"md": "montant (Md€)"}), hide_index=True)

# ---------------------------------------------------------------------------
# Qualité et sources
# ---------------------------------------------------------------------------
JEUX = {"smb": "Situations mensuelles", "lfi": "LFI", "lfr": "Dernière LFR", "execution": "Exécution (fichier des lois)",
        "execution_vs_smb": "Exécution vs SMB de décembre", "compta": "Comptabilité générale",
        "lois": "Lois de finances", "eurostat": "Eurostat (impôts, dépenses par fonction)"}

with onglet["Qualité et sources"]:
    ctl = requete("SELECT * FROM meta_controles")
    ctl["jeu"] = ctl["jeu"].map(JEUX).fillna(ctl["jeu"])
    n = ctl["statut"].value_counts()
    q1, q2, q3 = st.columns(3)
    q1.metric("Contrôles réussis", int(n.get("ok", 0)), border=True)
    q2.metric("Anomalies connues de la source", int(n.get("connue", 0)), border=True)
    q3.metric("Nouvelles alertes", int(n.get("alerte", 0)), border=True)
    if n.get("alerte", 0):
        st.warning("De nouvelles incohérences sont apparues dans les données publiées : voir le détail ci-dessous.")

    st.subheader("Contrôles de cohérence")
    resume = (ctl.assign(ok=ctl["statut"].eq("ok"), connues=ctl["statut"].eq("connue"), alertes=ctl["statut"].eq("alerte"))
              .groupby(["jeu", "controle"], as_index=False)
              .agg(verifications=("statut", "size"), ok=("ok", "sum"), connues=("connues", "sum"), alertes=("alertes", "sum")))
    st.dataframe(resume, hide_index=True)

    st.subheader("Anomalies")
    anomalies = ctl[ctl["statut"] != "ok"].copy()
    anomalies["ecart"] = [f"{nombre(e / 1e6)} M€" if u == "€" else f"{int(e)} {u}"
                          for e, u in zip(anomalies["ecart"], anomalies["unite"])]
    st.dataframe(anomalies[["statut", "jeu", "controle", "periode", "ecart", "detail", "explication"]]
                 .sort_values(["statut", "jeu", "periode"]), hide_index=True)

    st.subheader("Sources")
    sources = requete("SELECT titre, producteur, page, fichier FROM meta_sources")
    st.dataframe(sources, hide_index=True,
                 column_config={"page": st.column_config.LinkColumn("page", display_text="ouvrir"),
                                "fichier": "dernière version téléchargée"})

    st.subheader("Journal des collectes")
    journal = requete("SELECT horodatage, source, nouveau, octets, sha256 FROM meta_collectes ORDER BY horodatage DESC LIMIT 60")
    st.dataframe(journal, hide_index=True)

# ---------------------------------------------------------------------------
# Méthodologie
# ---------------------------------------------------------------------------
with onglet["Méthodologie"]:
    couverture = requete("""
        SELECT
            (SELECT max(annee) FROM stg_lois WHERE texte_code = 'lfi')          AS lois_fin,
            (SELECT min(annee) FROM stg_compta_generale)                          AS compta_debut,
            (SELECT max(annee) FROM stg_compta_generale)                          AS compta_fin,
            (SELECT min(annee) FROM v_maastricht WHERE dette_pct_pib IS NOT NULL) AS maas_debut,
            (SELECT max(annee) FROM v_maastricht WHERE dette_pct_pib IS NOT NULL) AS maas_fin,
            (SELECT min(annee) FROM v_prelevements)                               AS po_debut,
            (SELECT max(annee) FROM v_prelevements)                               AS po_fin,
            (SELECT count(*) FROM meta_controles)                                 AS nb_controles,
            (SELECT count(*) FROM ref_lignes)                                     AS nb_lignes
    """).iloc[0]

    st.markdown(f"""
Ce tableau de bord suit les recettes, les dépenses et les comptes de l'État français à partir de données
publiques, sans saisie manuelle. Les fichiers sont téléchargés tels que publiés par leurs producteurs,
conservés, puis transformés par un programme dont chaque étape est décrite ci-dessous. Les chiffres s'arrêtent
à la dernière publication disponible : l'exécution budgétaire va ici jusqu'au **{date_longue(dernier_arrete)}**.
""")

    st.subheader("Sources")
    PAGE_SMB = "https://data.economie.gouv.fr/explore/dataset/situations-mensuelles-budgetaires-series-longues/"
    st.dataframe(pd.DataFrame([
        {"source": "Situations mensuelles budgétaires (SMB), séries longues", "producteur": "DGFiP",
         "contenu": "Exécution du budget de l'État cumulée depuis le 1er janvier : solde, recettes par impôt, "
                    "dépenses par titre, prélèvements sur recettes",
         "période": f"janv. 2013 à {MOIS[dernier_arrete.month - 1]} {dernier_arrete.year}", "rythme": "mensuel",
         "lien": PAGE_SMB},
        {"source": "Textes législatifs (même jeu de données)", "producteur": "DGFiP",
         "contenu": "Montants votés en loi de finances initiale et dans la dernière loi rectificative, exécution annuelle",
         "période": f"2013 à {couverture['lois_fin']}", "rythme": "annuel", "lien": PAGE_SMB},
        {"source": "Données de comptabilité générale de l'État", "producteur": "DGFiP",
         "contenu": "Balances des comptes : bilan, compte de résultat, par mission et programme",
         "période": f"{couverture['compta_debut']} à {couverture['compta_fin']}", "rythme": "annuel",
         "lien": "https://data.economie.gouv.fr/explore/dataset/balances_des_comptes_etat/"},
        {"source": "gov_10dd_edpt1", "producteur": "Eurostat",
         "contenu": "Déficit et dette publics au sens de Maastricht (toutes administrations publiques)",
         "période": f"{couverture['maas_debut']} à {couverture['maas_fin']}", "rythme": "annuel",
         "lien": "https://ec.europa.eu/eurostat/databrowser/view/gov_10dd_edpt1/default/table"},
        {"source": "gov_10a_taxag", "producteur": "Eurostat",
         "contenu": "Impôts et cotisations sociales par administration bénéficiaire",
         "période": f"{couverture['po_debut']} à {couverture['po_fin']}", "rythme": "annuel",
         "lien": "https://ec.europa.eu/eurostat/databrowser/view/gov_10a_taxag/default/table"},
        {"source": "gov_10a_exp", "producteur": "Eurostat",
         "contenu": "Dépenses des administrations par fonction (nomenclature COFOG)",
         "période": f"{couverture['po_debut']} à {couverture['po_fin']}", "rythme": "annuel",
         "lien": "https://ec.europa.eu/eurostat/databrowser/view/gov_10a_exp/default/table"},
    ]), hide_index=True, column_config={"lien": st.column_config.LinkColumn("lien", display_text="ouvrir")})
    st.caption("Les situations mensuelles paraissent environ 5 semaines après la fin du mois. Toutes les sources sont "
               "en accès libre, sans clé d'API. La version exacte de chaque fichier utilisé figure dans l'onglet "
               "« Qualité et sources ».")

    st.subheader("Chaîne de traitement")
    st.markdown(f"""
1. **Collecte.** Chaque jour, une tâche automatique télécharge chaque source depuis l'API de
   data.economie.gouv.fr ou d'Eurostat. Les fichiers DGFiP sont repérés par leur titre plutôt que par leur
   identifiant, qui change à chaque republication.
2. **Historisation.** Le fichier est conservé tel quel, horodaté, avec son empreinte SHA-256. Un fichier identique
   au précédent n'est pas réenregistré : on garde l'historique des versions publiées, sans doublon. Chaque
   nouvelle version est inscrite au journal des collectes et archivée dans le [dépôt public du projet]({URL_DEPOT}) :
   chacun peut refaire les calculs à partir des mêmes fichiers. Si une source est indisponible, la dernière
   version téléchargée reste utilisée.
3. **Lecture.** Les particularités des fichiers sont gérées à la lecture : encodage UTF-16, compression gzip non
   signalée, séparateur « ; », virgule décimale, lignes vides. Les données Eurostat (format JSON-stat) sont
   aplaties. Tout est mis au format long : une ligne par valeur.
4. **Harmonisation.** Les libellés DGFiP sont rapprochés d'un référentiel de {couverture['nb_lignes']} lignes
   budgétaires, sans tenir compte des accents, des apostrophes ou des espaces. Quand deux fichiers se
   recouvrent (2013-2023 et 2024 à aujourd'hui), le plus récent l'emporte.
5. **Base de données.** Les données sont chargées dans une base DuckDB, entièrement reconstruite à chaque mise à
   jour à partir des fichiers conservés : le résultat est reproductible. Des vues SQL calculent les
   indicateurs affichés. La nouvelle base remplace l'ancienne d'un seul coup : le tableau de bord ne lit jamais
   une base à moitié chargée.
6. **Contrôles.** Des contrôles de cohérence sont exécutés à chaque construction (voir plus bas).
7. **Affichage.** Le tableau de bord lit la base en lecture seule. Chaque graphique donne accès à ses données
   (« Voir les données »).
""")

    st.subheader("Définitions et calculs")
    st.markdown("""
**Cumul et montant du mois.** Les situations mensuelles donnent des montants cumulés depuis le 1er janvier.
Le montant d'un mois est la différence entre deux cumuls successifs de la même année. La comparaison sur un an
rapproche le cumul d'un mois de celui du même mois de l'année précédente.

**Exécution annuelle.** Le montant exécuté d'une année est le cumul de décembre des situations mensuelles. Le
fichier des textes législatifs, qui contient aussi l'exécution, n'est utilisé qu'à défaut, car il comporte des
erreurs connues.

**Impôts bruts et nets.** L'État rend chaque année une partie des impôts encaissés (crédits de TVA remboursés,
restitutions d'impôt sur les sociétés, crédits d'impôt, dégrèvements d'impôts locaux). Impôts bruts = impôts
nets + remboursements et dégrèvements. Les données ne détaillent pas ces remboursements par impôt.

**Budget de l'État (diagramme de flux).** Les ressources sont les impôts nets, les recettes non fiscales, les
fonds de concours et, en cas de déficit, l'emprunt, égal au déficit budgétaire. Les emplois sont les dépenses par
titre et les prélèvements sur recettes versés aux collectivités et à l'Union européenne. L'excédent ou le déficit
des comptes spéciaux et des budgets annexes s'ajoute du côté correspondant.
""")
    st.markdown("**Prélèvements obligatoires par administration.** Les catégories affichées regroupent les codes "
                "de la comptabilité nationale (SEC 2010). Elles ne se recouvrent pas : leur somme égale le total "
                "des impôts et cotisations sociales.")
    st.dataframe(pd.DataFrame([
        ("TVA", "D211"),
        ("Impôts sur le revenu des ménages (IR, CSG, CRDS)", "D51A"),
        ("Cotisations sociales", "D611C + D613C"),
        ("Impôt sur les sociétés", "D51B"),
        ("Accises (énergie, tabac, alcool…)", "D214A"),
        ("Autres impôts sur les produits", "D214 − D214A"),
        ("Impôts sur les terrains et bâtiments", "D29A"),
        ("Autres impôts sur la production", "D29 − D29A"),
        ("Successions et autres impôts sur le patrimoine", "D59 + D91"),
        ("Droits de douane", "D21 − D211 − D214"),
    ], columns=["catégorie", "codes SEC 2010"]), hide_index=True)
    st.markdown("""
**Répartition par fonction.** Un impôt ne finance pas une dépense précise. Dans l'onglet « Circuits de
l'argent », l'argent reçu par chaque administration est réparti au prorata de l'ensemble de ses dépenses par
fonction (COFOG). C'est une clé de lecture, pas un fléchage. Les dépenses ne sont pas consolidées : un transfert
entre administrations (une dotation de l'État aux collectivités, par exemple) figure en « services généraux »
chez celle qui le verse.

**Comptabilité générale.** Dans la balance, les charges et l'actif sont au débit, les produits et le passif au
crédit. Le résultat patrimonial est la différence entre produits et charges ; les dettes financières sont le
poste du même nom au passif. Ces montants sont en droits constatés, avec amortissements et provisions : ils ne
se comparent pas directement aux dépenses budgétaires, comptées en caisse.

**Déficit et dette publics.** Ils couvrent toutes les administrations publiques (État, Sécurité sociale,
collectivités), au sens du traité de Maastricht, et sont repris d'Eurostat sans retraitement.
""")

    st.subheader("Contrôles de qualité")
    st.markdown(f"""
{nombre(couverture['nb_controles'], 0)} vérifications sont exécutées à chaque mise à jour :

- **identités comptables**, pour chaque mois et chaque loi de finances : recettes fiscales = somme des impôts,
  recettes nettes = fiscales + non fiscales, dépenses = somme des titres, prélèvements sur recettes =
  collectivités + Union européenne, solde = recettes − dépenses − prélèvements sur recettes + soldes des comptes
  spéciaux et des budgets annexes ;
- **concordance entre fichiers** : l'exécution annuelle du fichier des lois doit égaler le cumul de décembre des
  situations mensuelles ;
- **équilibre de la balance** de la comptabilité générale (total des débits = total des crédits) ;
- **totaux Eurostat** : la somme des catégories d'impôts et celle des fonctions retrouvent les totaux publiés ;
- **complétude** : aucun mois manquant, aucun libellé absent du référentiel.

L'écart admis est de 1 M€ pour les données DGFiP (arrondis) et de 0,5 Md€ pour les agrégats Eurostat. Un écart
ne bloque pas la mise à jour. S'il a déjà été analysé, il est classé « anomalie connue de la source », avec son
explication ; sinon, il apparaît comme nouvelle alerte. Le détail est dans l'onglet « Qualité et sources ».
""")

    st.subheader("Limites")
    st.markdown("""
- Le **solde budgétaire** (État seul, en caisse) et le **déficit public** (toutes administrations, en droits
  constatés) ne mesurent pas la même chose : l'un ne se déduit pas de l'autre.
- Les recettes de l'État ne comprennent que **sa part** des impôts partagés. Depuis 2018, une fraction croissante
  de la TVA va à la Sécurité sociale et aux collectivités : la baisse de la TVA de l'État n'est pas une baisse de
  la TVA.
- Les montants Eurostat (comptabilité nationale, champ « État et organismes centraux ») diffèrent légèrement de
  ceux du budget de l'État.
- Les producteurs peuvent réviser les données des dernières années ; les chiffres affichés sont ceux de la
  dernière publication téléchargée.
- Les sources ne sont pas corrigées : les anomalies relevées sont signalées, pas retraitées. Seule exception,
  l'exécution annuelle, prise dans les situations mensuelles de décembre plutôt que dans le fichier des lois.
""")

    st.subheader("Réutilisation")
    st.markdown("""
Les données DGFiP sont publiées sur data.economie.gouv.fr sous Licence Ouverte (Etalab) ; les données Eurostat
sont réutilisables à condition d'en citer la source. Pour reprendre les chiffres de ce tableau de bord, citer
« DGFiP et Eurostat, calculs Finances de l'État ».
""")

    st.subheader("Contribuer")
    st.markdown(f"""
Le code, les référentiels et l'archive des fichiers sources sont publics sur [GitHub]({URL_DEPOT}).

- **Une erreur, une incohérence ?** [Signalez-la]({URL_DEPOT}/issues/new) en précisant l'onglet, le chiffre
  concerné et, si possible, la source qui le contredit.
- **Une idée, une amélioration ?** Les propositions sont les bienvenues : le
  [guide de contribution]({URL_DEPOT}/blob/main/CONTRIBUTING.md) explique comment faire.
""")
    if URL_SOUTIEN:
        st.markdown("Le site est maintenu bénévolement. Votre soutien finance sa mise à jour et la création d'un "
                    "site plus complet.")
        bouton_soutien(st, width="content")
