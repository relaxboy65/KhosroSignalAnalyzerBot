#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec python collect_1m_data.py --loop --interval "${COLLECTOR_INTERVAL_SECONDS:-120}"
