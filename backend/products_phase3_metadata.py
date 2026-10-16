"""
Products, phase 3 — Price Books and CPQ's Sizing Guide get modules of their own (13 Oct 2026).

    python products_phase3_metadata.py            # dry run: validates, writes nothing
    python products_phase3_metadata.py --apply    # change the register and publish

Run AFTER `alembic upgrade head` (0045 makes the tables) and after
products_market_segments_metadata.py.

Until now the Products register module described EIGHT things, section by
section: a product, and seven tables about pricing. Every field is owned by one
module (metadata v2), so each of those goes to the module that owns it:

    CATALOGUE ITEM       stays                      Products
    REGION & FX          -> "PRICE BOOK"            Price Books          (new module)
    PRICE MATRIX         ->                         Prices               (new, under Price Books)
    Price Book Version   -> "EDITION"               Editions             (new, under Price Books)
    DEPLOYMENT SIZE      ->                         Sizing Guide         (new, under CPQ)
    PRICING PARAMETERS   ->                         CPQ                  (new module)
    SERVICES RATE CARD   Level, Role                -> a product's own fields, shown for a Service
                         the four rates             -> deleted: a service's day rate is its PRICE
    SUPPORT TIER         Tier, Coverage             -> a product's own fields, shown for Support
                         % of Annual Licence        -> Prices (a Support product's price)
    SERVICE CATEGORY     Service Category           -> Quotes, on a quote line (where it is chosen)
                         Sort Order                 -> deleted: a dropdown already has an order

What changes besides where a field sits, each step skipped when already done:

  * Price Books gain Price Book ID, Price Book Name, Standard Price Book and
    Active. Region Code is deleted: a book's NAME is what the dropdown was,
    and a new region is a new book, not a new choice in Setup.
  * Editions gain Edition ID, Status (Draft / Current / Retired, a new list of
    system values), Effective From, Effective To and Notes.
  * The Sizing Guide gains Size ID and Active. Size Code becomes TEXT — a size
    is a record now, made on the Sizing Guide. A price's Size becomes a lookup
    to it. The two size dropdown lists are retired.
  * Is Derived is deleted: prices are entered, none is worked out yet. CPQ's
    price rules bring that back, for real, in phase 4.
  * Unit of Measure gains "Per user" (the Additional User product).
  * Pricing Basis's "By T-shirt size" and "% of licence" become system values:
    the server reads them to know a price's shape (app/price_books.py).
  * The three sections left empty on Products are removed.

Deletes are LOGICAL, as Setup's own: the rows stay and a field can be restored.
NO DDL. Run on development and on production.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import (  # noqa: E402
    FieldDefinition,
    FieldPlacement,
    Layout,
    Module,
    Picklist,
    PicklistValue,
    Section,
)
from app.routers.metadata import _publish, _validation_out, build_snapshot  # noqa: E402

NOTE = (
    "Products phase 3: Price Books, Prices, Editions, CPQ and the Sizing Guide become modules; "
    "the rate card and support tiers become products and prices"
)
ORIGIN = "Products phase 3"
USE_CASE = "Products phase 3 (13 Oct 2026): Price Books and the Sizing Guide, editable in the app."

PRODUCTS = "products"
PRICE_BOOKS = "price_books"
PRICES = "price_book_entries"
EDITIONS = "price_book_editions"
CPQ = "cpq"
SIZES = "deployment_sizes"
QUOTES = "quotes"

#: key -> (label, the module it is filed under in Setup)
MODULES = {
    PRICE_BOOKS: ("Price Books", None),
    PRICES: ("Prices", PRICE_BOOKS),
    EDITIONS: ("Editions", PRICE_BOOKS),
    CPQ: ("CPQ", None),
    SIZES: ("Sizing Guide", CPQ),
}

#: Products section -> (the module it moves to, its name there)
SECTION_MOVES = {
    "REGION & FX": (PRICE_BOOKS, "PRICE BOOK"),
    "PRICE MATRIX": (PRICES, "PRICE MATRIX"),
    "DEPLOYMENT SIZE": (SIZES, "DEPLOYMENT SIZE"),
    "PRICING PARAMETERS": (CPQ, "PRICING PARAMETERS"),
}
EDITION_SECTION = "EDITION"
CATALOGUE_ANCHOR = "catalogue_category"

EDITION_STATUS = "price_book_editions__status"
STATUSES = (("DRAFT", "Draft"), ("CURRENT", "Current"), ("RETIRED", "Retired"))

#: Shown on a product only for its kind — the register's own condition language.
SERVICE_ONLY = "catalogue_category == 'Service'"
SUPPORT_ONLY = "catalogue_category == 'Support'"


def now() -> datetime:
    return datetime.now(timezone.utc)


class Register:
    """The draft register, with the handful of moves this script makes."""

    def __init__(self, db):
        self.db = db
        self.log: list[str] = []

    # ---- finding things

    def section(self, module: str, label: str) -> Section | None:
        return self.db.scalar(select(Section).where(Section.module_key == module, Section.label == label))

    def placement(self, module: str, api_name: str, section: Section | None = None) -> FieldPlacement | None:
        query = select(FieldPlacement).where(FieldPlacement.module_key == module, FieldPlacement.api_name == api_name)
        if section is not None:
            query = query.where(FieldPlacement.section_id == section.id)
        return self.db.scalars(query.order_by(FieldPlacement.status)).first()  # 'active' before 'deleted'

    def definition_of(self, placement: FieldPlacement) -> FieldDefinition:
        return self.db.get(FieldDefinition, placement.definition_id)

    def last_order(self, module: str) -> int:
        return self.db.scalar(select(func.max(FieldPlacement.sort_order)).where(FieldPlacement.module_key == module)) or 0

    def make_room(self, module: str, after: int, by: int = 1) -> None:
        for later in self.db.scalars(
            select(FieldPlacement).where(FieldPlacement.module_key == module, FieldPlacement.sort_order > after)
        ):
            later.sort_order += by

    # ---- modules and sections

    def ensure_modules(self) -> None:
        products = self.db.get(Module, PRODUCTS)
        if products is None:
            raise SystemExit("There is no Products module — is this the ARK register?")
        for key, (label, parent) in MODULES.items():
            if self.db.get(Module, key) is not None:
                continue
            self.db.add(Module(module_key=key, label=label, sort_order=products.sort_order, active=True, setup_parent=parent))
            self.db.flush()  # the Standard layout is made on insert (app/models.py)
            self.log.append(f"module {key} ({label}){' under ' + parent if parent else ''}: created")

    def layout_of(self, module: str) -> Layout:
        layout = self.db.scalar(select(Layout).where(Layout.module_key == module, Layout.is_default))
        if layout is None:
            raise SystemExit(f"{module} has no Standard layout")
        return layout

    def ensure_section(self, module: str, label: str) -> Section:
        section = self.section(module, label)
        if section is None:
            top = self.db.scalar(select(func.max(Section.sort_order)).where(Section.module_key == module)) or 0
            section = Section(module_key=module, label=label, sort_order=top + 1, active=True, layout_id=self.layout_of(module).id)
            self.db.add(section)
            self.db.flush()
            self.log.append(f"{module}: section {label} created")
        return section

    def rehome(self, placement: FieldPlacement, module: str) -> None:
        """A field now owned by `module`: its placement and its definition both say so."""
        definition = self.definition_of(placement)
        placement.module_key = module
        placement.scope_key = module
        definition.scope_key = module
        definition.origin_module = module

    def move_sections(self) -> None:
        for label, (module, new_label) in SECTION_MOVES.items():
            section = self.section(PRODUCTS, label)
            if section is None:
                continue  # already moved
            section.module_key = module
            section.layout_id = self.layout_of(module).id
            section.label = new_label
            section.sort_order = 1
            moved = 0
            for placement in self.db.scalars(select(FieldPlacement).where(FieldPlacement.section_id == section.id)):
                self.rehome(placement, module)
                moved += 1
            self.db.flush()
            renamed = f" as {new_label}" if new_label != label else ""
            self.log.append(f"{label} -> module {module}{renamed}: {moved} fields")

    def move_field(self, module: str, api_name: str, to_module: str, to_section: Section, after: int, **changes) -> bool:
        """One field to another module or section, placed straight after sort order `after`."""
        placement = self.placement(module, api_name)
        if placement is None or (placement.module_key, placement.section_id) == (to_module, to_section.id):
            return False
        self.make_room(to_module, after)
        if to_module != module:
            self.rehome(placement, to_module)
        placement.section_id = to_section.id
        placement.sort_order = after + 1
        for name, value in changes.items():
            setattr(placement, name, value)
        self.db.flush()
        return True

    # ---- fields

    def delete(self, module: str, api_name: str, why: str, section: Section | None = None, park: Section | None = None) -> None:
        """Setup's own delete: logical, restorable. `park` re-files the row so its old section can go."""
        placement = self.placement(module, api_name, section)
        if placement is None:
            return
        definition = self.definition_of(placement)
        if park is not None and placement.section_id != park.id:
            placement.section_id = park.id
        if definition.status == "deleted" and placement.status == "deleted":
            return
        stamp = now()
        definition.status, definition.deleted_at = "deleted", stamp
        placement.status, placement.deleted_at, placement.deleted_by_cascade = "deleted", stamp, True
        self.log.append(f"{module}.{api_name} ({definition.label}): deleted — {why}")

    def add(
        self,
        module: str,
        section: Section,
        api_name: str,
        label: str,
        field_type: str,
        *,
        order: int,
        requirement: str = "Optional",
        description: str,
        editable: bool = True,
        max_length: int | None = None,
        picklist: str | None = None,
        values_note: str | None = None,
    ) -> None:
        """A new register field with a column of its own (migration 0045)."""
        if self.placement(module, api_name) is not None:
            return
        definition = self.db.scalar(
            select(FieldDefinition).where(FieldDefinition.scope_key == module, FieldDefinition.api_name == api_name)
        )
        if definition is None:
            definition = FieldDefinition(
                scope_key=module,
                api_name=api_name,
                label=label,
                field_type=field_type,
                picklist_key=picklist,
                max_length=max_length,
                values_note=values_note,
                description=description,
                use_case=USE_CASE,
                origin=ORIGIN,
                origin_module=module,
                status="active",
            )
            self.db.add(definition)
            self.db.flush()
        self.make_room(module, order - 1)
        self.db.add(
            FieldPlacement(
                definition_id=definition.id,
                api_name=api_name,
                module_key=module,
                scope_key=module,
                section_id=section.id,
                sort_order=order,
                capture_any_stage=False,
                requirement=requirement,
                required_on_create=False,
                value_mode="own",
                editable=editable,
                storage="column",
                status="active",
                provenance="register",
            )
        )
        self.db.flush()
        self.log.append(f"{module}.{api_name} ({label}): added, {requirement}")

    # ---- lists

    def ensure_status_list(self) -> None:
        if self.db.get(Picklist, EDITION_STATUS) is not None:
            return
        top = self.db.scalar(select(func.max(Picklist.sort_order))) or 0
        self.db.add(Picklist(picklist_key=EDITION_STATUS, label="Editions · Status", sort_order=top + 1, active=True, is_global=False))
        self.db.flush()
        for position, (key, label) in enumerate(STATUSES, start=1):
            self.db.add(
                PicklistValue(picklist_key=EDITION_STATUS, key=key, label=label, sort_order=position, active=True, is_system=True)
            )
        self.db.flush()
        self.log.append(f"picklist {EDITION_STATUS}: created (Draft, Current, Retired — system values)")

    def add_choice(self, picklist: str, key: str, label: str) -> None:
        values = self.db.get(Picklist, picklist).values
        if any(v.key == key for v in values):
            return
        last = max((v.sort_order for v in values), default=0)
        self.db.add(PicklistValue(picklist_key=picklist, key=key, label=label, sort_order=last + 1, active=True))
        self.db.flush()
        self.log.append(f"picklist {picklist}: '{label}' added")

    def mark_system(self, picklist: str, keys: tuple[str, ...]) -> None:
        for value in self.db.get(Picklist, picklist).values:
            if value.key in keys and not value.is_system:
                value.is_system = True
                self.log.append(f"picklist {picklist}: '{value.label}' is a system value now")

    def renumber(self, module: str) -> None:
        """Sort orders 1..n again, in the order they already stand — moves leave gaps."""
        rows = list(
            self.db.scalars(
                select(FieldPlacement)
                .where(FieldPlacement.module_key == module)
                .order_by(FieldPlacement.sort_order, FieldPlacement.id)
            )
        )
        for number, row in enumerate(rows, start=1):
            if row.sort_order != number:
                row.sort_order = number
        self.db.flush()

    def retire_list(self, picklist: str) -> None:
        row = self.db.get(Picklist, picklist)
        if row is not None and row.active:
            row.active = False
            self.log.append(f"picklist {picklist}: retired — no field uses it")


def apply(db) -> list[str]:
    r = Register(db)
    catalogue = r.section(PRODUCTS, "CATALOGUE ITEM")
    if catalogue is None or r.placement(PRODUCTS, CATALOGUE_ANCHOR) is None:
        raise SystemExit("Products has no CATALOGUE ITEM section with a Catalogue Category — is this the ARK register?")

    r.ensure_modules()
    r.ensure_status_list()
    r.move_sections()

    # ------------------------------------------------------------ Price Books
    book = r.section(PRICE_BOOKS, "PRICE BOOK")
    r.delete(PRICE_BOOKS, "region_code", "a price book's name replaces it", book)
    r.add(PRICE_BOOKS, book, "price_book_id", "Price Book ID", "autonumber", order=1, requirement="System",
          description="System reference for the price book, e.g. PB-0001.", values_note="PB-0001")
    r.add(PRICE_BOOKS, book, "price_book_name", "Price Book Name", "text", order=2, requirement="Mandatory", max_length=120,
          description="What the book is called — the region and currency it prices for, e.g. UAE AED.",
          values_note="USA USD · UAE AED · India INR")
    r.add(PRICE_BOOKS, book, "is_standard", "Standard Price Book", "checkbox", order=3, requirement="System", editable=False,
          description="The master book. Its prices are entered; every other book is worked out from them.")
    r.add(PRICE_BOOKS, book, "active", "Active", "checkbox", order=r.last_order(PRICE_BOOKS) + 1,
          description="Whether this book may be quoted from today.")

    # ------------------------------------------------------------ Editions
    edition = r.ensure_section(EDITIONS, EDITION_SECTION)
    if r.move_field(PRICES, "price_book_version", EDITIONS, edition, 1):
        r.log.append("price_book_version (Price Book Version): now the name of an edition, on Editions")
    name = r.placement(EDITIONS, "price_book_version")
    if name is not None:
        definition = r.definition_of(name)
        if definition.max_length != 40:
            definition.max_length = 40
        definition.description = "The name of this edition of the price list, e.g. 2026-H2."
    r.add(EDITIONS, edition, "edition_id", "Edition ID", "autonumber", order=1, requirement="System",
          description="System reference for the edition, e.g. PBE-0001.", values_note="PBE-0001")
    last = r.last_order(EDITIONS)
    r.add(EDITIONS, edition, "status", "Status", "picklist", order=last + 1, requirement="System", editable=False,
          picklist=EDITION_STATUS,
          description="Draft while it is being prepared, Current while it is sold from, Retired afterwards.")
    r.add(EDITIONS, edition, "effective_from", "Effective From", "date", order=last + 2,
          description="The day this edition comes into use. Set when it is made current, if left empty.")
    r.add(EDITIONS, edition, "effective_to", "Effective To", "date", order=last + 3, requirement="System", editable=False,
          description="The day this edition stopped being used — set when the next one is made current.")
    r.add(EDITIONS, edition, "notes", "Notes", "longtext", order=last + 4,
          description="What changed in this edition, and why.")

    # ------------------------------------------------------------ Prices
    matrix = r.section(PRICES, "PRICE MATRIX")
    r.delete(PRICES, "is_derived", "prices are entered; CPQ's rules work them out from phase 4", matrix)
    price = r.placement(PRICES, "list_price_usa_usd")
    if price is not None and r.move_field(PRODUCTS, "pct_of_annual_licence", PRICES, matrix, price.sort_order):
        r.log.append("pct_of_annual_licence (% of Annual Licence): now a Support product's price, on Prices")
    size = r.placement(PRICES, "size")
    if size is not None:
        definition = r.definition_of(size)
        if definition.field_type != "lookup":
            definition.field_type, definition.picklist_key, definition.lookup_target = "lookup", None, "deployment_size"
            definition.description = "The deployment size this price applies to — a row of the Sizing Guide."
            r.log.append("price_book_entries.size: a dropdown -> a lookup to the Sizing Guide")

    # ------------------------------------------------------------ Sizing Guide
    sizing = r.section(SIZES, "DEPLOYMENT SIZE")
    code = r.placement(SIZES, "size_code")
    if code is not None:
        definition = r.definition_of(code)
        if definition.field_type != "text":
            definition.field_type, definition.picklist_key, definition.max_length = "text", None, 20
            definition.description = "The size's name as it is quoted: XS through Unlimited."
            r.log.append("deployment_sizes.size_code: a dropdown -> text (a size is a record now)")
    r.add(SIZES, sizing, "size_id", "Size ID", "autonumber", order=1, requirement="System",
          description="System reference for the size, e.g. SZ-0001.", values_note="SZ-0001")
    r.add(SIZES, sizing, "active", "Active", "checkbox", order=r.last_order(SIZES) + 1,
          description="Whether prices are set at this size today.")
    r.retire_list("products__size_code")
    r.retire_list("products__size")

    # ------------------------------------------------------------ Products
    anchor = r.placement(PRODUCTS, CATALOGUE_ANCHOR)
    after = anchor.sort_order
    for api_name, condition, what in (
        ("coverage", SUPPORT_ONLY, "a Support product"),
        ("tier", SUPPORT_ONLY, "a Support product"),
        ("role", SERVICE_ONLY, "a Service product"),
        ("level", SERVICE_ONLY, "a Service product"),
    ):
        # Each goes straight after Catalogue Category, so they end up in the
        # order Level, Role, Tier, Coverage.
        if r.move_field(PRODUCTS, api_name, PRODUCTS, catalogue, after, storage="custom_fields", visibility_condition=condition):
            r.log.append(f"products.{api_name}: now a field of {what}, shown after Catalogue Category")
    r.add_choice("products__unit_of_measure", "PER_USER", "Per user")
    r.mark_system("products__pricing_basis", ("BY_T_SHIRT_SIZE", "PCT_OF_LICENCE"))

    rate_card = r.section(PRODUCTS, "SERVICES RATE CARD")
    for api_name in ("rate_per_hour_—_offsite", "rate_per_day_—_offsite", "rate_per_hour_—_onsite", "rate_per_day_—_onsite"):
        r.delete(PRODUCTS, api_name, "a service's day rate is its price, in a price book", rate_card, park=catalogue)

    # ------------------------------------------------------------ Service Category
    categories = r.section(PRODUCTS, "SERVICE CATEGORY")
    line = r.section(QUOTES, "QUOTE LINE ITEM")
    level = r.placement(QUOTES, "service_level")
    if categories is not None:
        r.delete(PRODUCTS, "sort_order", "a dropdown's choices already have an order", categories, park=catalogue)
        if line is not None and level is not None and r.move_field(PRODUCTS, "service_category", QUOTES, line, level.sort_order):
            r.log.append("service_category (Service Category): now chosen on a quote line, on Quotes")

    # ------------------------------------------------------------ empty sections
    for label in ("SERVICES RATE CARD", "SERVICE CATEGORY", "SUPPORT TIER"):
        section = r.section(PRODUCTS, label)
        if section is None:
            continue
        held = db.scalar(select(func.count()).select_from(FieldPlacement).where(FieldPlacement.section_id == section.id))
        if held:
            raise SystemExit(f"Products section {label} still holds {held} field(s) — stop and look.")
        db.delete(section)
        r.log.append(f"products: empty section {label} removed")
    # Only once something moved: a second run must find nothing to do.
    if r.log:
        for module in (PRODUCTS, *MODULES):
            r.renumber(module)
    db.flush()
    return r.log


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "dry"
    with SessionLocal() as db:
        log = apply(db)
        print(f"Products phase 3 register — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if not log:
            db.rollback()
            return 0
        if mode == "dry":
            validation = _validation_out(build_snapshot(db))
            print(f"\nValidation: {'ok' if validation.ok else 'FAILED'}")
            for error in validation.errors:
                print(f"  error: {error}")
            db.rollback()
            print("Dry run — nothing written. Re-run with --apply.")
            return 0 if validation.ok else 1
        try:
            result = _publish(db, build_snapshot(db), NOTE, None)
        except HTTPException as exc:
            db.rollback()
            print(f"\nNot published, nothing written: {exc.detail}")
            return 1
        db.commit()
        print(f"\nPublished metadata version {result.version.version_no}.")
        for path in result.written:
            print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
