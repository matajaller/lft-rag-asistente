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

# Common Spanish words, plus words like 'artículo' that appear in every chunk's heading
STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "a", "en", "por", "para",
    "con", "sin", "que", "cual", "cuales", "cuanto", "cuantos", "cuantas", "como", "me", "mi", "mis",
    "se", "su", "sus", "es", "son", "al", "del", "lo", "le", "les", "este", "esta", "ese", "esa",
    "si", "no", "tengo", "tiene", "tienen", "puedo", "puede", "hay", "ser", "mas", "muy", "cuando",
    "donde", "despues", "antes", "yo", "nos", "ley", "articulo", "dice", "establece", "trata",
    "explicame",
}

# "artículo 162", "art. 39-A", "artículo 3 Bis", "art 353-Ñ"
ARTICLE_REF = re.compile(
    r"art(?:[íi]culo|\.)?\s*(\d+)\s*(?:-\s*([a-zñ]))?\s*(bis|ter|qu[áa]ter)?\b", re.IGNORECASE
)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---- direct lookup for questions that name an article ----

def lookup_articles(question):
    """Returns the first chunk of every article the question names explicitly."""
    ids = []
    for number, letter, latin in ARTICLE_REF.findall(question):
        aid = number
        if letter:
            aid += f"-{letter.upper()}"
        if latin:
            aid += f" {latin.capitalize()}"
        ids.append(aid)
    if not ids:
        return []
    conn = _connect()
    try:
        found = []
        for aid in ids:
            row = conn.execute(
                "SELECT chunk_id, article_id, heading, text FROM chunks WHERE article_id = ? ORDER BY part LIMIT 1",
                (aid,),
            ).fetchone()
            if row:
                found.append(dict(row))
        return found
    finally:
        conn.close()


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


# ---- hybrid search: direct lookup first, then weighted Reciprocal Rank Fusion ----

def hybrid_search(question, k=5, pool=20, rrf_k=60, keyword_weight=0.0, rewrite=False):
    """Articles named in the question come first. The rest is fused from semantic search
    (weight 1.0) and keyword search (keyword_weight); each list adds weight / (rrf_k + rank).
    Returns one result per article, represented by its best-scoring chunk."""
    out, seen = [], set()
    for r in lookup_articles(question):
        if r["article_id"] not in seen:
            seen.add(r["article_id"])
            out.append({**r, "rrf": None})

    lists = [(semantic_search(question, pool), 1.0)]
    if rewrite:
        # A second semantic search using the law's own vocabulary; the original wording still counts,
        # so a poor rewrite can't push out results the original question found
        from rewrite import rewrite_query
        rewritten = rewrite_query(question)
        if rewritten != question:
            lists.append((semantic_search(rewritten, pool), 1.0))
    if keyword_weight > 0:
        lists.append((keyword_search(question, pool), keyword_weight))

    scores, info = {}, {}
    for results, weight in lists:
        for rank, r in enumerate(results, start=1):
            scores[r["chunk_id"]] = scores.get(r["chunk_id"], 0.0) + weight / (rrf_k + rank)
            info[r["chunk_id"]] = r

    for cid in sorted(scores, key=scores.get, reverse=True):
        if len(out) >= k:
            break
        aid = info[cid]["article_id"]
        if aid in seen:
            continue
        seen.add(aid)
        out.append({**info[cid], "rrf": scores[cid]})
    return out[:k]


def unique_articles(results, k=5):
    """Article ids in rank order, without repeats (long articles have several chunks)."""
    seen, out = set(), []
    for r in results:
        if r["article_id"] not in seen:
            seen.add(r["article_id"])
            out.append(r["article_id"])
    return out[:k]