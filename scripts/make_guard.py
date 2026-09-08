#!/usr/bin/env python3
"""Guards for Makefile targets: keep the dev and the production stack out of each other's way.

Both compose files mount the same `psdshop_postgres` volume, so their postgres containers must
never run at the same time, and `make dev-nuke` would drop a production data directory just as
happily as a local one. Every dev-* target therefore runs `make_guard.py dev` first, every target
that can start the production stack runs `make_guard.py prod`, and both also assert that the .env
files the recipe is about to need actually exist (a missing one used to surface as an opaque
`uv`/compose error halfway through).

Cross-platform on purpose - Makefile recipes are only `cd` plus a binary call, so no shell tests,
no grep, no test(1) here either.

    python scripts/make_guard.py dev  [--docker docker] [--files a b ...]
    python scripts/make_guard.py prod [--docker docker] [--files a b ...]

Exit code 0 = go ahead, 1 = refused (with the reason and the way out on stderr).
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

# Pinned in both compose files, so the two postgres containers are told apart by name alone.
PROD_POSTGRES = "psdshop_postgres"
DEV_POSTGRES = "psdshop_postgres_dev"
# The other production services get their names from compose (psdshop_backend_1, psdshop-nginx-1).
PROD_SERVICE_RE = re.compile(r"psdshop[-_].*(backend|nginx|mail)", re.IGNORECASE)

# Touch one of these files on the machine (`make mark-prod` / `make mark-dev`) - a marker survives
# a stopped stack, unlike a container check, and is the only signal left when nothing is running.
PROD_MARKER = pathlib.Path(".production")
PROD_ENV_VALUES = {"prod", "production"}
DEV_MARKER = pathlib.Path(".development")
DEV_ENV_VALUES = {"dev", "development", "local"}

OVERRIDE = "ALLOW_DEV"
OVERRIDE_PROD = "ALLOW_PROD"


def running_containers(docker: str) -> list[str]:
    """Names of the running containers, or [] when docker is absent or not answering."""
    try:
        done = subprocess.run(
            [docker, "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def prod_reasons(docker: str) -> list[str]:
    """Why this machine looks like production."""
    reasons = []
    if PROD_MARKER.exists():
        reasons.append(f"есть маркер {PROD_MARKER} (его ставит `make mark-prod`)")
    env_value = os.environ.get("PSDSHOP_ENV", "").strip().lower()
    if env_value in PROD_ENV_VALUES:
        reasons.append(f"PSDSHOP_ENV={env_value}")
    for name in running_containers(docker):
        if name == PROD_POSTGRES:
            reasons.append(f"запущен контейнер прод-стека {name}")
        elif PROD_SERVICE_RE.search(name):
            reasons.append(f"запущен контейнер прод-стека {name}")
    return reasons


def missing_files(paths: list[str]) -> list[str]:
    return [p for p in paths if not pathlib.Path(p).is_file()]


def refuse(lines: list[str]) -> int:
    for line in lines:
        print(line, file=sys.stderr)
    return 1


def guard_dev(docker: str) -> int:
    reasons = prod_reasons(docker)
    if not reasons:
        return 0
    if os.environ.get(OVERRIDE) == "1":
        print(
            f"ВНИМАНИЕ: {OVERRIDE}=1 - dev-цель выполняется, хотя похоже на прод: {'; '.join(reasons)}"
        )
        return 0
    lines = [
        "ОТКАЗ: это похоже на продакшен, dev-цели тут запускать нельзя.",
        *(f"  - {r}" for r in reasons),
        "  dev-цели поднимают ВТОРОЙ postgres на том же volume psdshop_postgres (порча данных),",
        "  а dev-nuke удаляет этот volume целиком.",
        "  Нужен именно прод-стек? Это цели без префикса dev- (make up / migrate / manage ...).",
    ]
    if any(r.startswith("запущен контейнер") for r in reasons):
        lines.append(
            "  Это ваша машина и прод-стек поднят для проверки? Остановите его: make down."
        )
    lines.append(f"  Если вы точно знаете, что делаете: {OVERRIDE}=1 make <цель>")
    return refuse(lines)


def dev_reasons(docker: str) -> list[str]:
    """Why the production stack has no business starting here."""
    reasons = []
    if DEV_MARKER.exists():
        reasons.append(f"есть маркер {DEV_MARKER} (его ставит `make mark-dev`)")
    env_value = os.environ.get("PSDSHOP_ENV", "").strip().lower()
    if env_value in DEV_ENV_VALUES:
        reasons.append(f"PSDSHOP_ENV={env_value}")
    if DEV_POSTGRES in running_containers(docker):
        reasons.append(
            f"запущен dev-postgres ({DEV_POSTGRES}) на том же volume {PROD_POSTGRES}"
        )
    return reasons


def guard_prod(docker: str) -> int:
    reasons = dev_reasons(docker)
    if not reasons:
        return 0
    if os.environ.get(OVERRIDE_PROD) == "1":
        print(
            f"ВНИМАНИЕ: {OVERRIDE_PROD}=1 - прод-цель выполняется на dev-машине: {'; '.join(reasons)}"
        )
        return 0
    return refuse(
        [
            "ОТКАЗ: прод-стек тут поднимать нельзя.",
            *(f"  - {r}" for r in reasons),
            f"  Оба стека монтируют volume {PROD_POSTGRES}: два postgres на одном каталоге данных",
            "  портят базу, и postmaster.pid этого не ловит (у контейнеров свои PID namespace).",
            "  Локальный аналог цели - с префиксом dev- (make dev-messages, make dev-manage ...).",
            f"  Если прод-стек нужен именно тут: {OVERRIDE_PROD}=1 make <цель> (сначала make dev-infra-down).",
        ]
    )


def guard_files(paths: list[str]) -> int:
    missing = missing_files(paths)
    if not missing:
        return 0
    return refuse(
        [
            "ОТКАЗ: нет файлов конфигурации:",
            *(f"  - {p} (шаблон: {p}.dist)" for p in missing),
            "  Создать из шаблонов: make env, затем заполнить значения.",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("dev", "prod"))
    parser.add_argument("--docker", default="docker", help="docker/podman binary")
    parser.add_argument(
        "--files", nargs="*", default=[], help=".env files the recipe needs"
    )
    args = parser.parse_args()

    code = guard_dev(args.docker) if args.mode == "dev" else guard_prod(args.docker)
    if code:
        return code
    return guard_files(args.files)


if __name__ == "__main__":
    sys.exit(main())
