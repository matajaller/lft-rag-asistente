import json
import sqlite3
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "lft.db"
EMB_PATH = ROOT / "data" / "embeddings.npy"
IDS_PATH = ROOT / "data" / "embedding_ids.json"

MODEL_NAME = "intfloat/multilingual-e5-base"


def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT chunk_id, heading, text FROM chunks ORDER BY rowid").fetchall()
    conn.close()

    model = SentenceTransformer(MODEL_NAME)
    # e5 models expect "passage: " on documents and "query: " on questions
    texts = [f"passage: {heading}\n{text}" for _, heading, text in rows]
    vectors = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=True)

    np.save(EMB_PATH, vectors.astype(np.float32))
    IDS_PATH.write_text(json.dumps([r[0] for r in rows]), encoding="utf-8")
    print(f"Embedded {len(rows)} chunks -> {vectors.shape} saved to {EMB_PATH}")


if __name__ == "__main__":
    main()