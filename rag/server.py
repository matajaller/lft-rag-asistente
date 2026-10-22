import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from answer import LFT_VERSION, answer
from search import DB_PATH, _load_embeddings

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_QUESTION_CHARS = 500     # questions are short; this also stops anyone sending huge texts
MAX_ARTICLE_CHARS = 20000    # Article 513 alone is 313,000 characters


@asynccontextmanager
async def lifespan(app):
    # Load the embedding model once at startup, so the first visitor doesn't wait for it
    _load_embeddings()
    yield


app = FastAPI(title="Asistente LFT", lifespan=lifespan)


class Question(BaseModel):
    question: str


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/version")
def version():
    return {"lft_version": LFT_VERSION}


@app.post("/ask")
def ask(q: Question):
    # Plain def: FastAPI runs it in a worker thread, so a slow model call doesn't block other users
    text = q.question.strip()[:MAX_QUESTION_CHARS]
    if not text:
        raise HTTPException(status_code=400, detail="Escribe una pregunta.")
    r = answer(text)
    return {"answer": r["answer"], "cited": r["cited"], "retrieved": r["retrieved"], "truncated": r["truncated"]}


@app.get("/articulo/{article_id}")
def article(article_id: str):
    """Full text of one article, so users can check the source of every citation themselves."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, titulo, capitulo, text, derogado FROM articles WHERE LOWER(id) = LOWER(?)",
            (article_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Artículo no encontrado.")
    return {
        "id": row["id"],
        "titulo": row["titulo"],
        "capitulo": row["capitulo"],
        "text": row["text"][:MAX_ARTICLE_CHARS],
        "truncated": len(row["text"]) > MAX_ARTICLE_CHARS,
        "derogado": bool(row["derogado"]),
    }
