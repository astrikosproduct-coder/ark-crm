"""
One-time migration: frontend/spec/seed/contacts.json -> PostgreSQL.

Run:  python migrate_contacts.py            # dry run
      python migrate_contacts.py --apply

Same shape as migrate_accounts.py, reproducing what src/lib/spec/seed.ts does
in the browser: rename the seed's keys to register api_names, then resolve
every picklist value to its KEY.

One extra rule this file needs and accounts did not. resolvePicklistValue has a
third fallback the accounts seed never exercised: a value matching only the
LEADING CODE of a key. The contacts seed stores contact_role as "DECM", while
the picklist key is DECM_DECISION_MAKER. Without that fallback every contact
would land in the database with an unresolved role and the Contact Role badge
would render blank.

Idempotent: a contact whose id already exists is left untouched.
"""

import json
import sys
from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models import Account, Contact, User

SPEC = Path(__file__).resolve().parent.parent / "frontend" / "spec"

Base.metadata.create_all(bind=engine)

CHECKBOXES = ("confidential", "is_client_poc_evaluator")


def slug(value: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in str(value).lower()).strip("-")


def build_resolver():
    fields = json.loads((SPEC / "fields.json").read_text(encoding="utf-8"))
    picklists = json.loads((SPEC / "picklists.json").read_text(encoding="utf-8"))
    extensions = json.loads((SPEC / "extensions.json").read_text(encoding="utf-8"))

    rename = extensions["seed_normalisation"]["contacts"].get("rename", {})

    resolvers = {}
    for field in fields:
        if field.get("module") != "contacts":
            continue
        if field.get("type") not in ("picklist", "multiselect"):
            continue

        table = {}
        for option in picklists.get(field.get("picklist")) or []:
            key = option["key"]
            table[slug(key)] = key
            table[slug(option["label"])] = key
            # "DECM" for DECM_DECISION_MAKER. Registered last so an exact key or
            # label match always wins over a leading-code one.
            table.setdefault(slug(key.split("_")[0]), key)

        resolvers[field["api_name"]] = table

    scalars = [
        f["api_name"]
        for f in fields
        if f.get("module") == "contacts" and f.get("type") != "autonumber"
    ]
    return rename, resolvers, scalars


def normalise(row, rename, resolvers):
    out = {rename.get(k, k): v for k, v in row.items()}

    unresolved = []
    for api_name, table in resolvers.items():
        value = out.get(api_name)
        if value in (None, "", []):
            continue
        key = table.get(slug(value))
        if key is None:
            unresolved.append(f"{api_name}={value!r}")
            key = value
        out[api_name] = key

    return out, unresolved


def main(apply: bool) -> None:
    rename, resolvers, scalars = build_resolver()
    seed = json.loads((SPEC / "seed" / "contacts.json").read_text(encoding="utf-8"))

    db = SessionLocal()
    try:
        created = skipped = 0
        problems = []
        dangling = []

        for raw in seed:
            row, unresolved = normalise(raw, rename, resolvers)
            contact_id = raw.get("id")
            problems.extend(f"{contact_id}: {u}" for u in unresolved)

            # Both lookups are real foreign keys now. A seed row pointing at an
            # account or user that is not in the database would fail the insert,
            # so it is reported rather than silently dropped.
            if row.get("account") and db.get(Account, row["account"]) is None:
                dangling.append(f"{contact_id}: account {row['account']} not in DB")
            if row.get("engagement_owner") and db.get(User, row["engagement_owner"]) is None:
                dangling.append(f"{contact_id}: user {row['engagement_owner']} not in DB")

            if db.get(Contact, contact_id) is not None:
                skipped += 1
                continue

            print(
                f"  {contact_id}  {row.get('full_name'):22} "
                f"account={row.get('account')} role={row.get('contact_role')} "
                f"owner={row.get('engagement_owner')} f/f={row.get('friend_foe_assessment')}"
            )

            if apply:
                contact = Contact(contact_id=contact_id)
                for name in scalars:
                    if name in row:
                        setattr(contact, name, row[name])
                for name in CHECKBOXES:
                    if getattr(contact, name, None) is None:
                        setattr(contact, name, False)
                db.add(contact)

            created += 1

        if problems:
            print("\nPicklist values that would not resolve (stored as-is):")
            for p in problems:
                print(f"  ! {p}")

        if dangling:
            print("\nBROKEN LINKS - these would violate a foreign key:")
            for d in dangling:
                print(f"  !! {d}")
            if apply:
                print("\nRefusing to write. Fix the links or the seed first.")
                return

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
