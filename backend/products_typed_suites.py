"""
What was typed into the product fields before the catalogue existed.

    python products_typed_suites.py                           # report: writes nothing
    python products_typed_suites.py --apply                   # convert the exact matches
    python products_typed_suites.py --apply --map "Omnific=SEG-OMN" --map "Cognus=SEG-COG"

Run AFTER `load_price_book.py --apply` — it matches against the catalogue.

From 3 Sep 2026 to Products, step 1 (12 Oct 2026) four fields were typed by
hand: S!aP Solution Suite, Suite Demonstrated and Secondary S!aP Suites on a
Lead, Expansion Suites on a Deal. They pick from the catalogue now and store a
product's id. Whatever was typed is still in the column, and still shows on the
record as the text it is.

THE REPORT lists every such value, and for each says one of:
  converts      it is exactly one product's Item Name or SKU (case, spaces and
                punctuation ignored), and that product may be picked in the field
  as typed      anything else — left exactly as it is

--apply rewrites the "converts" ones to the product's id. NOTHING IS GUESSED:
"Omnific" is not "S!aP Omnific" until a person says so, with --map
"what was typed=SKU". A mapping applies wherever that exact text was typed.

A several-pick field converts only when EVERY part of it matches — parts are
separated by a comma, a semicolon or a new line. "Omnific and Cognus" is one
thing somebody wrote and stays one thing.

What stays as typed is not lost and blocks nothing: the record saves, the text
shows, and the field takes a product the next time someone edits it.

No audit line is written: the answer is the same product, only stored as its
id. `modified_date` is not touched.

NO DDL.
"""

from __future__ import annotations

import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select, text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import Deal, Lead, Product  # noqa: E402
from app.products import PRODUCT_ID_PATTERN, PRODUCT_PICKS, allowed_for, join_picks  # noqa: E402

MODELS = {"leads": (Lead, "lead_id", "opportunity_name"), "deals": (Deal, "deal_id", "deal_name")}
PARTS = re.compile(r"[,;\n]")


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


class Catalogue:
    def __init__(self, db, mappings: dict[str, str]):
        self.db = db
        self.products = list(db.scalars(select(Product)))
        self.by_sku = {p.sku_code.lower(): p for p in self.products}
        self.mapped: dict[str, Product] = {}
        for typed, sku in mappings.items():
            product = self.by_sku.get(sku.lower())
            if product is None:
                raise SystemExit(f"STOPPED: --map names the SKU “{sku}”, which is not in the catalogue.")
            self.mapped[_slug(typed)] = product

    def match(self, module: str, api_name: str, typed: str) -> Product | None:
        """The one product this text names, if it may be picked in this field."""
        want = _slug(typed)
        if not want:
            return None
        product = self.mapped.get(want)
        if product is None:
            hits = [p for p in self.products if want in (_slug(p.item_name), _slug(p.sku_code))]
            product = hits[0] if len(hits) == 1 else None
        if product is None or not allowed_for(self.db, module, api_name, product):
            return None
        return product


def resolve(catalogue: Catalogue, module: str, api_name: str, several: bool, stored: str) -> str | None:
    """The value to store instead, or None to leave what was typed."""
    if not several:
        product = catalogue.match(module, api_name, stored)
        return product.product_id if product else None
    whole = catalogue.match(module, api_name, stored)
    if whole:
        return whole.product_id
    parts = [p.strip() for p in PARTS.split(stored) if p.strip()]
    found = [catalogue.match(module, api_name, part) for part in parts]
    if not parts or any(f is None for f in found):
        return None
    return join_picks(f.product_id for f in found)


def is_typed(several: bool, stored: str | None) -> bool:
    text = (stored or "").strip()
    if not text:
        return False
    parts = [p.strip() for p in text.split(",")] if several else [text]
    return not all(PRODUCT_ID_PATTERN.match(p) for p in parts)


def main() -> int:
    apply = "--apply" in sys.argv
    mappings: dict[str, str] = {}
    args = sys.argv[1:]
    for index, arg in enumerate(args):
        if arg == "--map":
            pair = args[index + 1] if index + 1 < len(args) else ""
            typed, _, sku = pair.rpartition("=")
            if not typed.strip() or not sku.strip():
                raise SystemExit('STOPPED: --map takes "what was typed=SKU".')
            mappings[typed.strip()] = sku.strip()

    with SessionLocal() as db:
        catalogue = Catalogue(db, mappings)
        if not catalogue.products:
            raise SystemExit("STOPPED: the catalogue is empty — run load_price_book.py --apply first.")
        names = {p.product_id: p.item_name for p in catalogue.products}

        print(f"Typed product values — {'apply' if apply else 'report'}")
        print("=" * 74)
        converts = kept = 0
        left: dict[str, int] = {}
        for module, (model, id_attr, name_attr) in MODELS.items():
            for record in db.scalars(select(model).order_by(getattr(model, id_attr))):
                for api_name, several in PRODUCT_PICKS[module].items():
                    stored = getattr(record, api_name)
                    if not is_typed(several, stored):
                        continue
                    new = resolve(catalogue, module, api_name, several, stored.strip())
                    where = f"{getattr(record, id_attr)}  {(getattr(record, name_attr) or '')[:32]:<32}  {api_name}"
                    if new is None:
                        kept += 1
                        left[stored.strip()] = left.get(stored.strip(), 0) + 1
                        print(f"  as typed   {where}: “{stored}”")
                    else:
                        converts += 1
                        shown = ", ".join(names[p] for p in new.split(","))
                        print(f"  converts   {where}: “{stored}” -> {shown}")
                        if apply:
                            # Plain SQL, not the model: setting the attribute
                            # would fire modified_date's onupdate, and nobody
                            # modified this record. Both names are constants
                            # of this file and app/products.py.
                            db.execute(
                                text(f"UPDATE {model.__tablename__} SET {api_name} = :value WHERE {id_attr} = :id"),
                                {"value": new, "id": getattr(record, id_attr)},
                            )

        if not converts and not kept:
            print("  nothing typed — every value is a product from the catalogue, or empty")
        print(f"\n{converts} {'converted' if apply else 'would convert'}, {kept} left as typed.")
        if left:
            print("\nLeft as typed (how many times each was typed):")
            for text, count in sorted(left.items(), key=lambda item: (-item[1], item[0].lower())):
                print(f"  {count:>3} ×  “{text}”")
            print('\nTo convert one, say which product it is:  --map "what was typed=SKU"')
        if not apply:
            db.rollback()
            if converts:
                print("Report only — nothing written. Re-run with --apply.")
            return 0
        db.commit()
        if converts:
            print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
