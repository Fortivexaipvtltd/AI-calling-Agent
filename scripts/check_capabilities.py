from __future__ import annotations

import json

from app.capabilities import audit


def main() -> None:
    a = audit()
    print(f"capabilities: {a['present']}/{a['total']} present "
          f"({a['coverage']*100:.1f}%), missing {a['missing']}")
    by_cat: dict[str, list[str]] = {}
    for row in a["items"]:
        mark = "ok" if row["present"] else "MISSING"
        by_cat.setdefault(row["category"], []).append(f"  [{mark}] {row['capability']}")
    for cat in sorted(by_cat):
        print(f"\n{cat}:")
        print("\n".join(sorted(by_cat[cat])))
    missing = [r["capability"] for r in a["items"] if not r["present"]]
    if missing:
        print("\nMISSING:", json.dumps(missing))
    else:
        print("\nall requested capabilities present")


if __name__ == "__main__":
    main()
