#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import random
import re
import sqlite3
import sys
from datetime import date, datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "study.db"
CONFIG_PATH = ROOT / "config.yaml"
WORDS_PATH = DATA_DIR / "words.json"
HOST = "127.0.0.1"
PORT = 8765


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_scalar(value: str):
    value = value.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        return value


def read_config() -> dict:
    source = CONFIG_PATH if CONFIG_PATH.exists() else ROOT / "config.example.yaml"
    result: dict = {}
    section: dict | None = None
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            key = line[:-1].strip()
            result[key] = {}
            section = result[key]
            continue
        if section is not None and ":" in line:
            key, value = line.strip().split(":", 1)
            section[key] = parse_scalar(value)
    return result


def write_config(payload: dict) -> None:
    current = read_config()
    ai = {**current.get("ai", {}), **payload.get("ai", {})}
    study = {**current.get("study", {}), **payload.get("study", {})}
    lines = [
        "ai:",
        f"  provider: {ai.get('provider', 'openai')}",
        f"  base_url: {ai.get('base_url', 'https://api.openai.com/v1')}",
        f"  api_key: \"{str(ai.get('api_key', '')).replace(chr(34), '')}\"",
        f"  model: {ai.get('model', 'gpt-4o-mini')}",
        f"  timeout_seconds: {int(ai.get('timeout_seconds', 60))}",
        "study:",
        f"  daily_new_words: {int(study.get('daily_new_words', 30))}",
        f"  daily_reviews: {int(study.get('daily_reviews', 50))}",
        f"  daily_phrases: {int(study.get('daily_phrases', 10))}",
        f"  daily_listening: {int(study.get('daily_listening', 5))}",
        f"  exam_date: \"{str(study.get('exam_date', '')).replace(chr(34), '')}\"",
        "",
    ]
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS words (
                id INTEGER PRIMARY KEY,
                word TEXT UNIQUE NOT NULL,
                pos TEXT NOT NULL,
                meaning TEXT NOT NULL,
                phonetic TEXT DEFAULT '',
                phrases_json TEXT DEFAULT '[]',
                example TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS word_progress (
                word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
                attempts INTEGER NOT NULL DEFAULT 0,
                correct INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 0,
                unfamiliar INTEGER NOT NULL DEFAULT 0,
                mastery REAL NOT NULL DEFAULT 0,
                next_review_at TEXT,
                last_seen_at TEXT
            );
            CREATE TABLE IF NOT EXISTS practice_events (
                id INTEGER PRIMARY KEY,
                word_id INTEGER REFERENCES words(id) ON DELETE SET NULL,
                mode TEXT NOT NULL,
                result TEXT NOT NULL,
                answer TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS essays (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                prompt TEXT NOT NULL,
                content TEXT NOT NULL,
                score INTEGER,
                feedback_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS listening_events (
                id INTEGER PRIMARY KEY,
                word_id INTEGER REFERENCES words(id) ON DELETE SET NULL,
                answer TEXT DEFAULT '',
                correct INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        count = db.execute("SELECT COUNT(*) FROM words").fetchone()[0]
        if count == 0:
            records = json.loads(WORDS_PATH.read_text(encoding="utf-8"))
            db.executemany(
                """INSERT INTO words(word, pos, meaning, phonetic, phrases_json, example)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        item["word"], item["pos"], item["meaning"],
                        item.get("phonetic", ""), json.dumps(item.get("phrases", []), ensure_ascii=False),
                        item.get("example", ""),
                    )
                    for item in records
                ],
            )


VALID_MODES = {"zh-en", "en-zh", "phrase", "mixed"}


def normalize_english(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def chinese_tokens(value: str) -> set[str]:
    return {item for item in re.split(r"[；;，,、\s]+", value) if item}


def choose_mode(requested: str, phrases: list[str]) -> str:
    if requested not in VALID_MODES:
        raise ApiError(400, "未知训练模式")
    if requested != "mixed":
        return requested
    choices = ["zh-en", "en-zh"]
    if phrases:
        choices.append("phrase")
    return random.choice(choices)


def next_vocabulary_question(requested_mode: str) -> dict:
    now = utc_now()
    with connect() as db:
        rows = db.execute(
            """
            SELECT w.*, COALESCE(p.unfamiliar, 0) AS unfamiliar,
                   COALESCE(p.mastery, 0) AS mastery, p.next_review_at
            FROM words w
            LEFT JOIN word_progress p ON p.word_id = w.id
            ORDER BY
              CASE WHEN p.next_review_at IS NOT NULL AND p.next_review_at <= ? THEN 0 ELSE 1 END,
              CASE WHEN COALESCE(p.unfamiliar, 0) = 1 THEN RANDOM() % 3 ELSE 3 END,
              COALESCE(p.mastery, 0), RANDOM()
            LIMIT 12
            """,
            (now,),
        ).fetchall()
    if not rows:
        raise ApiError(404, "词库为空")
    row = random.choice(rows[: min(5, len(rows))])
    phrases = json.loads(row["phrases_json"])
    mode = choose_mode(requested_mode, phrases)
    prompt = row["meaning"] if mode in {"zh-en", "phrase"} else row["word"]
    if mode == "phrase":
        phrase = random.choice(phrases)
        prompt = f"使用“{row['meaning'].split('；')[0]}”相关表达写出词组"
        letter_count = len(phrase.replace(" ", ""))
    else:
        letter_count = len(row["word"])
    return {
        "id": row["id"],
        "mode": mode,
        "prompt": prompt,
        "pos": row["pos"],
        "letter_count": letter_count,
        "phonetic": row["phonetic"] if mode == "en-zh" else "",
        "unfamiliar": bool(row["unfamiliar"]),
    }


def question_answer(row: sqlite3.Row, mode: str) -> str:
    phrases = json.loads(row["phrases_json"])
    if mode == "phrase":
        return phrases[0] if phrases else row["word"]
    return row["meaning"] if mode == "en-zh" else row["word"]


def make_hint(answer: str, guess: str, failures: int) -> dict:
    normalized_answer = normalize_english(answer)
    normalized_guess = normalize_english(guess)
    positions = [
        index + 1
        for index, char in enumerate(normalized_answer)
        if index >= len(normalized_guess) or normalized_guess[index] != char
    ]
    if len(normalized_guess) > len(normalized_answer):
        positions.extend(range(len(normalized_answer) + 1, len(normalized_guess) + 1))
    reveal = 0 if failures < 3 else min(len(normalized_answer), failures - 2)
    pattern = "".join(char if char == " " or index < reveal else "_" for index, char in enumerate(normalized_answer))
    return {"wrong_positions": positions, "pattern": pattern, "letter_count": len(normalized_answer.replace(" ", ""))}


def check_vocabulary_answer(payload: dict) -> dict:
    word_id = int(payload.get("id", 0))
    mode = payload.get("mode", "")
    answer = str(payload.get("answer", "")).strip()
    failures = max(1, int(payload.get("failures", 1)))
    if mode not in {"zh-en", "en-zh", "phrase"} or not answer:
        raise ApiError(400, "请填写答案")
    with connect() as db:
        row = db.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        if not row:
            raise ApiError(404, "单词不存在")
        expected = question_answer(row, mode)
        if mode == "en-zh":
            expected_tokens = chinese_tokens(expected)
            answer_tokens = chinese_tokens(answer)
            is_correct = bool(answer_tokens) and any(
                any(token in item or item in token for item in expected_tokens)
                for token in answer_tokens
            )
        else:
            is_correct = normalize_english(answer) == normalize_english(expected)
        progress = db.execute("SELECT * FROM word_progress WHERE word_id = ?", (word_id,)).fetchone()
        attempts = (progress["attempts"] if progress else 0) + 1
        correct_count = (progress["correct"] if progress else 0) + int(is_correct)
        streak = (progress["streak"] if progress else 0) + 1 if is_correct else 0
        unfamiliar = progress["unfamiliar"] if progress else 0
        mastery = progress["mastery"] if progress else 0
        mastery = min(100, mastery + (12 if failures == 1 else 6)) if is_correct else max(0, mastery - 3)
        if is_correct and streak >= 3:
            unfamiliar = 0
        interval_days = min(30, max(1, 2 ** min(streak, 5))) if is_correct else 0
        next_review = datetime.fromtimestamp(datetime.now().timestamp() + interval_days * 86400, timezone.utc).isoformat()
        db.execute(
            """INSERT INTO word_progress(word_id, attempts, correct, streak, unfamiliar, mastery, next_review_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(word_id) DO UPDATE SET attempts=excluded.attempts, correct=excluded.correct,
               streak=excluded.streak, unfamiliar=excluded.unfamiliar, mastery=excluded.mastery,
               next_review_at=excluded.next_review_at, last_seen_at=excluded.last_seen_at""",
            (word_id, attempts, correct_count, streak, unfamiliar, mastery, next_review, utc_now()),
        )
        db.execute(
            "INSERT INTO practice_events(word_id, mode, result, answer, created_at) VALUES (?, ?, ?, ?, ?)",
            (word_id, mode, "correct" if is_correct else "wrong", answer, utc_now()),
        )
        response = {"correct": is_correct}
        if is_correct:
            response.update({
                "answer": expected,
                "word": row["word"], "meaning": row["meaning"], "pos": row["pos"],
                "phonetic": row["phonetic"], "example": row["example"],
            })
        elif mode == "en-zh":
            response.update({"answer": expected, "pos": row["pos"], "accepted": False})
        else:
            response["hint"] = make_hint(expected, answer, failures)
        return response


def give_up_word(payload: dict) -> dict:
    word_id = int(payload.get("id", 0))
    mode = payload.get("mode", "zh-en")
    with connect() as db:
        row = db.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        if not row:
            raise ApiError(404, "单词不存在")
        db.execute(
            """INSERT INTO word_progress(word_id, attempts, unfamiliar, mastery, next_review_at, last_seen_at)
               VALUES (?, 1, 1, 0, ?, ?)
               ON CONFLICT(word_id) DO UPDATE SET attempts=attempts+1, streak=0, unfamiliar=1,
               mastery=MAX(0, mastery-10), next_review_at=excluded.next_review_at, last_seen_at=excluded.last_seen_at""",
            (word_id, utc_now(), utc_now()),
        )
        db.execute(
            "INSERT INTO practice_events(word_id, mode, result, created_at) VALUES (?, ?, 'give_up', ?)",
            (word_id, mode, utc_now()),
        )
        return {
            "answer": question_answer(row, mode), "word": row["word"], "meaning": row["meaning"],
            "pos": row["pos"], "phonetic": row["phonetic"], "example": row["example"],
        }


def list_unfamiliar_words() -> list[dict]:
    with connect() as db:
        rows = db.execute(
            """SELECT w.word, w.pos, w.meaning, w.phonetic, p.mastery, p.last_seen_at
               FROM word_progress p JOIN words w ON w.id = p.word_id
               WHERE p.unfamiliar = 1 ORDER BY p.last_seen_at DESC"""
        ).fetchall()
    return [dict(row) for row in rows]


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


class AppHandler(BaseHTTPRequestHandler):
    server_version = "CET6Local/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError) as error:
            raise ApiError(400, "请求内容不是有效的 JSON") from error

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self.handle_api_get(parsed.path, parse_qs(parsed.query))
            else:
                self.serve_static(parsed.path)
        except ApiError as error:
            self.send_json({"error": error.message}, error.status)
        except Exception as error:
            self.send_json({"error": f"服务器错误: {error}"}, 500)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            self.handle_api_post(parsed.path, self.read_json())
        except ApiError as error:
            self.send_json({"error": error.message}, error.status)
        except Exception as error:
            self.send_json({"error": f"服务器错误: {error}"}, 500)

    def handle_api_get(self, path: str, query: dict) -> None:
        if path == "/api/health":
            self.send_json({"ok": True, "date": date.today().isoformat()})
            return
        if path == "/api/settings":
            config = read_config()
            ai = config.get("ai", {}).copy()
            ai["api_key"] = ""
            ai["has_api_key"] = bool(config.get("ai", {}).get("api_key"))
            self.send_json({"ai": ai, "study": config.get("study", {})})
            return
        if path == "/api/vocabulary/next":
            mode = query.get("mode", ["mixed"])[0]
            self.send_json(next_vocabulary_question(mode))
            return
        if path == "/api/vocabulary/unfamiliar":
            self.send_json({"words": list_unfamiliar_words()})
            return
        raise ApiError(404, "接口不存在")

    def handle_api_post(self, path: str, payload: dict) -> None:
        if path == "/api/settings":
            if payload.get("ai", {}).get("api_key") == "":
                payload.setdefault("ai", {})["api_key"] = read_config().get("ai", {}).get("api_key", "")
            write_config(payload)
            self.send_json({"ok": True})
            return
        if path == "/api/vocabulary/answer":
            self.send_json(check_vocabulary_answer(payload))
            return
        if path == "/api/vocabulary/give-up":
            self.send_json(give_up_word(payload))
            return
        raise ApiError(404, "接口不存在")

    def serve_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        candidate = (WEB_DIR / relative).resolve()
        if WEB_DIR.resolve() not in candidate.parents and candidate != WEB_DIR.resolve():
            raise ApiError(403, "禁止访问")
        if not candidate.is_file():
            candidate = WEB_DIR / "index.html"
        content = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"CET6 500 is running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
