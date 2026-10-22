import re
from pathlib import Path

import fitz  # PyMuPDF
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_PDF = ROOT / "data" / "raw" / "LFT.pdf"
TEXT_OUT = ROOT / "data" / "processed" / "lft.txt"

# Official, always-current version published by the Cámara de Diputados
SOURCE_URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf"


def download():
    if RAW_PDF.exists():
        print(f"PDF already downloaded: {RAW_PDF}")
        return
    RAW_PDF.parent.mkdir(parents=True, exist_ok=True)
    # Some government sites reject requests without a browser-like User-Agent
    resp = requests.get(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    resp.raise_for_status()
    RAW_PDF.write_bytes(resp.content)
    print(f"Downloaded {len(resp.content) / 1e6:.1f} MB to {RAW_PDF}")


def extract():
    doc = fitz.open(RAW_PDF)
    pages = [page.get_text() for page in doc]
    doc.close()

    text = "\n".join(pages)
    TEXT_OUT.parent.mkdir(parents=True, exist_ok=True)
    TEXT_OUT.write_text(text, encoding="utf-8")

    # Sanity checks: how many article headings, and which version of the law this is
    articles = re.findall(r"^\s*Art[íi]culo\s+\d+", text, flags=re.MULTILINE)
    reform = re.search(r"[ÚU]ltima [Rr]eforma[^\n]*", text)
    print(f"Pages: {len(pages)}")
    print(f"Characters: {len(text):,}")
    print(f"Article headings found: {len(articles)}")
    print(f"Version: {reform.group(0).strip() if reform else 'not found'}")
    print(f"Text saved to {TEXT_OUT}")


if __name__ == "__main__":
    download()
    extract()