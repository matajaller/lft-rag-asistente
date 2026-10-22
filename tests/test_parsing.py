from build_index import HARD_LIMIT, split_long
from split_articles import parse

# A small piece of law text with every heading format the real PDF contains
SAMPLE = """LEY FEDERAL DEL TRABAJO
TITULO SEGUNDO
Relaciones Individuales de Trabajo
CAPITULO IV
Rescisión de las relaciones de trabajo
Artículo 2o.- Las normas del trabajo tienden a conseguir el equilibrio.
Artículo 3o. Bis.- Para efectos de esta Ley se entiende por hostigamiento.
Artículo 15-A.- El trabajo en régimen de subcontratación.
Párrafo reformado DOF 30-11-2012
12 de 457
Artículo 22. Los mayores de quince años pueden prestar libremente sus servicios.
Artículo 22 Bis. Queda prohibido el trabajo de menores de quince años.
Artículo 353-Ñ.- Los sindicatos y las directivas de los mismos.
Artículo 512-D Bis.- Los patrones deberán efectuar las modificaciones.
Artículo 890- Se deroga.
TRANSITORIOS
Artículo 5.- Esto es un transitorio y no debe aparecer.
"""


def parsed():
    articles, duplicates = parse(SAMPLE)
    return {a["id"]: a for a in articles}, duplicates


def test_every_heading_format_is_recognised():
    articles, duplicates = parsed()
    assert set(articles) == {"2", "3 Bis", "15-A", "22", "22 Bis", "353-Ñ", "512-D Bis", "890"}
    assert duplicates == []


def test_titles_and_chapters_are_attached():
    articles, _ = parsed()
    assert articles["2"]["titulo"] == "TITULO SEGUNDO: Relaciones Individuales de Trabajo"
    assert articles["2"]["capitulo"] == "CAPITULO IV: Rescisión de las relaciones de trabajo"


def test_page_noise_and_reform_notes_are_removed():
    articles, _ = parsed()
    text = articles["15-A"]["text"]
    assert "DOF" not in text
    assert "de 457" not in text


def test_repealed_articles_are_flagged():
    articles, _ = parsed()
    assert articles["890"]["derogado"] is True
    assert articles["22"]["derogado"] is False


def test_transitional_articles_are_excluded():
    articles, _ = parsed()
    assert "5" not in articles


def test_short_articles_stay_whole():
    assert split_long("Artículo corto.") == ["Artículo corto."]


def test_long_articles_split_without_losing_text():
    text = "\n".join(f"Fracción {i}: texto de la fracción número {i}." for i in range(400))
    parts = split_long(text)
    assert len(parts) > 1
    assert all(len(p) <= HARD_LIMIT + 200 for p in parts)
    assert "\n".join(parts) == text
