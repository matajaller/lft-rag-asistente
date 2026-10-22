import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
text = (ROOT / "data" / "processed" / "lft.txt").read_text(encoding="utf-8")
lines = [l.strip() for l in text.splitlines()]

# How the headings of some missing articles actually look in the text
for n in [22, 23, 35, 43, 74, 154]:
    hits = [l for l in lines if re.match(rf"^Art[íi]culo\s+{n}\b", l)]
    print(f"{n}: {[h[:80] for h in hits[:3]]}")

# What ended up inside Article 513
conn = sqlite3.connect(ROOT / "data" / "lft.db")
a513 = conn.execute("SELECT text FROM articles WHERE id = '513'").fetchone()[0]
conn.close()
print("\n513 starts:", repr(a513[:200]))
print("\n513 ends:", repr(a513[-300:]))
print("\nArticle-like lines inside 513:", re.findall(r"\n(Art[íi]culo\s+\d+[^\n]{0,40})", a513)[:10])