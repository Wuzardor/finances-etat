from datetime import date, timedelta

import duckdb
import pytest

from finances_etat.config import RAW_DIR
from finances_etat.construction import construire
from finances_etat.promo import posts as P
from finances_etat.promo import proposer as R
from finances_etat.promo.publier import LIMITE, MARQUEUR_FIN, PartieLue, lire_ticket, longueur_x, verifier

LUNDI = date(2026, 9, 28)


def test_longueur_x():
    assert longueur_x("abc") == 3
    assert longueur_x("é à ç") == 5
    assert longueur_x("12 Md€") == 7  # € compte double, l'espace insécable simple
    assert longueur_x("voir https://exemple.fr/une/tres/longue/adresse") == len("voir ") + 23


def test_lire_ticket(tmp_path):
    visuel = tmp_path / "promo" / "visuels" / "2026-09-28-essai.png"
    visuel.parent.mkdir(parents=True)
    visuel.write_bytes(b"png")
    corps = ("Premier post\n\n![Texte alternatif](https://raw.githubusercontent.com/moi/depot/main/"
             "promo/visuels/2026-09-28-essai.png)\n\n---\n\nDeuxième post\n\n"
             f"{MARQUEUR_FIN}\n\n___\nConsignes, avec un --- qui ne compte pas")
    parties = lire_ticket(corps, racine=tmp_path)
    assert [p.texte for p in parties] == ["Premier post", "Deuxième post"]
    assert parties[0].images == [(visuel, "Texte alternatif")]


def test_lire_ticket_refuse_une_image_exterieure(tmp_path):
    with pytest.raises(ValueError, match="refusée"):
        lire_ticket("Texte ![x](https://exemple.fr/image.png)", racine=tmp_path)


def test_verifier_refuse_un_post_trop_long():
    with pytest.raises(ValueError, match="trop long"):
        verifier([PartieLue("€" * 141, [])])


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    if not any(RAW_DIR.glob("*/*.*")):
        pytest.skip("fichiers bruts absents")
    con = duckdb.connect(str(construire(tmp_path_factory.mktemp("base") / "base.duckdb")), read_only=True)
    yield con
    con.close()


@pytest.mark.parametrize("modele", [*P.CATALOGUE, P.point_mensuel, P.lancement], ids=lambda m: m.__name__)
def test_modeles_sur_les_donnees_reelles(base, modele, tmp_path):
    post = modele(base, tmp_path, LUNDI)
    assert post is not None
    for p in post.parties:
        assert 0 < longueur_x(p.texte) <= LIMITE, p.texte
        assert p.image is None or p.image.exists()


def test_ticket_relu_a_l_identique(base, tmp_path):
    post = P.charge_dette(base, tmp_path / "promo" / "visuels", LUNDI)
    parties = lire_ticket(R.corps_ticket(post, depot="moi/depot"), racine=tmp_path)
    assert [p.texte for p in parties] == [post.parties[0].texte]
    assert parties[0].images == [(post.parties[0].image, post.parties[0].alt)]


def test_choix_des_posts(base, tmp_path):
    modeles = lambda jour, journal, en_attente=0: [  # noqa: E731
        p.modele for p in R.choisir(base, jour, journal, en_attente, tmp_path)]
    assert modeles(LUNDI, []) == ["lancement"]

    journal = [{"date": "2026-09-27", "modele": "lancement", "cle": "1"}]
    assert modeles(LUNDI, journal) == ["point_mensuel", "prevu_realise"]

    journal += [{"date": "2026-09-28", "modele": "point_mensuel", "cle": "2026-07"},
                {"date": "2026-09-28", "modele": "prevu_realise", "cle": "2025"}]
    assert modeles(LUNDI + timedelta(days=1), journal) == []  # mardi : ni nouveau mois ni jour thématique
    assert modeles(LUNDI + timedelta(days=3), journal, en_attente=3) == []  # jeudi, mais trop de posts en attente
    assert modeles(LUNDI + timedelta(days=3), journal) == ["depenses_fonctions"]


def test_un_modele_n_est_repropose_qu_avec_des_donnees_nouvelles_ou_apres_six_mois(base, tmp_path):
    journal = [{"date": "2026-01-05", "modele": "lancement", "cle": "1"},
               {"date": "2026-01-05", "modele": "point_mensuel", "cle": "2026-07"}]
    journal += [{"date": "2026-01-05", "modele": m.__name__, "cle": m(base, tmp_path, LUNDI).cle} for m in P.CATALOGUE]
    assert R.choisir(base, date(2026, 3, 2), journal, 0, tmp_path) == []  # mêmes données, moins de 6 mois
    assert [p.modele for p in R.choisir(base, date(2026, 7, 6), journal, 0, tmp_path)] == ["prevu_realise"]


class FausseApiX:
    """Enregistre les appels et répond comme l'API de X."""

    def __init__(self):
        self.appels = []

    def post(self, url, **options):
        self.appels.append((url.rsplit("/2/", 1)[1], options.get("json")))
        identifiant = str(len(self.appels))
        return type("Reponse", (), {"status_code": 201, "text": "", "json": lambda _: {"data": {"id": identifiant}}})()


def test_publier_un_fil_avec_image(tmp_path):
    from finances_etat.promo.publier import publier
    image = tmp_path / "visuel.png"
    image.write_bytes(b"png")
    api = FausseApiX()
    ids = publier([PartieLue("Premier", [(image, "Graphique")]), PartieLue("Second", [])], api)
    assert [url for url, _ in api.appels] == ["media/upload", "media/metadata", "tweets", "tweets"]
    assert api.appels[1][1]["metadata"]["alt_text"]["text"] == "Graphique"
    assert api.appels[2][1] == {"text": "Premier", "media": {"media_ids": ["1"]}}
    assert api.appels[3][1] == {"text": "Second", "reply": {"in_reply_to_tweet_id": "3"}}
    assert ids == ["3", "4"]
