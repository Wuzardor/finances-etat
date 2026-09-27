"""Modèles de posts : chaque modèle lit la base et renvoie un post (textes et visuels) à jour.

Les textes ne contiennent que des chiffres calculés et leur définition, jamais d'appréciation :
le compte doit rester crédible pour tous les bords. Un post ne dépasse pas 280 caractères
au sens de X (voir publier.longueur_x) ; les tests le vérifient sur les données réelles.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb

from . import visuels as v

URL_SITE = "https://finances-etat-fr.streamlit.app"
ESP = "\u00a0"  # espace insécable : compte pour un caractère sur X, contrairement à l'espace fine
MOIS_LONG = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
             "octobre", "novembre", "décembre"]
SOURCE_SMB = "DGFiP, situations mensuelles budgétaires"


@dataclass
class Partie:
    texte: str
    image: Path | None = None
    alt: str = ""  # texte alternatif de l'image, lu par les lecteurs d'écran


@dataclass
class Post:
    modele: str
    cle: str  # millésime des données racontées : un même modèle n'est reproposé que s'il change
    titre: str
    parties: list[Partie] = field(default_factory=list)
    inclus: list[tuple[str, str]] = field(default_factory=list)  # (modèle, clé) repris dans un fil


# ---------------------------------------------------------------------------
# Formats (texte des posts)
# ---------------------------------------------------------------------------
def nb(x: float, decimales: int = 1) -> str:
    return v.nombre(x, decimales, separateur=ESP)


def md(x: float, decimales: int = 1) -> str:
    return f"{nb(x, decimales)}{ESP}Md€"


def pc(x: float, decimales: int = 0) -> str:
    return f"{nb(x, decimales)}{ESP}%"


def variation(n: float, n1: float) -> str:
    x = (n / n1 - 1) * 100
    return f"{'+' if x >= 0 else '−'}{pc(abs(x), 1)}"


# ---------------------------------------------------------------------------
# Accès aux données (montants en Md€)
# ---------------------------------------------------------------------------
def derniere_annee_budget(con: duckdb.DuckDBPyConnection) -> int:
    return con.sql("SELECT max(annee) FROM v_budget_annuel "
                   "WHERE code = 'solde_budgetaire' AND execution IS NOT NULL").fetchone()[0]


def budget(con: duckdb.DuckDBPyConnection, annee: int) -> defaultdict:
    lignes = con.execute("SELECT code, execution / 1e9 FROM v_budget_annuel WHERE annee = ? AND execution IS NOT NULL",
                         [annee]).fetchall()
    return defaultdict(float, lignes)


def serie_budget(con: duckdb.DuckDBPyConnection, code: str, colonne: str = "execution") -> list[tuple[int, float]]:
    return con.execute(f"SELECT annee, {colonne} / 1e9 FROM v_budget_annuel "
                       f"WHERE code = ? AND {colonne} IS NOT NULL ORDER BY annee", [code]).fetchall()


def image(dossier: Path, jour: date, modele: str) -> Path:
    return dossier / f"{jour:%Y-%m-%d}-{modele}.png"


IMPOTS = ["rec_ir", "rec_is", "rec_tva", "rec_ticpe", "rec_autres_fiscales"]


# ---------------------------------------------------------------------------
# Modèles thématiques
# ---------------------------------------------------------------------------
def sur_100_euros(con, dossier: Path, jour: date) -> Post:
    an = derniere_annee_budget(con)
    b = budget(con, an)
    impots = sum(b[k] for k in IMPOTS)
    autres = (b["rec_non_fiscales"] + b["rec_fonds_concours"]
              + max(b["solde_comptes_speciaux"], 0) + max(b["solde_budgets_annexes"], 0))
    emprunt = max(-b["solde_budgetaire"], 0)
    total = impots + autres + emprunt
    p_impots, p_emprunt = round(impots / total * 100), round(emprunt / total * 100)
    p_autres = 100 - p_impots - p_emprunt
    texte = (f"D'où vient l'argent de l'État ?\n\nSur 100 € mobilisés en {an} :\n"
             f"{p_impots} € d'impôts\n{p_autres} € d'autres recettes\n{p_emprunt} € d'emprunt\n\n"
             f"Au total : {md(total)}.")
    chemin = v.proportions(
        image(dossier, jour, "sur-100-euros"), f"Sur 100 € mobilisés par l'État en {an}",
        "Ressources du budget de l'État : impôts nets des remboursements, autres recettes (non fiscales, "
        "fonds de concours) et emprunt, égal au déficit budgétaire.",
        f"{SOURCE_SMB} (exécution {an})",
        [("d'impôts", p_impots, v.BLEU), ("d'autres recettes", p_autres, v.GRIS), ("d'emprunt", p_emprunt, v.ORANGE)])
    alt = (f"Sur 100 € mobilisés par l'État en {an} : {p_impots} € viennent des impôts, "
           f"{p_autres} € d'autres recettes et {p_emprunt} € de l'emprunt.")
    return Post("sur_100_euros", str(an), f"Sur 100 € mobilisés par l'État ({an})", [Partie(texte, chemin, alt)])


def impots_rendus(con, dossier: Path, jour: date) -> Post:
    an = derniere_annee_budget(con)
    b = budget(con, an)
    nets = sum(b[k] for k in IMPOTS)
    rendus = b["rd_impots_etat"] + b["rd_impots_locaux"]
    bruts = nets + rendus
    texte = (f"En {an}, l'État a encaissé {md(bruts)} d'impôts. Il en a rendu {md(rendus)} : crédits de TVA "
             "remboursés aux entreprises, restitutions d'impôt sur les sociétés, crédits d'impôt, dégrèvements.\n\n"
             f"Ce qu'il garde vraiment : {md(nets)}, soit {pc(nets / bruts * 100)} de ce qu'il encaisse.")
    chemin = v.cascade(
        image(dossier, jour, "impots-rendus"), f"Impôts de l'État en {an} : encaissés, rendus, gardés",
        "Les remboursements et dégrèvements (crédits de TVA, restitutions d'impôt sur les sociétés, crédits "
        "d'impôt, dégrèvements d'impôts locaux) sont rendus aux contribuables.",
        f"{SOURCE_SMB} (exécution {an})",
        [("Encaissés", 0, bruts, v.BLEU), ("Rendus aux contribuables", nets, bruts, v.GRIS),
         ("Gardés par l'État", 0, nets, v.BLEU)])
    alt = (f"En {an}, l'État a encaissé {md(bruts)} d'impôts, en a rendu {md(rendus)} aux contribuables "
           f"et en a gardé {md(nets)}.")
    return Post("impots_rendus", str(an), f"Impôts encaissés, rendus, gardés ({an})", [Partie(texte, chemin, alt)])


def tva_partagee(con, dossier: Path, jour: date) -> Post:
    df = con.sql("""
        SELECT annee, administration, sum(montant) / 1e9 AS md FROM v_prelevements
        WHERE prelevement = 'TVA' GROUP BY ALL ORDER BY annee
    """).df().pivot(index="annee", columns="administration", values="md").fillna(0)
    total = df.sum(axis=1)
    etat = df["État et organismes centraux"]
    a0, a1 = int(df.index[0]), int(df.index[-1])
    part0, part1 = etat[a0] / total[a0] * 100, etat[a1] / total[a1] * 100
    texte = (f"La TVA de l'État baisse, pas la TVA.\n\nEn {a1}, la TVA a rapporté {md(total[a1])} "
             f"(contre {md(total[a0])} en {a0}). Mais l'État et ses organismes n'en gardent plus que {pc(part1)}, "
             f"contre {pc(part0)} en {a0}. Le reste va à la Sécurité sociale ({md(df['Sécurité sociale'][a1])}) "
             f"et aux collectivités ({md(df['Collectivités locales'][a1])}).")
    ordre = [a for a in v.COULEURS_ADMIN if a in df.columns and df[a].sum() > 0]
    x = [int(a) for a in df.index]
    chemin = v.colonnes_empilees(
        image(dossier, jour, "tva-partagee"), "La TVA est de plus en plus partagée",
        "TVA perçue par chaque administration publique, en Md€, et part gardée par l'État et ses organismes.",
        "Eurostat, gov_10a_taxag (comptabilité nationale)", x,
        {("État et ses organismes" if a.startswith("État") else a): df[a].tolist() for a in ordre},
        {("État et ses organismes" if a.startswith("État") else a): v.COULEURS_ADMIN[a] for a in ordre},
        {0: f"État : {v.nombre(part0, 0)} %", len(x) - 1: f"État : {v.nombre(part1, 0)} %"})
    alt = (f"La TVA est passée de {md(total[a0])} en {a0} à {md(total[a1])} en {a1}. La part gardée par l'État "
           f"et ses organismes est passée de {pc(part0)} à {pc(part1)}, le reste allant à la Sécurité sociale "
           "et aux collectivités.")
    return Post("tva_partagee", str(a1), f"La TVA de plus en plus partagée ({a1})", [Partie(texte, chemin, alt)])


def charge_dette(con, dossier: Path, jour: date) -> Post:
    serie = serie_budget(con, "dep_t4_charge_dette")
    annees, valeurs = [a for a, _ in serie], [m for _, m in serie]
    an, dernier = annees[-1], valeurs[-1]
    i_min = min(range(len(valeurs)), key=valeurs.__getitem__)
    depenses = budget(con, an)["dep_bg_total"]
    texte = (f"La charge de la dette de l'État : {md(dernier)} en {an}, contre {md(valeurs[i_min])} "
             f"en {annees[i_min]}, son point bas depuis {annees[0]}.\n\n"
             f"C'est {pc(dernier / depenses * 100)} des dépenses nettes du budget de l'État.")
    chemin = v.colonnes(
        image(dossier, jour, "charge-dette"), "Charge de la dette de l'État",
        "Dépenses du titre 4 du budget général (charge de la dette), en Md€ par an.",
        f"{SOURCE_SMB} (exécution)", annees, valeurs, sorted({0, i_min, len(valeurs) - 1}))
    alt = (f"Charge de la dette de l'État de {annees[0]} à {an} : {md(valeurs[0])} en {annees[0]}, "
           f"point bas de {md(valeurs[i_min])} en {annees[i_min]}, {md(dernier)} en {an}.")
    return Post("charge_dette", str(an), f"Charge de la dette de l'État ({an})", [Partie(texte, chemin, alt)])


def prevu_realise(con, dossier: Path, jour: date) -> Post | None:
    lfi = dict(serie_budget(con, "solde_budgetaire", "lfi"))
    execution = dict(serie_budget(con, "solde_budgetaire", "execution"))
    annees = sorted(set(lfi) & set(execution))
    an = annees[-1]
    if lfi[an] >= 0 or execution[an] >= 0 or lfi[an - 1] >= 0 or execution[an - 1] >= 0:
        return None  # textes écrits pour des déficits
    ecart = execution[an] - lfi[an]
    texte = (f"Budget {an} : la loi de finances initiale prévoyait un déficit de {md(-lfi[an])}. "
             f"Résultat : {md(-execution[an])}, soit {md(abs(ecart))} {'de moins' if ecart > 0 else 'de plus'} "
             f"que prévu.\n\nEn {an - 1} : {md(-execution[an - 1])} réalisés pour {md(-lfi[an - 1])} prévus.")
    chemin = v.courbes(
        image(dossier, jour, "prevu-realise"), "Déficit de l'État : prévu et réalisé",
        "Solde budgétaire voté en loi de finances initiale et solde exécuté, en Md€.",
        "DGFiP, lois de finances et situations mensuelles budgétaires", annees,
        [("Prévu (LFI)", [lfi[a] for a in annees], v.ORANGE), ("Réalisé", [execution[a] for a in annees], v.BLEU)])
    alt = (f"Solde budgétaire de l'État prévu et réalisé de {annees[0]} à {an}. En {an} : "
           f"{md(lfi[an])} prévus, {md(execution[an])} réalisés.")
    return Post("prevu_realise", str(an), f"Déficit de l'État prévu et réalisé ({an})", [Partie(texte, chemin, alt)])


def dette_publique(con, dossier: Path, jour: date) -> Post:
    df = con.sql("SELECT annee, dette_pct_pib, dette / 1e9 AS md FROM v_maastricht "
                 "WHERE dette_pct_pib IS NOT NULL ORDER BY annee").df().set_index("annee")
    a0, an = int(df.index[0]), int(df.index[-1])
    rappel = f"{pc(df.loc[2019, 'dette_pct_pib'], 1)} du PIB en 2019 et " if 2019 in df.index and an > 2020 else ""
    texte = (f"Dette publique fin {an} : {pc(df.loc[an, 'dette_pct_pib'], 1)} du PIB, soit {md(df.loc[an, 'md'], 0)} "
             "(État, Sécurité sociale et collectivités, au sens de Maastricht).\n\n"
             f"Elle représentait {rappel}{pc(df.loc[a0, 'dette_pct_pib'], 1)} en {a0}.")
    x = [int(a) for a in df.index]
    reperes = [0] + ([x.index(2019)] if 2019 in x and an > 2020 else [])
    chemin = v.courbes(
        image(dossier, jour, "dette-publique"), "Dette publique, en % du PIB",
        "Dette brute consolidée de toutes les administrations publiques (État, Sécurité sociale, "
        "collectivités), au sens de Maastricht.",
        "Eurostat, gov_10dd_edpt1", x, [("Dette publique", df["dette_pct_pib"].tolist(), v.BLEU)],
        unite="% du PIB", remplir=True, reperes=reperes, format_valeur=lambda y: f"{v.nombre(y)} %")
    alt = (f"Dette publique en % du PIB de {a0} à {an} : {pc(df.loc[a0, 'dette_pct_pib'], 1)} en {a0}, "
           f"{pc(df.loc[an, 'dette_pct_pib'], 1)} en {an}.")
    return Post("dette_publique", str(an), f"Dette publique ({an})", [Partie(texte, chemin, alt)])


def deficit_public(con, dossier: Path, jour: date) -> Post | None:
    df = con.sql("SELECT annee, solde_pct_pib, solde / 1e9 AS md FROM v_maastricht "
                 "WHERE solde_pct_pib IS NOT NULL ORDER BY annee").df().set_index("annee")
    an = int(df.index[-1])
    sous_3 = df[df["solde_pct_pib"] >= -3]
    if df.loc[an, "solde_pct_pib"] >= 0 or sous_3.empty:
        return None
    a3 = int(sous_3.index[-1])
    texte = (f"Déficit public {an} : {pc(-df.loc[an, 'solde_pct_pib'], 1)} du PIB, soit {md(-df.loc[an, 'md'])} "
             "(État, Sécurité sociale et collectivités).\n\n"
             f"Dernière année sous la barre des 3 % fixée par les règles européennes : {a3} "
             f"({pc(-df.loc[a3, 'solde_pct_pib'], 1)}).")
    x = [int(a) for a in df.index]
    y = df["solde_pct_pib"].tolist()
    chemin = v.colonnes(
        image(dossier, jour, "deficit-public"), "Déficit public, en % du PIB",
        "Solde de toutes les administrations publiques au sens de Maastricht. "
        "Trait horizontal : limite de 3 % du PIB des règles européennes.",
        "Eurostat, gov_10dd_edpt1", x, y, sorted({x.index(a3), len(x) - 1}), unite="% du PIB",
        format_valeur=lambda s: f"{v.nombre(s)} %", reference=(-3, "−3 %"))
    alt = (f"Solde public en % du PIB de {x[0]} à {an} : {pc(df.loc[an, 'solde_pct_pib'], 1)} en {an}. "
           f"Dernière année au-dessus de −3 % : {a3}.")
    return Post("deficit_public", str(an), f"Déficit public ({an})", [Partie(texte, chemin, alt)])


NOMS_PRELEVEMENTS = {  # nom dans une phrase, libellé court pour le graphique
    "Cotisations sociales": ("les cotisations sociales", "Cotisations sociales"),
    "Impôts sur le revenu des ménages (IR, CSG, CRDS)": ("l'impôt sur le revenu, la CSG et la CRDS",
                                                          "Impôt sur le revenu, CSG, CRDS"),
    "TVA": ("la TVA", "TVA"),
    "Impôt sur les sociétés": ("l'impôt sur les sociétés", "Impôt sur les sociétés"),
    "Accises (énergie, tabac, alcool…)": ("les accises", "Accises (énergie, tabac, alcool)"),
    "Autres impôts sur les produits (droits de mutation, assurances…)": (
        "les autres impôts sur les produits", "Autres impôts sur les produits"),
    "Impôts sur les terrains et bâtiments (taxes foncières…)": ("les taxes foncières", "Taxes foncières"),
    "Autres impôts sur la production (dont taxes sur les salaires)": (
        "les autres impôts sur la production", "Autres impôts sur la production"),
    "Successions et autres impôts sur le patrimoine": ("les impôts sur le patrimoine", "Successions, patrimoine"),
    "Droits de douane": ("les droits de douane", "Droits de douane"),
}


def prelevements(con, dossier: Path, jour: date) -> Post:
    an = con.sql("SELECT max(annee) FROM v_prelevements").fetchone()[0]
    lignes = con.execute("SELECT prelevement, sum(montant) / 1e9 AS md FROM v_prelevements WHERE annee = ? "
                         "GROUP BY 1 ORDER BY md DESC", [an]).fetchall()
    total = sum(m for _, m in lignes)
    (p1, m1), (p2, m2), (p3, m3) = lignes[:3]
    nom = lambda p: NOMS_PRELEVEMENTS.get(p, (p.lower(), p))  # noqa: E731
    texte = (f"En {an}, {md(total, 0)} d'impôts et de cotisations sociales ont été prélevés en France.\n\n"
             f"Premier poste : {nom(p1)[0]} ({md(m1)}), devant {nom(p2)[0]} ({md(m2)}) et {nom(p3)[0]} ({md(m3)}).")
    chemin = v.barres(
        image(dossier, jour, "prelevements"), "Impôts et cotisations : les plus gros prélèvements",
        f"Prélèvements obligatoires en {an}, toutes administrations bénéficiaires confondues, en Md€.",
        "Eurostat, gov_10a_taxag (comptabilité nationale)",
        [nom(p)[1] for p, _ in lignes], [m for _, m in lignes])
    alt = (f"Prélèvements obligatoires en {an} par catégorie. Les plus importants : {nom(p1)[1]} {md(m1)}, "
           f"{nom(p2)[1]} {md(m2)}, {nom(p3)[1]} {md(m3)}.")
    return Post("prelevements", str(an), f"Les plus gros prélèvements ({an})", [Partie(texte, chemin, alt)])


TITRES = {"dep_t2_personnel": "Personnel", "dep_t6_intervention": "Interventions (aides, transferts)",
          "dep_t3_fonctionnement": "Fonctionnement", "dep_t4_charge_dette": "Charge de la dette",
          "dep_t5_investissement": "Investissement"}


def depenses_titres(con, dossier: Path, jour: date) -> Post:
    an = derniere_annee_budget(con)
    b = budget(con, an)
    titres = sorted(TITRES, key=lambda k: -b[k])
    autres = b["dep_bg_total"] - sum(b[k] for k in TITRES)
    lignes = "\n".join(f"{TITRES[k]} : {md(b[k])}" for k in titres)
    texte = f"Où vont les {md(b['dep_bg_total'])} de dépenses nettes du budget de l'État en {an} ?\n\n{lignes}"
    chemin = v.barres(
        image(dossier, jour, "depenses-titres"), f"Les dépenses de l'État en {an}",
        "Dépenses nettes du budget général par nature (titres budgétaires), en Md€. Hors prélèvements sur "
        "recettes versés aux collectivités et à l'Union européenne.",
        f"{SOURCE_SMB} (exécution {an})",
        [TITRES[k] for k in titres] + ["Autres"], [b[k] for k in titres] + [autres])
    alt = f"Dépenses nettes du budget de l'État en {an} par nature : " + ", ".join(
        f"{TITRES[k].lower()} {md(b[k])}" for k in titres) + "."
    return Post("depenses_titres", str(an), f"Les dépenses de l'État par nature ({an})", [Partie(texte, chemin, alt)])


PRECISIONS_FONCTIONS = {"Protection sociale": "protection sociale (retraites, famille, chômage…)",
                        "Services généraux": "services généraux (dont intérêts de la dette)",
                        "Affaires économiques": "affaires économiques (transports, énergie, aides…)"}


def depenses_fonctions(con, dossier: Path, jour: date) -> Post:
    an = con.sql("SELECT max(annee) FROM stg_eurostat_cofog WHERE sector = 'S13'").fetchone()[0]
    lignes = con.execute("""
        SELECT f.fonction, d.valeur / 1e3 AS md FROM stg_eurostat_cofog d JOIN ref_fonctions f USING (cofog99)
        WHERE d.annee = ? AND d.sector = 'S13' ORDER BY md DESC
    """, [an]).fetchall()
    total = sum(m for _, m in lignes)
    detail = "\n".join(f"{round(m / total * 100)} € {PRECISIONS_FONCTIONS.get(f, f.lower())}" for f, m in lignes[:5])
    texte = f"Sur 100 € de dépenses publiques en {an} (toutes administrations) :\n\n{detail}"
    chemin = v.barres(
        image(dossier, jour, "depenses-fonctions"), "Où vont les dépenses publiques ?",
        f"Dépenses de toutes les administrations publiques par fonction en {an}, en Md€ "
        f"(total : {v.nombre(total, 0)} Md€).",
        "Eurostat, gov_10a_exp (nomenclature COFOG)", [f for f, _ in lignes], [m for _, m in lignes])
    alt = f"Dépenses publiques en {an} par fonction : " + ", ".join(f"{f.lower()} {md(m)}" for f, m in lignes) + "."
    return Post("depenses_fonctions", str(an), f"Les dépenses publiques par fonction ({an})",
                [Partie(texte, chemin, alt)])


def recettes_impots(con, dossier: Path, jour: date) -> Post:
    series = {code: dict(serie_budget(con, code)) for code in ("rec_ir", "rec_is", "rec_tva")}
    an = max(series["rec_ir"])
    a0 = an - 6
    ir, is_, tva = series["rec_ir"], series["rec_is"], series["rec_tva"]
    fin = ("\n\nLa TVA de l'État recule car elle est partagée avec la Sécurité sociale et les collectivités."
           if tva[an] < tva[a0] else "")
    texte = (f"Recettes fiscales nettes de l'État, {a0} → {an} :\n\n"
             f"Impôt sur le revenu : {nb(ir[a0])} → {md(ir[an])}\n"
             f"Impôt sur les sociétés : {nb(is_[a0])} → {md(is_[an])}\n"
             f"TVA (part de l'État) : {nb(tva[a0])} → {md(tva[an])}{fin}")
    annees = sorted(ir)
    chemin = v.courbes(
        image(dossier, jour, "recettes-impots"), "Les grands impôts de l'État",
        "Recettes fiscales nettes de l'État par impôt, en Md€. Pour la TVA, part revenant à l'État seulement.",
        f"{SOURCE_SMB} (exécution)", annees,
        [("TVA", [tva.get(a) for a in annees], v.VERT), ("Impôt sur les sociétés", [is_.get(a) for a in annees], v.ORANGE),
         ("Impôt sur le revenu", [ir.get(a) for a in annees], v.BLEU)])
    alt = (f"Recettes nettes de l'État de {annees[0]} à {an} : impôt sur le revenu {md(ir[an])} en {an}, "
           f"impôt sur les sociétés {md(is_[an])}, TVA (part de l'État) {md(tva[an])}.")
    return Post("recettes_impots", str(an), f"Les grands impôts de l'État ({a0}-{an})", [Partie(texte, chemin, alt)])


# ---------------------------------------------------------------------------
# Point mensuel et fil de lancement
# ---------------------------------------------------------------------------
def point_mensuel(con, dossier: Path, jour: date) -> Post:
    arrete = con.sql("SELECT max(date_arrete) FROM stg_smb").fetchone()[0]
    an, mois = arrete.year, arrete.month
    cumul = defaultdict(float, {(c, a): m for c, a, m in con.execute("""
        SELECT code, annee, cumul / 1e9 FROM v_execution_mensuelle
        WHERE mois = ? AND annee IN (?, ?) AND code IN ('solde_budgetaire', 'rec_bg_nettes', 'dep_bg_total')
    """, [mois, an, an - 1]).fetchall()})
    solde, solde1 = cumul[("solde_budgetaire", an)], cumul[("solde_budgetaire", an - 1)]
    fin_mois = f"fin {MOIS_LONG[mois - 1]}"
    if solde < 0 and solde1 < 0:
        tete = f"déficit cumulé de {md(-solde)}, contre {md(-solde1)} {fin_mois} {an - 1}"
    else:
        tete = f"solde cumulé de {md(solde)}, contre {md(solde1)} {fin_mois} {an - 1}"
    texte = (f"Budget de l'État à {fin_mois} {an} : {tete}.\n\n"
             f"Recettes nettes : {md(cumul[('rec_bg_nettes', an)])} "
             f"({variation(cumul[('rec_bg_nettes', an)], cumul[('rec_bg_nettes', an - 1)])} sur un an)\n"
             f"Dépenses nettes : {md(cumul[('dep_bg_total', an)])} "
             f"({variation(cumul[('dep_bg_total', an)], cumul[('dep_bg_total', an - 1)])})")
    lignes = con.execute("""
        SELECT annee, mois, cumul / 1e9 FROM v_execution_mensuelle
        WHERE code = 'solde_budgetaire' AND annee >= ? ORDER BY annee, mois
    """, [an - 2]).fetchall()
    series = []
    for annee, couleur in [(an - 2, v.GRIS_CLAIR), (an - 1, v.GRIS), (an, v.BLEU)]:
        par_mois = {m: c for a, m, c in lignes if a == annee}
        series.append((str(annee), [par_mois.get(m) for m in range(1, 13)], couleur))
    chemin = v.courbes(
        image(dossier, jour, "point-mensuel"), f"Solde de l'État à {fin_mois} {an}",
        "Solde budgétaire cumulé depuis le 1er janvier, en Md€. Le déficit se creuse en cours d'année : "
        "on le compare à la même date des années précédentes.",
        f"{SOURCE_SMB} ({fin_mois} {an})", list(range(1, 13)), series, etiquettes_x=v.MOIS)
    alt = (f"Solde budgétaire cumulé de l'État mois par mois en {an - 2}, {an - 1} et {an} : "
           f"{md(solde)} à {fin_mois} {an}, contre {md(solde1)} un an plus tôt.")
    return Post("point_mensuel", f"{an}-{mois:02d}", f"Point mensuel : le budget à {fin_mois} {an}",
                [Partie(texte, chemin, alt)])


FIL_LANCEMENT = [sur_100_euros, impots_rendus, tva_partagee, charge_dette]


def lancement(con, dossier: Path, jour: date) -> Post:
    """Fil de présentation du site. Seul post qui contient un lien : un lien coûte plus cher via l'API de X."""
    posts = [modele(con, dossier, jour) for modele in FIL_LANCEMENT]
    controles = con.sql("SELECT count(*) FROM meta_controles").fetchone()[0]
    debut = Partie("J'ai construit un tableau de bord gratuit et indépendant sur les finances de l'État, mis à jour "
                   "automatiquement à partir des données publiques (DGFiP, Eurostat).\n\n"
                   "Ce qu'on y apprend, en quelques chiffres 🧵")
    fin = Partie(f"Tout est sourcé et vérifié à chaque mise à jour par {nb(controles, 0)} contrôles de cohérence. "
                 "Le code et les données sont publics.\n\nGratuit, sans publicité et sans lien avec l'administration : "
                 f"{URL_SITE}")
    return Post("lancement", "1", "Fil de lancement du compte", [debut, *(p.parties[0] for p in posts), fin],
                inclus=[(p.modele, p.cle) for p in posts])


# Ordre de proposition des modèles thématiques. Les quatre premiers du fil de lancement
# viennent en dernier : ils viennent d'être publiés dans le fil.
CATALOGUE = [prevu_realise, depenses_fonctions, prelevements, dette_publique, recettes_impots, deficit_public,
             depenses_titres, sur_100_euros, impots_rendus, tva_partagee, charge_dette]
