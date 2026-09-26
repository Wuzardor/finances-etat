import re
import unicodedata


def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def cle_libelle(s: str) -> str:
    """Clé de rapprochement d'un libellé : sans accents, minuscules, apostrophes et espaces unifiés.

    Les fichiers DGFiP mélangent ’ et ', et laissent parfois des espaces en fin de libellé.
    """
    s = sans_accents(s).replace("’", "'").replace(" ", " ").lower()
    return re.sub(r"\s+", " ", s).strip()
