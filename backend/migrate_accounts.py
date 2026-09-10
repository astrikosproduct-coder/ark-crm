"""
One-time migration: frontend/spec/seed/accounts.json -> PostgreSQL.

Run:  python migrate_accounts.py            # dry run, prints what it would write
      python migrate_accounts.py --apply

Why this is not a straight copy
-------------------------------
The seed file is NOT in register shape. src/lib/spec/seed.ts normalises it in
the browser at load time, and this reproduces that same transform so the
database holds canonical values:

  1. rename   `name` -> `account_name`, `account_types` -> `account_type`
              (from extensions.json seed_normalisation.accounts)
  2. label -> key for every picklist and multiselect field, because the seed
              stores display labels ("Infrastructure", "B Commercial
              ($250K-$2M)") while the register and the UI both work in keys
              (INFRASTRUCTURE, B_COMMERCIAL_$250K_$2M)

Skipping step 2 leaves every picklist on every account rendering blank, because
the Select control cannot match a label against its options.

Idempotent: an account whose id already exists is left untouched.
"""

import json
import sys
from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models import Account, AccountType

SPEC = Path(__file__).resolve().parent.parent / "frontend" / "spec"

Base.metadata.create_all(bind=engine)


def slug(value: str) -> str:
    """Same normalisation the frontend's picklist resolver uses."""
    return "".join(c if c.isalnum() else "-" for c in str(value).lower()).strip("-")


def load_spec():
    fields = json.loads((SPEC / "fields.json").read_text(encoding="utf-8"))
    picklists = json.loads((SPEC / "picklists.json").read_text(encoding="utf-8"))
    extensions = json.loads((SPEC / "extensions.json").read_text(encoding="utf-8"))
    return fields, picklists, extensions


def build_resolver(fields, picklists, extensions):
    """api_name -> (is_multi, {slug(label or key): key}) for account picklists."""
    rename = extensions["seed_normalisation"]["accounts"].get("rename", {})

    resolvers = {}
    for field in fields:
        if field.get("module") != "accounts":
            continue
        if field.get("type") not in ("picklist", "multiselect"):
            continue

        options = picklists.get(field.get("picklist")) or []
        table = {}
        for option in options:
            table[slug(option["key"])] = option["key"]
            table[slug(option["label"])] = option["key"]

        resolvers[field["api_name"]] = (field["type"] == "multiselect", table)

    return rename, resolvers


def normalise(row, rename, resolvers):
    out = {}
    for key, value in row.items():
        out[rename.get(key, key)] = value

    unresolved = []
    for api_name, (is_multi, table) in resolvers.items():
        value = out.get(api_name)
        if value in (None, "", []):
            continue

        if is_multi:
            values = value if isinstance(value, list) else [value]
            resolved = []
            for v in values:
                key = table.get(slug(v))
                if key is None:
                    unresolved.append(f"{api_name}={v!r}")
                    key = v
                resolved.append(key)
            out[api_name] = resolved
        else:
            key = table.get(slug(value))
            if key is None:
                unresolved.append(f"{api_name}={value!r}")
                key = value
            out[api_name] = key

    return out, unresolved


def main(apply: bool) -> None:
    fields, picklists, extensions = load_spec()
    rename, resolvers = build_resolver(fields, picklists, extensions)
    seed = json.loads((SPEC / "seed" / "accounts.json").read_text(encoding="utf-8"))

    scalars = [
        f["api_name"]
        for f in fields
        if f.get("module") == "accounts"
        and f.get("type") not in ("multiselect", "autonumber")
    ]

    db = SessionLocal()
    try:
        created = skipped = 0
        problems = []

        for raw in seed:
            row, unresolved = normalise(raw, rename, resolvers)
            account_id = raw.get("id")
            problems.extend(f"{account_id}: {u}" for u in unresolved)

            if db.get(Account, account_id) is not None:
                skipped += 1
                continue

            print(
                f"  {account_id}  {row.get('account_name'):32} "
                f"type={row.get('account_type')} owner={row.get('account_owner')} "
                f"segment={row.get('segment')}"
            )

            if not apply:
                created += 1
                continue

            account = Account(account_id=account_id)
            for name in scalars:
                if name in row:
                    setattr(account, name, row[name])
            db.add(account)
            db.flush()

            for value in dict.fromkeys(row.get("account_type") or []):
                db.add(AccountType(account_id=account_id, account_type=value))

            created += 1

        if problems:
            print("\nValues the picklists could not resolve (stored as-is):")
            for p in problems:
                print(f"  ! {p}")

        if apply:
            db.commit()
            print(f"\nApplied. {created} created, {skipped} already present.")
        else:
            print(f"\nDry run. {created} would be created, {skipped} already present.")
            print("Re-run with --apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
