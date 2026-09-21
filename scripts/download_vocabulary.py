#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "data" / "cet6_source.json"
DB_PATH = ROOT / "data" / "study.db"
SOURCE_URL = "https://raw.githubusercontent.com/RealKai42/qwerty-learner/master/public/dicts/CET6_T.json"


def infer_pos(translations: list[str]) -> str:
    labels = []
    for translation in translations:
        labels.extend(re.findall(r"\(([^)]+)\)", translation))
    normalized = []
    for label in labels:
        for item in re.split(r"[/,，;；\s]+", label):
            item = item.strip()
            if item and item not in normalized:
                normalized.append(item)
    return "/".join(normalized) or "word"


def clean_meaning(value: str) -> str:
    return re.sub(r"\s*\([^)]+\)\s*$", "", value).strip().replace("； ", "；")


def main() -> None:
    print(f"Downloading {SOURCE_URL}")
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "CET6-500-local-app"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            SOURCE_PATH.write_bytes(response.read())
    except urllib.error.URLError as error:
        print(f"Python TLS download failed ({error.reason}); retrying with system curl.")
        subprocess.run(
            ["curl", "--fail", "--location", "--max-time", "60", SOURCE_URL, "--output", str(SOURCE_PATH)],
            check=True,
        )
    records = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if len(records) < 2000:
        raise RuntimeError(f"Unexpected record count: {len(records)}")
    if not DB_PATH.exists():
        import sys
        sys.path.insert(0, str(ROOT))
        from server import init_db
        init_db()
    with sqlite3.connect(DB_PATH) as db:
        for item in records:
            translations = item.get("trans") or []
            word = str(item.get("name", "")).strip().lower()
            if not word or not translations:
                continue
            meaning = "；".join(clean_meaning(value) for value in translations)
            db.execute(
                """INSERT INTO words(word, pos, meaning, phonetic, phrases_json, example)
                   VALUES (?, ?, ?, ?, '[]', '')
                   ON CONFLICT(word) DO UPDATE SET
                     pos = CASE WHEN words.pos = '' THEN excluded.pos ELSE words.pos END,
                     meaning = CASE WHEN words.meaning = '' THEN excluded.meaning ELSE words.meaning END,
                     phonetic = CASE WHEN words.phonetic = '' THEN excluded.phonetic ELSE words.phonetic END""",
                (word, infer_pos(translations), meaning, item.get("usphone") or item.get("ukphone") or ""),
            )
        total = db.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    print(f"Imported {len(records)} source records. Local vocabulary now has {total} words.")
    print("Source and license details: data/SOURCE.md")


if __name__ == "__main__":
    main()
