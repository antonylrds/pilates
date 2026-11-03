"""Exporta a especificação OpenAPI da API para packages/api-client/openapi.json.

Uso (a partir de back/): uv run python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACK))

from app.main import app  # noqa: E402

target = BACK.parent / "packages" / "api-client" / "openapi.json"
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(f"OpenAPI exportado em {target}")
