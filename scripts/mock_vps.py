#!/usr/bin/env python3
"""Эмулятор хостинга (ihor.online / reg.ru): «арендует» VPS и выдаёт данные доступа.

Реального API-вызова нет. Скрипт генерирует запись того же вида, что хостинг
показывает в разделе «Инструкция» у виртуального сервера, и сохраняет:
  mock/vps_instance.json     — данные сервера
  mock/ssh_config_snippet    — блок для ~/.ssh/config

Повторный запуск не пересоздаёт сервер (как и в панели хостинга), если не передан --force.
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import json
import random
import secrets
import string
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOCK_DIR = ROOT / "mock"
INSTANCE = MOCK_DIR / "vps_instance.json"
SNIPPET = MOCK_DIR / "ssh_config_snippet"

TARIFFS = [
    ("Cloud-1 (1 vCPU / 1 ГБ RAM / 15 ГБ NVMe)", 290),
    ("Cloud-2 (2 vCPU / 2 ГБ RAM / 30 ГБ NVMe)", 490),
    ("Cloud-3 (2 vCPU / 4 ГБ RAM / 50 ГБ NVMe)", 890),
]


def read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        path = ROOT / "example.env"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def gen_password(n: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    # как у хостингов: буквы, цифры и пара спецсимволов, без путаницы 0/O, l/1
    alphabet = alphabet.translate(str.maketrans("", "", "0O1lI"))
    pwd = [secrets.choice(alphabet) for _ in range(n - 2)] + [secrets.choice("!#%+"), secrets.choice(string.digits)]
    random.SystemRandom().shuffle(pwd)
    return "".join(pwd)


def create_instance() -> dict:
    tariff, price = random.choice(TARIFFS)
    server_id = f"vps-{secrets.token_hex(3)}"
    # 203.0.113.0/24 — TEST-NET-3 (RFC 5737): документационный диапазон, в интернете не маршрутизируется
    ip = f"203.0.113.{random.randint(10, 250)}"
    return {
        "provider": "ihor.online (эмуляция)",
        "server_id": server_id,
        "hostname": f"{server_id}.autello.mock",
        "ip": ip,
        "os": "Ubuntu 22.04",
        "user": "root",
        "password": gen_password(),
        "ssh_port": 22,
        "status": "active",
        "tariff": tariff,
        "price_rub": price,
        "datacenter": "Москва",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def print_instruction(vps: dict) -> None:
    line = "─" * 62
    print(line)
    print(f" Хостинг: {vps['provider']}")
    print(" Раздел «Виртуальные серверы» → сервер → «Инструкция»")
    print(line)
    print(f" Сервер:        {vps['hostname']}  ({vps['server_id']})")
    print(f" Статус:        {vps['status']}")
    print(f" Тариф:         {vps['tariff']} — {vps['price_rub']} ₽/мес")
    print(f" ОС:            {vps['os']}")
    print(f" IP-адрес:      {vps['ip']}")
    print(f" Пользователь:  {vps['user']}")
    print(f" Пароль:        {vps['password']}")
    print(line)
    print(f" Подключение:   ssh {vps['user']}@{vps['ip']}")
    print(line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="пересоздать сервер")
    args = ap.parse_args()

    env = read_env()
    if env.get("MOCK_MODE", "true").lower() != "true":
        print("MOCK_MODE=false — эмулятор не нужен: арендуйте VPS у хостинга и впишите данные в .env")
        return 0

    MOCK_DIR.mkdir(exist_ok=True)
    if INSTANCE.exists() and not args.force:
        vps = json.loads(INSTANCE.read_text(encoding="utf-8"))
        print(f"Сервер уже «арендован» ранее ({INSTANCE.relative_to(ROOT)}). Пересоздать: --force\n")
    else:
        vps = create_instance()
        INSTANCE.write_text(json.dumps(vps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        INSTANCE.chmod(0o600)

    key = env.get("VPS_SSH_KEY_PATH", "~/.ssh/id_ed25519")
    SNIPPET.write_text(
        "# Добавьте в ~/.ssh/config (или сделает scripts/setup_ssh_key.sh в боевом режиме)\n"
        f"Host autello-vps\n"
        f"    HostName {vps['ip']}\n"
        f"    User {vps['user']}\n"
        f"    Port {vps['ssh_port']}\n"
        f"    IdentityFile {key}\n"
        f"    IdentitiesOnly yes\n",
        encoding="utf-8",
    )

    print_instruction(vps)
    print(f"Сохранено: {INSTANCE.relative_to(ROOT)}, {SNIPPET.relative_to(ROOT)}")
    if env.get("VPS_HOST") != vps["ip"]:
        print(f"Подсказка: в эмуляции можно вписать в .env  VPS_HOST={vps['ip']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
