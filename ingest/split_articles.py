import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_IN = ROOT / "data" / "processed" / "lft.txt"
DB_PATH = ROOT / "data" / "lft.db"

# Lines that repeat on every page or annotate reforms; none of it is the law's content
NOISE = [re.compile(p, re.IGNORECASE) for p in [
    r"^LEY FEDERAL DEL TRABAJO$",
    r"^C[ÁA]MARA DE DIPUTADOS DEL H\. CONGRESO DE LA UNI[ÓO]N$",
    r"^Secretar[íi]a General$",
    r"^Secretar[íi]a de Servicios Parlamentarios$",
    r"^[ÚU]ltima Reforma DOF",
    r"^\d+ de \d+$",
    r"(reformad|adicionad|derogad|recorrid)[oa]s?\b.*DOF",
]]

LATIN = r"(?:Bis|Ter|Qu[áa]ter|Quintus|Quinquies|Sexies|Septies|Octies|Nonies|Decies)"

# "Artículo 47.-", "Artículo 2o.-", "Artículo 3o. Bis.-", "Artículo 15-A.-", "Artículo 512-D Bis.-",
# and the newer reformed style without the dash: "Artículo 22.", "Artículo 22 Bis."
ARTICLE = re.compile(
    r"^Art[íi]culo\s+(\d+)\s*(?:o|°|º)?\s*\.?\s*"
    rf"(-[A-ZÑ](?:\s+{LATIN})?|{LATIN}(?:\s*\d+)?)?"
    r"\s*(?:\.\s*-?|-)\s*(.*)$"   # ".-", "." or, in one typo in the official text, just "-"
)
# Upper-case only, so references like "el Título Sexto" inside the text don't match
TITULO = re.compile(r"^T[ÍI]TULO\s+[A-ZÁÉÍÓÚ]+")
CAPITULO = re.compile(r"^CAP[ÍI]TULO\s+[IVXLC]+(\s+BIS)?\b")


def article_id(number, suffix):
    """Builds ids like '22', '22 Bis', '15-A' or '512-D Bis'."""
    if not suffix:
        return number
    if suffix.startswith("-"):
        return f"{number}{suffix}"
    return f"{number} {suffix}"


def parse(text):
    articles, titulo, capitulo, pending, current = {}, None, None, None, None
    duplicates = []

    for line in (l.strip() for l in text.splitlines()):
        if not line or any(p.search(line) for p in NOISE):
            continue
        # Transitional articles come after the main body; they're about when reforms took effect
        if articles and line.upper().startswith("TRANSITORIO"):
            break

        m = ARTICLE.match(line)
        if m:
            aid = article_id(m.group(1), m.group(2))
            if aid in articles:
                # Kept with the raw line, so an unrecognised heading format is easy to spot
                duplicates.append((aid, line[:70]))
                current = None
                continue
            current = {"id": aid, "number": int(m.group(1)), "titulo": titulo,
                       "capitulo": capitulo, "lines": [m.group(3)]}
            articles[aid] = current
            pending = None
            continue

        if TITULO.match(line):
            titulo, capitulo, pending = line, None, "titulo"
            continue
        if CAPITULO.match(line):
            capitulo, pending = line, "capitulo"
            continue
        # The line after a TÍTULO / CAPÍTULO heading is its name
        if pending == "titulo":
            titulo, pending = f"{titulo}: {line}", None
            continue
        if pending == "capitulo":
            capitulo, pending = f"{capitulo}: {line}", None
            continue

        if current is not None:
            current["lines"].append(line)

    for a in articles.values():
        a["text"] = "\n".join(a.pop("lines")).strip()
        a["derogado"] = bool(re.match(r"^\(?Se deroga", a["text"], re.IGNORECASE))
    return list(articles.values()), duplicates


def save(articles):
    DB_PATH.unlink(missing_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE articles (
                id       TEXT PRIMARY KEY,
                number   INTEGER NOT NULL,
                titulo   TEXT,
                capitulo TEXT,
                text     TEXT NOT NULL,
                derogado INTEGER NOT NULL
            )""")
        conn.executemany(
            "INSERT INTO articles VALUES (:id, :number, :titulo, :capitulo, :text, :derogado)",
            articles,
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    articles, duplicates = parse(TEXT_IN.read_text(encoding="utf-8"))
    save(articles)

    numbers = {a["number"] for a in articles}
    missing = [n for n in range(1, max(numbers) + 1) if n not in numbers]
    longest = max(articles, key=lambda a: len(a["text"]))

    print(f"Articles saved: {len(articles)}  (repealed: {sum(a['derogado'] for a in articles)})")
    print(f"Highest article number: {max(numbers)}")
    print(f"Missing numbers: {len(missing)} {missing[:20]}")
    print(f"Duplicate headings skipped: {len(duplicates)}")
    for aid, raw in duplicates:
        print(f"   {aid}: {raw}")
    print(f"Longest article: {longest['id']} ({len(longest['text']):,} characters)")
    sample = next(a for a in articles if a["id"] == "47")
    print(f"\nSample, Article 47 ({sample['titulo']} / {sample['capitulo']}):\n{sample['text'][:400]}...")