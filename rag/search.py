import json
import re
import sqlite3
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "lft.db"
EMB_PATH = ROOT / "data" / "embeddings.npy"
IDS_PATH = ROOT / "data" / "embedding_ids.json"
MODEL_NAME = "intfloat/multilingual-e5-base"

# Common Spanish words that would match almost every article
STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "a", "en", "por", "para",
    "con", "sin", "que", "cual", "cuales", "cuanto", "cuantos", "cuantas", "como", "me", "mi", "mis",
    "se", "su", "sus", "es", "son", "al", "del", "lo", "le", "les", "este", "esta", "ese", "esa",
    "si", "no", "tengo", "tiene", "tienen", "puedo", "puede", "hay", "ser", "mas", "muy", "cuando",
    "donde", "despues", "antes", "yo", "nos", "ley",
}


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---- keyword search (BM25) ----

def _fts_query(question):
    """Turns a question into an FTS5 query: meaningful words, any of which may match."""
    words = re.findall(r"\w+", question.lower())
    terms = [w for w in words if len(w) > 2 and w not in STOPWORDS]
    return " OR ".join(f'"{t}"' for t in terms)


def keyword_search(question, k=5):
    """BM25 ranking over the article chunks; lower bm25 scores are better matches."""
    query = _fts_query(question)
    if not query:
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT c.chunk_id, c.article_id, c.heading, c.text,
                   bm25(chunks_fts, 0.0, 2.0, 1.0) AS score   -- heading weighted double
            FROM chunks_fts
            JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (query, k),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---- semantic search (embeddings) ----

_model, _vectors, _ids = None, None, None


def _load_embeddings():
    """Loads the model and the chunk vectors once, on first use."""
    global _model, _vectors, _ids
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
        _vectors = np.load(EMB_PATH)
        _ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))


def semantic_search(question, k=5):
    """Cosine similarity between the question and every chunk (vectors are normalised, so a dot product)."""
    _load_embeddings()
    q = _model.encode([f"query: {question}"], normalize_embeddings=True)[0]
    sims = _vectors @ q
    top = np.argsort(-sims)[:k]
    wanted = [_ids[i] for i in top]

    conn = _connect()
    try:
        marks = ",".join("?" * len(wanted))
        rows = {r["chunk_id"]: dict(r) for r in conn.execute(
            f"SELECT chunk_id, article_id, heading, text FROM chunks WHERE chunk_id IN ({marks})", wanted)}
    finally:
        conn.close()
    return [{**rows[cid], "score": float(sims[i])} for cid, i in zip(wanted, top)]


# ---- hybrid search (Reciprocal Rank Fusion) ----

def hybrid_search(question, k=5, pool=20, rrf_k=60):
    """Each list scores a chunk 1/(rrf_k + rank); chunks found by both lists rise to the top.
    Returns one result per article, represented by its best-scoring chunk."""
    scores, info = {}, {}
    for results in (keyword_search(question, pool), semantic_search(question, pool)):
        for rank, r in enumerate(results, start=1):
            scores[r["chunk_id"]] = scores.get(r["chunk_id"], 0.0) + 1.0 / (rrf_k + rank)
            info[r["chunk_id"]] = r

    out, seen = [], set()
    for cid in sorted(scores, key=scores.get, reverse=True):
        aid = info[cid]["article_id"]
        if aid in seen:
            continue
        seen.add(aid)
        out.append({**info[cid], "rrf": scores[cid]})
        if len(out) == k:
            break
    return out


def unique_articles(results, k=5):
    """Article ids in rank order, without repeats (long articles have several chunks)."""
    seen, out = set(), []
    for r in results:
        if r["article_id"] not in seen:
            seen.add(r["article_id"])
            out.append(r["article_id"])
    return out[:k]


if __name__ == "__main__":
    # Each question with the article(s) a labour lawyer would point to
    tests = [
        ("¿Cuántos días de vacaciones me tocan después de un año de trabajo?", {"76"}),
        ("¿Cuándo se debe pagar el aguinaldo?", {"87"}),
        ("¿Cuáles son las causas de despido justificado?", {"47"}),
        ("¿Cómo se pagan las horas extra?", {"67", "68"}),
        ("¿Cuánto es la prima vacacional?", {"80"}),
        ("¿Cuántos días de permiso de paternidad me dan?", {"132"}),
        ("Si me despiden sin causa, ¿qué me tienen que pagar?", {"48", "50"}),
    ]
    hits = {"keyword": 0, "semantic": 0, "hybrid": 0}
    for question, expected in tests:
        print(question)
        for name, fn in (("keyword", keyword_search), ("semantic", semantic_search), ("hybrid", hybrid_search)):
            found = unique_articles(fn(question, k=10))[:5]
            hit = bool(expected & set(found))
            hits[name] += hit
            print(f"   {name:<9} {'HIT ' if hit else 'miss'} {found}")
        print(f"   expected: {sorted(expected)}\n")
    print("Top-5 hits:", {name: f"{n}/{len(tests)}" for name, n in hits.items()})