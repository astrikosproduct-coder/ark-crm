"""
Release 1.1, chunk D — which Accounts already in this database look like duplicates?

    python release_1_1_duplicate_accounts.py

READ-ONLY: it changes nothing. Run it on production BEFORE the release (it
works on V1's schema, before any migration) so the duplicates are known — and
merged or explained by hand — before the duplicate check starts asking.

It uses the release's own rules (app/account_matching.py):

  SAME NAME        one registered name, ignoring case, punctuation and how the
                   legal form is spelt ("Pvt. Ltd." = "Private Limited"). V1
                   accounts have no Country yet, so these are only LIKELY the
                   same company — after the release, one with the same Country
                   is refused.
  SIMILAR          what the check will ASK about: the same name without its
                   legal form, a typo apart, or the same distinctive first word.

Nothing is merged: deciding that two accounts are one company — and moving
their contacts, leads and registrations onto one — is a person's call.
"""

from __future__ import annotations

import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import inspect, text  # noqa: E402

from app.account_matching import registered_name, similar  # noqa: E402
from app.database import engine  # noqa: E402

engine.echo = False


def main() -> int:
    columns = {c["name"] for c in inspect(engine).get_columns("accounts")}
    country = "country" if "country" in columns else "NULL"
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT account_id, account_name, region, {country} AS country, active FROM accounts ORDER BY account_id")
        ).mappings().all()

    def line(r) -> str:
        where = " · ".join(x for x in (r["region"], r["country"]) if x) or "no Region"
        return f"{r['account_id']}  {r['account_name']}  ({where}{'' if r['active'] else ', inactive'})"

    by_name: dict[str, list] = defaultdict(list)
    for r in rows:
        by_name[registered_name(r["account_name"])].append(r)
    same = [group for group in by_name.values() if len(group) > 1]

    pairs = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if registered_name(a["account_name"]) != registered_name(b["account_name"]) and similar(
                a["account_name"], b["account_name"]
            ):
                pairs.append((a, b))

    print(f"Accounts checked: {len(rows)}")
    print("=" * 74)
    print(f"\nSAME NAME — {len(same)} group(s), likely the same company:")
    for group in same:
        print()
        for r in group:
            print(f"  {line(r)}")
    print(f"\nSIMILAR — {len(pairs)} pair(s), will be asked about when either is saved:")
    for a, b in pairs:
        print(f"\n  {line(a)}\n  {line(b)}")
    if not same and not pairs:
        print("\nNo duplicates found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
