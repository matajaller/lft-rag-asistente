from answer import check_citations
from search import _fts_query, referenced_article_ids


# ---- direct article lookup ----

def test_article_references_are_normalised():
    assert referenced_article_ids("¿Qué dice el artículo 162?") == ["162"]
    assert referenced_article_ids("Explícame el art. 39-a") == ["39-A"]
    assert referenced_article_ids("¿De qué trata el artículo 3 bis?") == ["3 Bis"]
    assert referenced_article_ids("artículo 353-ñ") == ["353-Ñ"]


def test_no_false_references():
    assert referenced_article_ids("Trabajo 20 días al mes, aparte de 3 horas extra") == []


# ---- keyword query ----

def test_fts_query_drops_stopwords():
    query = _fts_query("¿Cuándo se debe pagar el aguinaldo?")
    assert '"aguinaldo"' in query
    assert '"el"' not in query and '"cuando"' not in query


# ---- citation checking ----

def test_formal_citations_are_found():
    cited, unsupported = check_citations("Son 12 días (Art. 76) y la prima es del 25% (Art. 80).", ["76", "80"])
    assert cited == ["76", "80"]
    assert unsupported == []


def test_citations_with_fractions_and_suffixes():
    cited, _ = check_citations("Permiso de paternidad (Art. 132, fracción XXVII Bis); hostigamiento (Art. 3 Bis).",
                               ["132", "3 Bis"])
    assert cited == ["132", "3 Bis"]


def test_plain_mentions_are_not_citations():
    cited, _ = check_citations("Conforme al artículo 36, el contrato termina (Art. 53).", ["53"])
    assert cited == ["53"]


def test_unretrieved_citations_are_flagged():
    _, unsupported = check_citations("El patrón puede despedir (Art. 47).", ["46", "51"])
    assert unsupported == ["47"]
