import duckdb

from finances_etat.collecte import meme_contenu


def ecrire_parquet(chemin, sql: str, options: str = ""):
    duckdb.sql(f"COPY ({sql}) TO '{chemin}' (FORMAT parquet{options})")
    return chemin


LIGNES = "SELECT * FROM (VALUES (2024, 'Charges', 12.5), (2025, 'Produits', -3.0)) t(annee, categorie, solde)"


def test_parquet_memes_donnees_autre_ordre_et_compression(tmp_path):
    precedent = ecrire_parquet(tmp_path / "a.parquet", f"{LIGNES} ORDER BY annee")
    telecharge = ecrire_parquet(tmp_path / "b.parquet", f"{LIGNES} ORDER BY annee DESC", ", COMPRESSION zstd")
    assert precedent.read_bytes() != telecharge.read_bytes()
    assert meme_contenu(precedent, telecharge.read_bytes(), "parquet")


def test_parquet_donnees_modifiees(tmp_path):
    precedent = ecrire_parquet(tmp_path / "a.parquet", LIGNES)
    telecharge = ecrire_parquet(tmp_path / "b.parquet", f"SELECT annee, categorie, solde + 1 AS solde FROM ({LIGNES})")
    assert not meme_contenu(precedent, telecharge.read_bytes(), "parquet")


def test_autres_formats_compares_octet_pour_octet(tmp_path):
    precedent = tmp_path / "a.csv"
    precedent.write_bytes(b"a;b\r\n1;2\r\n")
    assert meme_contenu(precedent, b"a;b\r\n1;2\r\n", "csv")
    assert not meme_contenu(precedent, b"a;b\n1;2\n", "csv")
