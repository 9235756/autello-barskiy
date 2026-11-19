"""Общие функции для скриптов (только stdlib): чтение .env и HTTP-запросы к API через nginx."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Windows-консоль: печатаем UTF-8, чтобы не было «кракозябр» и UnicodeEncodeError
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def load_env() -> dict[str, str]:
    """Читает .env (или example.env) — только строки KEY=VALUE, комментарии пропускает."""
    env: dict[str, str] = {}
    for name in (".env", "example.env"):
        path = ROOT / name
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
            break
    env.update({k: v for k, v in os.environ.items() if k in env or k == "BASE_URL"})
    return env


def base_url() -> str:
    """Все запросы идут ЧЕРЕЗ nginx (http://localhost[:HTTP_PORT]) — backend снаружи недоступен."""
    env = load_env()
    if env.get("BASE_URL"):
        return env["BASE_URL"].rstrip("/")
    port = env.get("HTTP_PORT", "80")
    return "http://localhost" + ("" if port == "80" else f":{port}")


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def request(method: str, path: str, payload: dict | None = None, timeout: float = 15) -> tuple[int, object]:
    """HTTP-запрос к API. Возвращает (код, JSON). На 4xx/5xx бросает ApiError."""
    url = base_url() + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raise ApiError(exc.code, exc.read().decode("utf-8", "replace")) from None
    except urllib.error.URLError as exc:
        sys.exit(f"Нет связи с {url}: {exc.reason}. Стек запущен? (make up)")


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    """Простая текстовая таблица без сторонних библиотек."""
    cells = [[str(c) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in cells)) if cells else len(h) for i, h in enumerate(headers)]
    line = "+".join("-" * (w + 2) for w in widths)
    fmt = " | ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print(line)
    for r in cells:
        print(fmt.format(*r))
