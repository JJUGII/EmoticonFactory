#!/usr/bin/env bash
# 루트에서 실행: bash check_after_reboot.sh [--web] [--notify]
exec bash "$(cd "$(dirname "$0")" && pwd)/scripts/check_after_reboot.sh" "$@"
