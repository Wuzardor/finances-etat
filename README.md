# Finances de l'État

Site: https://finances-etat.streamlit.app/

Suivi des recettes et des dépenses de l'État français à partir de l'open data :
collecte automatique, base de données analytique, contrôles de cohérence et tableau de bord.

```
 Sources open data            data/raw/              DuckDB                     Streamlit
 ─────────────────            ─────────              ──────                     ─────────
 DGFiP (data.economie)  ──►   fichiers bruts   ──►   tables stg_*          ──►  tableau de bord
 Eurostat (API)               historisés,            vues v_* (analyses)        8 onglets
                              journal.csv            meta_controles (qualité)
```

Projet indépendant, sans lien avec l'administration. Pour signaler une erreur ou proposer une amélioration,
voir [CONTRIBUTING.md](CONTRIBUTING.md).

## Démarrage

Prérequis : [uv](https://docs.astral.sh/uv/) (il installe Python et les dépendances).

```bash
uv sync
uv run streamlit run app/tableau_de_bord.py
```

La première commande installe l'environnement, la seconde ouvre le tableau de bord dans le navigateur.
Les fichiers bruts étant versionnés dans `data/raw/`, la base est construite au premier lancement
(quelques secondes), puis reconstruite dès qu'un fichier brut, un référentiel ou une vue change.

Autres commandes :

```bash
uv run python -m finances_etat                # télécharge les dernières données et reconstruit la base (~1 min)
uv run python -m finances_etat --hors-ligne   # reconstruit la base sans rien télécharger
uv run --group dev pytest                     # tests
```

## Sources

| Source | Contenu | Producteur |
|---|---|---|
| [Situations mensuelles budgétaires, séries longues](https://data.economie.gouv.fr/explore/dataset/situations-mensuelles-budgetaires-series-longues/) | Exécution mensuelle cumulée depuis 2013 (solde, recettes par impôt, dépenses par titre, PSR) et prévisions LFI / dernière LFR | DGFiP |
| [Données de comptabilité générale de l'État](https://data.economie.gouv.fr/explore/dataset/balances_des_comptes_etat/) | Balances 2016-2025 : bilan, compte de résultat, par mission et programme | DGFiP |
| [gov_10dd_edpt1](https://ec.europa.eu/eurostat/databrowser/view/gov_10dd_edpt1/default/table) | Déficit et dette publics au sens de Maastricht | Eurostat |
| [gov_10a_taxag](https://ec.europa.eu/eurostat/databrowser/view/gov_10a_taxag/default/table) | Impôts et cotisations par administration bénéficiaire (État, Sécurité sociale, collectivités, UE) | Eurostat |
| [gov_10a_exp](https://ec.europa.eu/eurostat/databrowser/view/gov_10a_exp/default/table) | Dépenses publiques par fonction (COFOG) et par administration | Eurostat |

Toutes sont accessibles sans clé d'API. Le catalogue est dans [finances_etat/sources.py](finances_etat/sources.py) :
les pièces jointes DGFiP sont repérées par leur titre, car leurs identifiants changent quand le fichier est republié.

## Tableau de bord

- **Vue d'ensemble** : solde, impôts bruts, recettes nettes et dépenses cumulés comparés à l'année précédente,
  déficit et dette publics.
- **Circuits de l'argent** : diagrammes de flux. Qui encaisse chaque impôt (TVA, IR/CSG, IS, cotisations…)
  et comment chaque administration dépense (au prorata, par fonction) ; d'où vient et où va l'argent du budget de l'État,
  des impôts bruts aux dépenses, en passant par les montants rendus aux contribuables et l'emprunt.
- **Recettes** et **Dépenses** : évolution annuelle par impôt et par nature, suivi mensuel de l'année en cours.
- **Prévu vs réalisé** : LFI, dernière loi rectificative et exécution, écarts.
- **Comptes de l'État** : compte de résultat, charges par mission, bilan (comptabilité générale).
- **Qualité et sources** : résultats des contrôles, anomalies documentées, journal des collectes.
- **Méthodologie** : sources, chaîne de traitement, définitions et calculs, contrôles, limites.

## Organisation du code

```
finances_etat/
  sources.py       catalogue des sources
  collecte.py      téléchargement, historisation (SHA-256), journal
  lecture.py       lecture des formats DGFiP (UTF-16, gzip, virgule décimale) et JSON-stat Eurostat
  construction.py  construction de la base DuckDB (fichier temporaire puis remplacement atomique)
  controles.py     contrôles de cohérence
  pipeline.py      point d'entrée : python -m finances_etat
sql/vues.sql       vues analytiques (v_*) utilisées par le tableau de bord
ref/               référentiels : lignes budgétaires, fonctions, administrations, anomalies connues
app/               tableau de bord Streamlit
tests/             tests unitaires
```

La base `data/finances_etat.duckdb` est entièrement reconstruite à chaque exécution à partir de
`data/raw/`. Elle s'ouvre aussi avec n'importe quel client SQL compatible DuckDB (DBeaver, CLI `duckdb`…)
ou depuis Python, Excel ou Power BI via ODBC. Les vues principales :

| Vue | Contenu |
|---|---|
| `v_execution_mensuelle` | cumul et flux du mois, par ligne budgétaire |
| `v_cumul_vs_n1` | cumul comparé au même mois de l'année précédente |
| `v_budget_annuel` | LFI, dernière LFR et exécution par année |
| `v_prelevements` | prélèvements obligatoires par type et par administration bénéficiaire |
| `v_depenses_fonction` | dépenses de chaque administration par fonction |
| `v_compte_resultat`, `v_bilan`, `v_charges_par_mission` | comptabilité générale de l'État |
| `v_maastricht` | déficit et dette publics |

## Contrôles de qualité

À chaque construction, les identités comptables sont vérifiées (recettes fiscales = somme des impôts,
dépenses = somme des titres, solde = recettes − dépenses…), ainsi que la concordance entre fichiers,
l'équilibre de la balance comptable, la continuité des mois et le référencement de tous les libellés.
Une anomalie ne bloque pas le chargement : elle apparaît dans l'onglet « Qualité et sources ».

Anomalies de la source déjà analysées et documentées dans [ref/anomalies_connues.csv](ref/anomalies_connues.csv) :

- fichier des textes législatifs : le total des dépenses exécutées 2019-2021 est décalé d'un an
  (les situations mensuelles de décembre, cohérentes, servent de référence) ;
- LFI 2022 : les lignes « PSR collectivités » et « PSR Union européenne » contiennent les valeurs d'autres lignes ;
- LFI et LFR 2013-2016 : écarts de quelques millions d'euros liés au traitement des budgets annexes.

## Mise à jour automatique et hébergement

Les situations mensuelles paraissent environ 5 semaines après la fin du mois. La tâche GitHub Actions
[.github/workflows/mise-a-jour.yml](.github/workflows/mise-a-jour.yml) lance la collecte chaque jour.
Une collecte sans nouveauté ne crée aucun nouveau fichier brut ; sinon, les nouveaux fichiers et le journal
sont publiés dans le dépôt. On peut aussi la lancer à la main depuis l'onglet *Actions* (*Run workflow*).

Le tableau de bord est hébergé sur Streamlit Community Cloud, qui suit la branche `main` : à chaque
publication, l'application récupère les nouveaux fichiers et reconstruit sa base à la visite suivante.
La base elle-même n'est pas versionnée.

## Lecture des chiffres

- Le **solde budgétaire** concerne l'État seul, en caisse ; le **déficit public** (Maastricht) couvre toutes
  les administrations, en droits constatés. L'un ne se déduit pas de l'autre.
- **Impôts bruts et nets** : l'État encaisse environ 500 Md€ d'impôts par an (497,8 Md€ en 2025), mais en rend
  une partie (141 Md€ en 2025) sous forme de remboursements et dégrèvements : crédits de TVA remboursés aux
  entreprises, restitutions d'impôt sur les sociétés, crédits d'impôt, dégrèvements d'impôts locaux. Le budget
  raisonne en **net** (356 Md€ d'impôts en 2025) : c'est ce que l'État garde. Les données DGFiP ne détaillent pas
  les remboursements par impôt, d'où un seul total « impôts bruts ».
- Les recettes de l'État ne comprennent que **sa part** des impôts partagés : une fraction croissante de la TVA
  va à la Sécurité sociale (depuis 2019) et aux collectivités (depuis 2018, fortement depuis 2021).
- Un impôt n'est pas affecté à une dépense : la répartition « par fonction » de l'onglet Circuits est une
  clé de lecture au prorata, pas un fléchage.

## Pistes

- Exécution budgétaire par mission et programme (données PLF/RAP de data.economie.gouv.fr).
- Dette négociable de l'État (Agence France Trésor).
- Rapprochement de la comptabilité générale avec les états financiers publiés en annexe du jeu DGFiP.
- Signalement à la DGFiP des anomalies relevées dans ses fichiers.
- Site dédié, au-delà du tableau de bord Streamlit.
