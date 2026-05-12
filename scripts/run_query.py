from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workflow import run_query


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the source-bound DataAgent skeleton.")
    parser.add_argument("query", help="Natural language economic data request.")
    parser.add_argument("--ckan", action="store_true", help="Enable live CKAN package_search.")
    args = parser.parse_args()

    response = run_query(args.query, include_network=args.ckan)
    print(json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
