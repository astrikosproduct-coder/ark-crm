"""
Fill the catalogue, the price books and the Sizing Guide from the price book files.

    python load_price_book.py                          # dry run: says what it would write
    python load_price_book.py --apply                  # write it
    python load_price_book.py --apply --add-missing    # also add what the app's copy lacks

Run AFTER `alembic upgrade head` (0044, 0045) and AFTER products_phase3_metadata.py
--apply, which adds the choices this reads ("Per user", the edition statuses).

THE FIRST FILL — AND AFTER IT, ONLY WHAT IS MISSING
    Products, prices, price books and sizes are all edited in the app since
    phases 2 and 3 (13 Oct 2026), so the app's copy is the one that counts.
    This never changes anything that is already there: not a product's name,
    not a price, not an FX rate. A difference from the files is listed, never
    written.

    What it ADDS depends on what it finds:
      · an empty table      everything the files hold for it. That is the first
                            fill, table by table — the catalogue, the Sizing
                            Guide, the price books.
      · a table with rows   nothing, unless --add-missing: then whatever the
                            files hold and the table lacks. Something missing
                            may have been deleted in the app on purpose, so
                            that is a person's decision, made with this flag.
    A size's empty details (what it covers, users included) are filled from
    the file either way: filling a blank overwrites nothing.

WHAT COMES FROM WHICH FILE (frontend/spec/seed/)
    products.json        the catalogue: modules, suites, user packs, add-ons
    prices.json          their list prices, per size — into the Standard book
    sizes.json           the Sizing Guide
    regions.json         the price books. "USA USD" is the Standard book; each
                         other row becomes a regional book with its currency,
                         Region Pricing % and FX rate
    rate_card.json       four Service products, L1 to L4, priced per day at the
                         OFFSITE rate. (The onsite rate is offsite x a premium:
                         a CPQ price rule from phase 4, not a second price.)
    support_tiers.json   four Support products, priced as a % of the licence
    pricing_params.json  the per-user rate: one "Additional User" product

    The first edition of the price list is made here if there is none, and is
    the one in use.

WRITES ONLY WHAT THE FILES STATE. Supports Perpetual, Has Annual Updates
Option, Quantity Allowed and Unit of Measure are in no file for the catalogue
items, and stay empty. A user pack's one price ("ALL" in the file) has no size.

STOPS, WRITING NOTHING, on anything it cannot place: a category, charge type,
pricing basis, unit, level, tier, currency or size that is not a choice in the
register; a SKU listed twice; a price for a SKU that is not in the catalogue.

NO DDL.
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app import price_books as rules  # noqa: E402
from app.clock import now_utc  # noqa: E402
from app.ids import next_reference_id  # noqa: E402
from app.metadata_spec import SPEC_DIR  # noqa: E402
from app.models import (  # noqa: E402
    DeploymentSize,
    PicklistValue,
    PriceBook,
    PriceBookEdition,
    PriceBookEntry,
    Product,
)

SEED = SPEC_DIR / "seed"
FILES = ("products", "prices", "sizes", "regions", "rate_card", "support_tiers", "pricing_params")

#: Column <- (key in the file, the picklist its label must be a choice of).
PICKLIST_COLUMNS = {
    "catalogue_category": ("category", "products__catalogue_category"),
    "charge_type": ("charge_type", "products__charge_type"),
    "pricing_basis": ("pricing_basis", "products__pricing_basis"),
}
#: The file's word for "one price whatever the size".
EVERY_SIZE = "ALL"
#: The file's name for the master price list — the same the migration gave it.
STANDARD_NAME = "USA USD"
FIRST_EDITION = "Edition 1"

PRODUCT_ID = re.compile(r"^PRD-(\d+)$")


def _slug(value: object) -> str:
    # "24×7" in one file is "24x7" in the register: the same thing, typed twice.
    return re.sub(r"[\s_\-/]+", "", str(value or "").replace("×", "x")).lower()


class Choices:
    """A picklist's keys, found by key or by label, however either is spaced."""

    def __init__(self, db, picklist: str):
        self.picklist = picklist
        self.by_slug: dict[str, str] = {}
        for row in db.scalars(select(PicklistValue).where(PicklistValue.picklist_key == picklist)):
            self.by_slug[_slug(row.key)] = row.key
            self.by_slug[_slug(row.label)] = row.key

    def key_of(self, label: object, where: str) -> str:
        key = self.by_slug.get(_slug(label))
        if key is None:
            hint = " Run products_phase3_metadata.py --apply first." if self.by_slug else ""
            raise SystemExit(f"STOPPED: {where} says “{label}”, which is not a choice of {self.picklist}.{hint}")
        return key


class Load:
    def __init__(self, db, add_missing: bool):
        self.db = db
        self.add_missing = add_missing
        self.log: list[str] = []
        self.notes: list[str] = []
        missing = [name for name in FILES if not (SEED / f"{name}.json").exists()]
        if missing:
            raise SystemExit(f"STOPPED: the price book files are not all at {SEED}: {', '.join(missing)}.")
        self.file = {name: json.loads((SEED / f"{name}.json").read_text(encoding="utf-8")) for name in FILES}
        self.choices = {column: Choices(db, picklist) for column, (_, picklist) in PICKLIST_COLUMNS.items()}
        self.units = Choices(db, "products__unit_of_measure")
        self.levels = Choices(db, "products__level")
        self.tiers = Choices(db, "products__tier")
        self.currencies = Choices(db, "products__currency")
        # The products added below, for the prices that follow: sku -> Product.
        self.products: dict[str, Product] = {}
        self.highest = 0

    def may_add(self, table_was_empty: bool) -> bool:
        return table_was_empty or self.add_missing

    # ------------------------------------------------------------ sizes

    def sizes(self) -> None:
        existing = {_slug(s.size_code): s for s in self.db.scalars(select(DeploymentSize))}
        adding = self.may_add(not existing)
        for row in self.file["sizes"]:
            details = {
                "managed_assets_cap": row.get("managed_assets"),
                "typical_deployment": row.get("typical_deployment"),
                "subsystem_types": row.get("subsystem_types"),
                "base_users_included": int(str(row["base_users"]).replace(",", "")) if row.get("base_users") else None,
                "sort_order": row.get("sort"),
            }
            size = existing.get(_slug(row["code"]))
            if size is None:
                if not adding:
                    self.notes.append(f"size {row['code']} is in the file and not in the Sizing Guide — add it with --add-missing")
                    continue
                size = DeploymentSize(size_id=rules.next_size_id(self.db), size_code=row["code"], active=True, **details)
                self.db.add(size)
                self.db.flush()
                existing[_slug(size.size_code)] = size
                self.log.append(f"+ size {size.size_id}  {size.size_code}")
                continue
            filled = [c for c, v in details.items() if getattr(size, c) is None and v is not None]
            for column in filled:
                setattr(size, column, details[column])
            if filled:
                self.log.append(f"~ size {size.size_code}: {', '.join(filled)} filled in")
        self.db.flush()
        self.size_of = existing

    # ------------------------------------------------------------ products

    def _product(self, sku: str, stated: dict, custom: dict | None, adding: bool, existing: dict[str, Product]) -> Product | None:
        product = existing.get(sku)
        if product is None:
            if not adding:
                self.notes.append(f"{sku} ({stated['item_name']}) is in the files and not in the catalogue — add it with --add-missing")
                return None
            product = Product(
                product_id=next_reference_id(self.db, "products", "PRD", 4, self.highest),
                sku_code=sku,
                active=True,
                custom_fields=dict(custom or {}),
                **stated,
            )
            self.db.add(product)
            self.db.flush()
            existing[sku] = product
            self.log.append(f"+ {product.product_id}  {sku:<12} {stated['item_name']}")
        else:
            differs = [c for c, v in stated.items() if c != "display_order" and getattr(product, c) != v]
            if differs:
                self.notes.append(f"{sku}: {', '.join(differs)} differ from the files — the catalogue's are kept")
        self.products[sku] = product
        return product

    def catalogue(self) -> None:
        items = self.file["products"]
        skus = [item["sku"] for item in items]
        twice = sorted({s for s in skus if skus.count(s) > 1})
        if twice:
            raise SystemExit(f"STOPPED: listed twice in the catalogue file: {', '.join(twice)}.")
        unknown = sorted({p["sku"] for p in self.file["prices"]} - set(skus))
        if unknown:
            raise SystemExit(f"STOPPED: priced but not in the catalogue file: {', '.join(unknown)}.")

        existing = {p.sku_code: p for p in self.db.scalars(select(Product))}
        self.highest = max(
            (int(m.group(1)) for m in (PRODUCT_ID.match(p.product_id) for p in existing.values()) if m),
            default=0,
        )
        adding = self.may_add(not existing)
        key = lambda column, value, where: self.choices[column].key_of(value, where)  # noqa: E731

        position: dict[str, int] = {}
        for item in items:
            sku = item["sku"]
            stated = {
                "item_name": item["name"],
                "description": item.get("description"),
                **{column: key(column, item.get(file_key), f"{sku} {file_key}") for column, (file_key, _) in PICKLIST_COLUMNS.items()},
            }
            position[stated["catalogue_category"]] = position.get(stated["catalogue_category"], 0) + 1
            stated["display_order"] = position[stated["catalogue_category"]]
            self._product(sku, stated, None, adding, existing)

        # ---- services: one product per level, priced per day
        day = self.units.key_of("Per day", "the rate card")
        for order, row in enumerate(sorted(self.file["rate_card"], key=lambda r: r["level"]), start=1):
            level = self.levels.key_of(row["level"], "the rate card")
            self._product(
                f"SVC-{row['level']}",
                {
                    "item_name": f"{row['role']} ({row['level']})",
                    "description": f"Professional services at level {row['level']}: {row['role']}. Priced per day, offsite.",
                    "catalogue_category": key("catalogue_category", "Service", "a service"),
                    "charge_type": key("charge_type", "One-Time", "a service"),
                    "pricing_basis": key("pricing_basis", "Per day rate", "a service"),
                    "unit_of_measure": day,
                    "quantity_allowed": True,
                    "supports_perpetual": False,
                    "has_annual_updates_option": False,
                    "display_order": order,
                },
                {"level": level, "role": row["role"]},
                adding,
                existing,
            )

        # ---- support: one product per tier, priced as a share of the licence
        share = self.units.key_of("Per licence %", "the support tiers")
        for order, row in enumerate(self.file["support_tiers"], start=1):
            tier = self.tiers.key_of(row["tier"], "the support tiers")
            self._product(
                f"SUP-{order}",
                {
                    "item_name": f"{row['tier']} Support",
                    "description": row.get("coverage"),
                    "catalogue_category": key("catalogue_category", "Support", "a support tier"),
                    "charge_type": key("charge_type", "Annual", "a support tier"),
                    "pricing_basis": key("pricing_basis", "% of licence", "a support tier"),
                    "unit_of_measure": share,
                    "quantity_allowed": False,
                    "supports_perpetual": False,
                    "has_annual_updates_option": False,
                    "display_order": order,
                },
                {"tier": tier, "coverage": row.get("coverage")},
                adding,
                existing,
            )

        # ---- one more user, beside the user packs
        self._product(
            "USR-ADD",
            {
                "item_name": "Additional User",
                "description": "One more user for a year, beyond the users the deployment size includes.",
                "catalogue_category": key("catalogue_category", "User Pack", "the additional user"),
                "charge_type": key("charge_type", "Annual", "the additional user"),
                "pricing_basis": key("pricing_basis", "Flat", "the additional user"),
                "unit_of_measure": self.units.key_of("Per user", "the additional user"),
                "quantity_allowed": True,
                "supports_perpetual": False,
                "has_annual_updates_option": False,
                "display_order": 99,
            },
            None,
            adding,
            existing,
        )
        for sku in sorted(set(existing) - set(self.products)):
            self.notes.append(f"{sku} ({existing[sku].item_name}) is in the catalogue and not in the files — left alone")
        self.db.flush()

    # ------------------------------------------------------------ price books

    def books(self) -> None:
        existing = {_slug(b.price_book_name): b for b in self.db.scalars(select(PriceBook))}
        regional = [b for b in existing.values() if not b.is_standard]
        standard = rules.standard_book(self.db)
        adding = self.may_add(not regional)

        for row in self.file["regions"]:
            name = row["code"]
            is_standard = _slug(name) == _slug(STANDARD_NAME)
            book = standard if is_standard else existing.get(_slug(name))
            stated = {
                "currency": self.currencies.key_of(row["currency"], f"price book {name}"),
                "region_pricing_pct": Decimal(str(row["region_pricing_pct"])),
                "fx_rate_local_per_usd": Decimal(str(row["fx_rate"])),
                "display_format": row.get("display_format"),
            }
            if book is None:
                if not (is_standard or adding):
                    self.notes.append(f"price book {name} is in the file and not in ARK — add it with --add-missing")
                    continue
                book = PriceBook(
                    price_book_id=rules.next_book_id(self.db), price_book_name=name, is_standard=is_standard, active=True, **stated
                )
                self.db.add(book)
                self.db.flush()
                existing[_slug(name)] = book
                if is_standard:
                    standard = book
                self.log.append(f"+ price book {book.price_book_id}  {name}{'  (Standard)' if is_standard else ''}")
                continue
            if book.display_format is None and stated["display_format"]:
                book.display_format = stated["display_format"]
                self.log.append(f"~ price book {book.price_book_name}: display format filled in")
            differs = [
                c for c in ("region_pricing_pct", "fx_rate_local_per_usd")
                if getattr(book, c) is not None and Decimal(str(getattr(book, c))) != stated[c]
            ]
            if book.currency and book.currency != stated["currency"]:
                differs.append("currency")
            if differs:
                self.notes.append(f"price book {book.price_book_name}: {', '.join(differs)} differ from the file — ARK's are kept")
        if standard is None:
            raise SystemExit(f"STOPPED: regions.json has no “{STANDARD_NAME}” row, and there is no Standard price book.")
        self.db.flush()
        self.standard = standard

    def edition(self) -> None:
        current = rules.current_edition(self.db)
        if current is None:
            any_edition = self.db.scalar(select(func.count()).select_from(PriceBookEdition))
            if any_edition:
                raise SystemExit("STOPPED: there are editions but none is in use. Make one current in ARK, then run this again.")
            current = PriceBookEdition(
                edition_id=rules.next_edition_id(self.db),
                price_book_version=FIRST_EDITION,
                status=rules.CURRENT,
                effective_from=now_utc().date(),
                made_current_at=now_utc(),
            )
            self.db.add(current)
            self.db.flush()
            self.log.append(f"+ edition {current.edition_id}  {FIRST_EDITION}  (in use)")
        self.current = current

    # ------------------------------------------------------------ prices

    def _price(self, product: Product, size: DeploymentSize | None, amount: Decimal, *, share: bool = False) -> None:
        """A first price where there is none. One already there is never touched."""
        entry = self.db.scalar(
            select(PriceBookEntry)
            .where(PriceBookEntry.price_book_id == self.standard.price_book_id)
            .where(PriceBookEntry.edition_id == self.current.edition_id)
            .where(PriceBookEntry.product_id == product.product_id)
            .where(PriceBookEntry.size_id.is_(None) if size is None else PriceBookEntry.size_id == size.size_id)
        )
        where = size.size_code if size else "every size"
        if entry is None:
            self.db.add(
                PriceBookEntry(
                    price_book_id=self.standard.price_book_id,
                    edition_id=self.current.edition_id,
                    product_id=product.product_id,
                    size_id=size.size_id if size else None,
                    list_price=None if share else amount,
                    pct_of_annual_licence=amount if share else None,
                )
            )
            shown = f"{amount * 100:.0f}%" if share else f"{amount:>12,.2f}"
            self.log.append(f"    + price {product.sku_code:<12} {where:<10} {shown}")
            return
        held = entry.pct_of_annual_licence if share else entry.list_price
        if held is not None and Decimal(held) != amount:
            self.notes.append(f"{product.sku_code} at {where}: ARK has {held:,.2f}, the file {amount:,.2f} — ARK's is kept")

    def prices(self) -> None:
        cent = Decimal("0.01")
        priced: set[str] = set()
        for sku, product in self.products.items():
            seen: set[str | None] = set()
            for row in (p for p in self.file["prices"] if p["sku"] == sku):
                if row["size"] == EVERY_SIZE:
                    size = None
                else:
                    size = self.size_of.get(_slug(row["size"]))
                    if size is None:
                        raise SystemExit(f"STOPPED: {sku} is priced at “{row['size']}”, which is not a size in the Sizing Guide.")
                if (size.size_id if size else None) in seen:
                    raise SystemExit(f"STOPPED: {sku} is priced twice at {row['size']}.")
                seen.add(size.size_id if size else None)
                self._price(product, size, Decimal(str(row["list_price_usd"])).quantize(cent))
            if None in seen and len(seen) > 1:
                raise SystemExit(f"STOPPED: {sku} has a price for every size AND a price per size.")
            if seen:
                priced.add(sku)

        for row in self.file["rate_card"]:
            product = self.products.get(f"SVC-{row['level']}")
            if product is not None:
                self._price(product, None, Decimal(str(row["day_offsite"])).quantize(cent))
                priced.add(product.sku_code)
        for order, row in enumerate(self.file["support_tiers"], start=1):
            product = self.products.get(f"SUP-{order}")
            if product is not None:
                self._price(product, None, Decimal(str(row["pct_of_annual_licence"])).quantize(Decimal("0.000001")), share=True)
                priced.add(product.sku_code)
        extra = self.products.get("USR-ADD")
        if extra is not None:
            self._price(extra, None, Decimal(str(self.file["pricing_params"]["user_blended_rate_usd"])).quantize(cent))
            priced.add(extra.sku_code)

        for sku, product in self.products.items():
            if sku not in priced:
                self.notes.append(f"{sku} ({product.item_name}) has no price in the files — it can be picked, not quoted")
        self.db.flush()


def plan(db, add_missing: bool = False) -> tuple[list[str], list[str]]:
    """Apply the files to the session (flushed, not committed)."""
    load = Load(db, add_missing)
    load.sizes()
    load.catalogue()
    load.books()
    load.edition()
    load.prices()
    return load.log, load.notes


def main() -> int:
    apply = "--apply" in sys.argv
    with SessionLocal() as db:
        log, notes = plan(db, add_missing="--add-missing" in sys.argv)
        print(f"Price book files -> ARK — {'apply' if apply else 'dry run'}")
        print("=" * 74)
        for line in log or ["nothing to write — ARK already holds everything the files do"]:
            print(f"  {line}")
        if notes:
            print("\nTo know:")
            for note in notes:
                print(f"  · {note}")
        count = lambda model: db.scalar(select(func.count()).select_from(model))  # noqa: E731
        print(
            f"\n{count(Product)} products, {count(PriceBookEntry)} prices, {count(PriceBook)} price books, "
            f"{count(DeploymentSize)} sizes, {count(PriceBookEdition)} edition(s)."
        )
        if not apply:
            db.rollback()
            print("Dry run — nothing written. Re-run with --apply.")
            return 0
        db.commit()
        print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
