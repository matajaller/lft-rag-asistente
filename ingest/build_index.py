import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "lft.db"

TARGET_CHARS = 1200   # aim for pieces about this size...
HARD_LIMIT = 2500     # ...and never let one grow past this


def split_long(text):
    """Short articles stay whole; long ones are cut into pieces at sentence ends."""
    if len(text) <= HARD_LIMIT:
        return [text]
    parts, buf, size = [], [], 0
    for line in text.split("\n"):
        buf.append(line)
        size += len(line) + 1
        if (size >= TARGET_CHARS and line.rstrip().endswith((".", ";", ":"))) or size >= HARD_LIMIT:
            parts.append("\n".join(buf))
            buf, size = [], 0
    if buf:
        parts.append("\n".join(buf))
    return parts


def build():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DROP TABLE IF EXISTS chunks")
        conn.execute("DROP TABLE IF EXISTS chunks_fts")
        conn.execute("""
            CREATE TABLE chunks (
                chunk_id   TEXT PRIMARY KEY,   -- e.g. '47#1', '513#12'
                article_id TEXT NOT NULL,
                part       INTEGER NOT NULL,
                heading    TEXT NOT NULL,
                text       TEXT NOT NULL
            )""")
        # Full-text index; remove_diacritics makes 'vacación' and 'vacacion' match
        conn.execute("""
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                chunk_id UNINDEXED, heading, text,
                tokenize = 'unicode61 remove_diacritics 2'
            )""")

        # Repealed articles only say "Se deroga", so they'd add noise to search results
        articles = conn.execute(
            "SELECT id, titulo, capitulo, text FROM articles WHERE derogado = 0 ORDER BY number, id"
        ).fetchall()

        rows = []
        for aid, titulo, capitulo, text in articles:
            heading = f"Artículo {aid}. {titulo or ''} / {capitulo or ''}"
            for i, part in enumerate(split_long(text), start=1):
                rows.append((f"{aid}#{i}", aid, i, heading, part))

        conn.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?, ?)", rows)
        conn.executemany(
            "INSERT INTO chunks_fts (chunk_id, heading, text) VALUES (?, ?, ?)",
            [(r[0], r[3], r[4]) for r in rows],
        )
        conn.commit()

        print(f"Articles indexed: {len(articles)}")
        print(f"Chunks created: {len(rows)}")
        print(f"Article 513 split into {sum(1 for r in rows if r[1] == '513')} pieces")
    finally:
        conn.close()


if __name__ == "__main__":
    build()