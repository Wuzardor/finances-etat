# Posts X automatiques

Les posts du compte X sont écrits et illustrés automatiquement à partir des données du site.
Rien ne part sans validation humaine.

```
 collecte quotidienne ──► « Posts X à valider »  ──► ticket GitHub ──► étiquette « valide » ──► « Publication sur X »
 (mise-a-jour.yml)          (posts-x.yml)             à relire          (le mainteneur)           (publication-x.yml)
```

## Ce qui est proposé

- **Le fil de lancement**, une seule fois, avant tout le reste.
- **Le point mensuel**, dès qu'une nouvelle situation mensuelle budgétaire paraît.
- **Un post thématique le lundi et le jeudi**, tant qu'il y a moins de 3 posts en attente :
  prévu et réalisé, dépenses par fonction, prélèvements, dette, déficit, grands impôts…
  Un thème n'est reproposé que si ses données ont changé (et au moins 4 semaines après), ou au bout de 6 mois.

Les textes sont dans [finances_etat/promo/posts.py](../finances_etat/promo/posts.py), les graphiques dans
[visuels.py](../finances_etat/promo/visuels.py). Ils ne contiennent que des chiffres et leur définition,
jamais d'appréciation. Chaque proposition est inscrite dans [journal.csv](journal.csv) ; les visuels
sont rangés dans [visuels/](visuels/).

## Valider

Chaque proposition arrive en ticket avec l'étiquette `post-x`. GitHub prévient par e-mail et dans
l'application mobile.

- **Publier** : ajouter l'étiquette `valide`. Le post part au créneau suivant, du lundi au vendredi,
  vers 8 h 30 ou 18 h 30 (heure de Paris en été), un post par créneau, le plus ancien d'abord.
- **Modifier** : éditer le texte du ticket au-dessus du trait, puis ajouter `valide`.
- **Refuser** : fermer le ticket.
- **Publier tout de suite** : onglet *Actions* → *Publication sur X* → *Run workflow*.
- **Écrire un post à la main** : *New issue* → *Post X (mainteneur)*.

Seuls les tickets créés par la tâche automatique ou par le propriétaire du dépôt peuvent être publiés.
En cas d'échec, la tâche l'explique en commentaire et retire l'étiquette `valide`.

## Clés de l'API X

La publication passe par l'API de X, facturée à l'usage : environ 0,02 $ par post avec image,
davantage pour un post contenant un lien (seul le dernier post du fil de lancement en contient).
Les quatre clés du compte se rangent dans *Settings → Secrets and variables → Actions* :
`X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`.

## En local

```bash
uv run --group promo python -m finances_etat.promo.kit                         # bannière et photo du profil
uv run --group promo python -m finances_etat.promo.publier corps.md --essai    # relire un ticket sans publier
```

Ne lancez pas `finances_etat.promo.proposer` sur la copie de travail sans raison : il inscrit ses
propositions dans le journal, qui décide de ce que la tâche automatique proposera ensuite.
