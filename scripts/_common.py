"""Общие функции для скриптов (только stdlib): чтение .env, HTTP-запросы к API через nginx, вход админа."""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401 — не следуем за 301, только смотрим на код
        return None


def _ssl_context(url: str) -> ssl.SSLContext | None:
    """Самоподписанный сертификат на localhost (make certs) не пройдёт проверку — для localhost
    и при MOCK_MODE=true проверку отключаем. На VPS с Let's Encrypt проверка остаётся."""
    if not url.startswith("https://"):
        return None
    host = urllib.parse.urlparse(url).hostname or ""
    if host in ("localhost", "127.0.0.1", "nginx") or load_env().get("MOCK_MODE", "true") == "true":
        return ssl._create_unverified_context()  # noqa: S323 — осознанно, только для локального стенда
    return ssl.create_default_context()


_BASE: str | None = None


def base_url() -> str:
    """Все запросы идут ЧЕРЕЗ nginx — backend снаружи недоступен.

    dev-режим: http://localhost отдаёт сайт. secure-режим: http → 301, тогда берём https://localhost.
    Явный адрес: переменная окружения BASE_URL.
    """
    global _BASE
    if _BASE:
        return _BASE
    env = load_env()
    if env.get("BASE_URL"):
        _BASE = env["BASE_URL"].rstrip("/")
        return _BASE
    port = env.get("HTTP_PORT", "80")
    http = "http://localhost" + ("" if port == "80" else f":{port}")
    https_port = env.get("HTTPS_PORT", "443")
    https = "https://localhost" + ("" if https_port == "443" else f":{https_port}")
    try:
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(http + "/api/health", timeout=5) as resp:
            _BASE = http if resp.status == 200 else https
    except urllib.error.HTTPError as exc:
        _BASE = https if exc.code in (301, 302, 307, 308) else http
    except urllib.error.URLError:
        _BASE = https
    return _BASE


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def request(
    method: str,
    path: str,
    payload: dict | None = None,
    timeout: float = 15,
    token: str | None = None,
    form: dict | None = None,
) -> tuple[int, object]:
    """HTTP-запрос к API. Возвращает (код, JSON). На 4xx/5xx бросает ApiError.

    payload — тело JSON; form — application/x-www-form-urlencoded (логин); token — Bearer.
    """
    url = base_url() + path
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
    elif payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    else:
        data = None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if form is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    elif data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context(url)) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raise ApiError(exc.code, exc.read().decode("utf-8", "replace")) from None
    except urllib.error.URLError as exc:
        sys.exit(f"Нет связи с {url}: {exc.reason}. Стек запущен? (make dev или make secure)")


def admin_token(register_if_empty: bool = True) -> str:
    """JWT демо-админа из .env (DEMO_ADMIN_USER / DEMO_ADMIN_PASSWORD).

    Если админов в БД ещё нет — регистрирует демо-админа (как кнопка «Зарегистрироваться»).
    """
    env = load_env()
    user = env.get("DEMO_ADMIN_USER", "admin")
    password = env.get("DEMO_ADMIN_PASSWORD", "change_me_demo")
    _, check = request("GET", "/api/auth/check")
    if not check.get("has_admins"):
        if not register_if_empty:
            sys.exit("В БД нет ни одного админа. Зарегистрируйтесь на /admin или запустите make seed")
        request("POST", "/api/auth/register", {"username": user, "password": password})
        print(f"Админов не было — зарегистрирован демо-админ «{user}» (DEMO_ADMIN_USER из .env)")
    try:
        _, tok = request("POST", "/api/auth/login", form={"username": user, "password": password})
    except ApiError as exc:
        if exc.status == 401:
            sys.exit(
                f"Не удалось войти как «{user}». Админ уже зарегистрирован с другими данными: "
                "пропишите его логин и пароль в DEMO_ADMIN_USER / DEMO_ADMIN_PASSWORD в .env"
            )
        raise
    return tok["access_token"]


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
