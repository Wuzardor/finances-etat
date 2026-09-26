# Contribuer

Merci de votre intérêt pour le projet. Toute aide est bienvenue, même sans écrire de code.

## Signaler une erreur

Un chiffre vous semble faux, un graphique incohérent ? [Ouvrez un ticket](https://github.com/Wuzardor/finances-etat/issues/new) en précisant :

- l'onglet et le graphique concernés ;
- le chiffre affiché et celui que vous attendiez ;
- si possible, la source qui le contredit (lien, page d'un rapport…).

Les incohérences propres aux fichiers publiés par la DGFiP ou Eurostat sont aussi utiles : une fois analysées,
elles sont documentées dans [ref/anomalies_connues.csv](ref/anomalies_connues.csv).

## Proposer une amélioration

Pour une idée de graphique, de source ou d'explication, ouvrez d'abord un ticket pour en discuter.
Pour proposer directement une modification :

1. créez une copie du dépôt (bouton *Fork*) ;
2. faites vos changements sur une branche ;
3. ouvrez une *pull request* en expliquant ce qui change et pourquoi.

## Travailler en local

Prérequis : [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run streamlit run app/tableau_de_bord.py   # la base est construite au premier lancement
uv run python -m finances_etat                # télécharge les dernières données et reconstruit la base
uv run --group dev pytest                     # tests
```

Quelques règles :

- le code, les noms et les commentaires sont en français, comme le reste du projet ;
- les données brutes (`data/raw/`) sont mises à jour par une tâche automatique quotidienne :
  ne les modifiez pas à la main ;
- un nouveau libellé budgétaire se déclare dans [ref/lignes_budget.csv](ref/lignes_budget.csv) ;
- une nouvelle analyse passe de préférence par une vue SQL dans [sql/vues.sql](sql/vues.sql).
