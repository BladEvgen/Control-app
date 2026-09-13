#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
RUFF="${ROOT}/venv/bin/ruff"

if [ ! -x "$RUFF" ]; then
    echo "Не найден ${RUFF}. Установите зависимости: pip install -r backend/requirements/base.txt" >&2
    exit 1
fi

case "${1-}" in
    --fix)
        "$RUFF" check "${ROOT}" --fix
        CHANGED=$(
            {
                git -C "${ROOT}" diff --name-only -z --diff-filter=ACMR HEAD
                git -C "${ROOT}" ls-files --others --exclude-standard -z
            } | grep -zE '\.py$' | grep -zvE '(^|/)migrations/' | sort -zu | tr '\0' '\n'
        )
        if [ -n "$CHANGED" ]; then
            printf '%s\n' "$CHANGED" | (cd "${ROOT}" && xargs -r "${ROOT}/venv/bin/isort" --profile black)
            printf '%s\n' "$CHANGED" | (cd "${ROOT}" && xargs -r "${ROOT}/venv/bin/black")
        fi
        ;;
    --complexity)
        "$RUFF" check "${ROOT}/backend" --select C901 --statistics
        ;;
    *)
        "$RUFF" check "${ROOT}"
        ;;
esac
