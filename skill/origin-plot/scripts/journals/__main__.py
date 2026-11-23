"""Read publisher instructions, display one style profile or check measured metadata."""

import argparse
import json
from pathlib import Path
import sys

from . import load_profile, validate_figure
from .prompt import journal_prompt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prompt", "show", "check"))
    parser.add_argument("journal")
    parser.add_argument("metadata", type=Path, nargs="?")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.action == "prompt":
        if args.metadata:
            parser.error("prompt takes the journal name only")
        try:
            print(journal_prompt(args.journal))
        except ValueError as exc:
            parser.error(str(exc))
        return 0
    if args.action == "show":
        result = load_profile(args.journal)
    else:
        if not args.metadata:
            parser.error("check needs a measured figure metadata JSON file")
        result = validate_figure(args.journal, json.loads(args.metadata.read_text("utf-8-sig")))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"fail": 2, "review": 1}.get(result.get("status"), 0)


if __name__ == "__main__":
    raise SystemExit(main())
