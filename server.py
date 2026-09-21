#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import random
import re
import sqlite3
import sys
import urllib.error
import urllib.request
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


WRITING_PROMPTS = [
    {
        "title": "The Value of Lifelong Learning",
        "prompt": "Write an essay on the value of lifelong learning. You should explain why it matters and how college students can develop this habit.",
    },
    {
        "title": "Responsible Use of Artificial Intelligence",
        "prompt": "Write an essay on the responsible use of artificial intelligence in education. Give reasons and examples to support your view.",
    },
    {
        "title": "Learning from Setbacks",
        "prompt": "Write an essay on the importance of learning from setbacks. You should state your opinion and support it with examples.",
    },
    {
        "title": "Community Service",
        "prompt": "Write an essay discussing why university students should participate in community service and what they can gain from it.",
    },
    {
        "title": "Information Overload",
        "prompt": "Write an essay on how young people can deal with information overload in the digital age.",
    },
]


def local_writing_evaluation(content: str) -> dict:
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", content)
    sentences = [part.strip() for part in re.split(r"[.!?]+", content) if part.strip()]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
    lower = content.lower()
    connectors = [
        term for term in ["however", "therefore", "moreover", "furthermore", "in addition", "for example", "in conclusion", "firstly", "secondly", "consequently"]
        if term in lower
    ]
    unique_ratio = len({word.lower() for word in words}) / max(1, len(words))
    average_sentence = len(words) / max(1, len(sentences))
    length_score = max(8, 28 - abs(len(words) - 180) // 5)
    structure_score = min(24, 10 + len(paragraphs) * 3 + len(connectors) * 2)
    language_score = min(27, int(12 + unique_ratio * 16 + (3 if 10 <= average_sentence <= 25 else 0)))
    content_score = min(21, 12 + min(5, len(sentences) // 2) + (4 if len(words) >= 120 else 0))
    score = int(max(35, min(92, length_score + structure_score + language_score + content_score)))
    issues = []
    suggestions = []
    if len(words) < 150:
        issues.append(f"全文约 {len(words)} 词，论证可能不够充分。")
        suggestions.append("补充一个具体例子，并解释它如何支持中心观点。")
    elif len(words) > 220:
        issues.append(f"全文约 {len(words)} 词，考试中可能挤压检查时间。")
        suggestions.append("删除重复论点，将全文控制在 160-200 词左右。")
    if len(paragraphs) < 3:
        issues.append("段落层次不明显。")
        suggestions.append("采用引言、主体、结论至少三段的结构。")
    if len(connectors) < 2:
        issues.append("显性逻辑连接较少。")
        suggestions.append("在转折、递进和结论处自然加入连接词。")
    if average_sentence > 27:
        issues.append("平均句长偏长，容易产生粘连句。")
        suggestions.append("把较长句拆分，并检查每个从句的谓语。")
    if not issues:
        issues.append("本地检查未发现明显的结构性问题。")
        suggestions.append("继续检查冠词、单复数和动词时态等细节。")
    return {
        "score": score,
        "source": "local",
        "summary": "本地评分侧重字数、结构、词汇变化和逻辑标记；配置 AI 后可获得逐句语法反馈。",
        "dimensions": {
            "content": content_score,
            "organization": structure_score,
            "language": language_score,
            "task_completion": length_score,
        },
        "issues": issues,
        "suggestions": suggestions,
        "revised_essay": "",
        "useful_phrases": connectors[:5],
        "word_count": len(words),
    }


def extract_json_object(value: str) -> dict:
    value = value.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("AI 未返回 JSON")
    return json.loads(value[start:end + 1])


def ai_writing_evaluation(title: str, prompt: str, content: str, config: dict) -> dict:
    ai = config.get("ai", {})
    base_url = str(ai.get("base_url", "")).rstrip("/")
    api_key = str(ai.get("api_key", ""))
    if not base_url or not api_key:
        raise ValueError("AI 未配置")
    instruction = """You are a strict CET-6 writing examiner. Score the essay on a 0-100 scale. Return JSON only with: score (integer), summary (Chinese), dimensions (object containing content, organization, language, task_completion, each 0-25), issues (Chinese string array), suggestions (Chinese string array), revised_essay (English), useful_phrases (English string array). Do not use markdown."""
    body = json.dumps({
        "model": ai.get("model", "gpt-4o-mini"),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": f"Title: {title}\nPrompt: {prompt}\nEssay:\n{content}"},
        ],
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=int(ai.get("timeout_seconds", 60))) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise ValueError(f"AI 接口返回 {error.code}: {detail}") from error
    result = extract_json_object(payload["choices"][0]["message"]["content"])
    result["source"] = "ai"
    result["word_count"] = len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", content))
    result["score"] = max(0, min(100, int(result.get("score", 0))))
    return result


def evaluate_writing(payload: dict) -> dict:
    title = str(payload.get("title", "Untitled essay")).strip()[:160]
    prompt = str(payload.get("prompt", "")).strip()[:2000]
    content = str(payload.get("content", "")).strip()
    if len(re.findall(r"[A-Za-z]+", content)) < 20:
        raise ApiError(400, "作文至少需要 20 个英文单词")
    config = read_config()
    warning = ""
    if config.get("ai", {}).get("api_key"):
        try:
            result = ai_writing_evaluation(title, prompt, content, config)
        except (ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as error:
            result = local_writing_evaluation(content)
            warning = f"AI 评分失败，已使用本地评分：{error}"
    else:
        result = local_writing_evaluation(content)
        warning = "未配置 API Key，本次使用本地基础评分。"
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO essays(title, prompt, content, score, feedback_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (title, prompt, content, result["score"], json.dumps(result, ensure_ascii=False), utc_now()),
        )
    return {"id": cursor.lastrowid, "warning": warning, **result}


def writing_history() -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT id, title, score, created_at FROM essays ORDER BY id DESC LIMIT 20"
        ).fetchall()
    return [dict(row) for row in rows]


def next_listening_question(requested_mode: str) -> dict:
    if requested_mode not in {"word", "sentence", "mixed"}:
        raise ApiError(400, "未知听力模式")
    mode = random.choice(["word", "sentence"]) if requested_mode == "mixed" else requested_mode
    with connect() as db:
        row = db.execute(
            """SELECT w.* FROM words w LEFT JOIN word_progress p ON p.word_id = w.id
               ORDER BY COALESCE(p.mastery, 0), RANDOM() LIMIT 1"""
        ).fetchone()
    if not row:
        raise ApiError(404, "词库为空")
    text = row["word"] if mode == "word" else row["example"]
    return {"id": row["id"], "mode": mode, "speech": text, "word_count": len(text.split())}


def word_diff(expected: str, answer: str) -> list[dict]:
    expected_words = normalize_english(expected).split()
    answer_words = normalize_english(answer).split()
    result = []
    for index, word in enumerate(expected_words):
        result.append({"word": word, "correct": index < len(answer_words) and answer_words[index] == word})
    if len(answer_words) > len(expected_words):
        result.extend({"word": word, "correct": False, "extra": True} for word in answer_words[len(expected_words):])
    return result


def check_listening_answer(payload: dict) -> dict:
    word_id = int(payload.get("id", 0))
    mode = payload.get("mode", "")
    answer = str(payload.get("answer", "")).strip()
    if mode not in {"word", "sentence"} or not answer:
        raise ApiError(400, "请填写听到的内容")
    with connect() as db:
        row = db.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        if not row:
            raise ApiError(404, "听力题不存在")
        expected = row["word"] if mode == "word" else row["example"]
        correct = normalize_english(answer) == normalize_english(expected)
        db.execute(
            "INSERT INTO listening_events(word_id, answer, correct, created_at) VALUES (?, ?, ?, ?)",
            (word_id, answer, int(correct), utc_now()),
        )
        return {
            "correct": correct, "answer": expected, "diff": word_diff(expected, answer),
            "meaning": row["meaning"], "pos": row["pos"], "phonetic": row["phonetic"],
        }


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
        if path == "/api/writing/prompts":
            self.send_json({"prompts": WRITING_PROMPTS})
            return
        if path == "/api/writing/history":
            self.send_json({"essays": writing_history()})
            return
        if path == "/api/listening/next":
            mode = query.get("mode", ["mixed"])[0]
            self.send_json(next_listening_question(mode))
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
        if path == "/api/writing/evaluate":
            self.send_json(evaluate_writing(payload))
            return
        if path == "/api/listening/answer":
            self.send_json(check_listening_answer(payload))
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
