"""
Products: what a pursuit may name, and what names a product (step 1, 12 Oct 2026),
and what a product record is made of (phase 2, 13 Oct 2026).

FOUR FIELDS PICK FROM THE CATALOGUE
    Leads   S!aP Solution Suite · Suite Demonstrated · Secondary S!aP Suites
    Deals   Expansion Suites
They were typed by hand from 3 Sep 2026, when Products had no table. Each now
stores a product_id — one for a single pick, several joined by commas for a
several-pick — in the column it always had.

WHAT WAS TYPED IS KEPT, NEVER GUESSED AT
    Those columns still hold whatever was typed before the catalogue existed
    ("Customized", say). Nothing here rewrites it: it reads back as the text it
    is, and it is refused only when a save CHANGES the field to something that
    is not a product. products_typed_suites.py reports those values and
    converts the ones that are exactly a product's name.

A PICK IS CHECKED WHEN IT CHANGES, against the field's own rule
    The product must exist, be active, and pass the field's lookup filter
    (spec/extensions.json `lookup_filter_expr` — "Catalogue Category must be
    Segment Library" for the suites). The rule is read from the spec, as the
    form reads it; no category is named in this file.

NO FOREIGN KEY on those columns, for the reason above: a constraint would have
to delete what was typed first. So nothing in the database stops a product
being deleted from under a Lead — `records_naming` is what does: the delete
route refuses while any Lead or Deal still holds the product's id.

WHICH REGISTER FIELDS ARE A PRODUCT'S (phase 2)
    A product's fields are the register section holding its key, Product ID.
    `record_fields` reads that off the published register — no section is
    named here, so renaming it in Setup changes nothing, and a field added to
    it in Setup is a product's field at once. The form draws the same section
    (src/lib/products.ts).

    When this was written the Products module also described the price matrix
    and five pricing tables, section by section, and the scoping was what kept
    a product from being asked for a Size or an FX rate. Phase 3 (13 Oct 2026)
    gave those sections modules of their own — Price Books, Prices, Editions,
    CPQ, the Sizing Guide — so today the product's section is the whole module.
    The scoping stays: it costs nothing, and it holds if a section is added.

RELATED, ON A PRODUCT'S PAGE
    Every pursuit naming the product, with the two figures the Group companies
    tab shows — Open pipeline and Won, by app/revenue.py's rule, each pursuit
    counted once however many of its fields name the product.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .live_register import published
from .messages import picked_record_missing, refusal
from .models import Deal, Lead, Opportunity, Product

PRODUCT_ID_PATTERN = re.compile(r"^PRD-\d+$")

MODULE = "products"
#: The register field that is a product's key. The section holding it is the
#: product; see record_fields.
KEY_FIELD = "product_id"

#: The product-picking fields of each live module: api_name -> picks several.
PRODUCT_PICKS: dict[str, dict[str, bool]] = {
    "leads": {
        "sap_solution_suite": False,
        "suite_demonstrated": False,
        "secondary_sap_suites": True,
    },
    "deals": {"expansion_suites": True},
}

#: Room in the several-pick columns (VARCHAR 255): "PRD-0001," is nine characters.
MAX_PICKS = 25


def picks_several(module: str, api_name: str) -> bool:
    return PRODUCT_PICKS.get(module, {}).get(api_name, False)


# ------------------------------------------------------------------ stored form


def split_picks(stored: Any) -> list[str]:
    """
    A several-pick column as the list a form holds.

    Product ids come back as ids. Anything else is what was typed before the
    catalogue existed and comes back WHOLE, as one entry — "Omnific and Cognus"
    is one thing a person wrote, not two picks to be inferred.
    """
    if isinstance(stored, list):
        return [str(v) for v in stored if v not in (None, "")]
    text = str(stored or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in text.split(",")]
    if all(PRODUCT_ID_PATTERN.match(p) for p in parts):
        return parts
    return [text]


def join_picks(picks: Iterable[str] | None) -> str | None:
    seen: list[str] = []
    for pick in picks or []:
        if pick and pick not in seen:
            seen.append(pick)
    return ",".join(seen) or None


def product_names(db: Session) -> dict[str, str]:
    """product_id -> Item Name, for a page's worth of rows at once."""
    return {p.product_id: p.item_name for p in db.scalars(select(Product))}


def pick_labels(module: str, record: Any, names: dict[str, str]) -> dict[str, str]:
    """
    The `__labels` entries for a record's product fields: the product's name
    for a single pick, the names joined for a several-pick. What was typed
    reads as typed.
    """
    out: dict[str, str] = {}
    for api_name, several in PRODUCT_PICKS.get(module, {}).items():
        stored = getattr(record, api_name, None)
        if not stored:
            continue
        if several:
            out[api_name] = ", ".join(names.get(p, p) for p in split_picks(stored))
        elif stored in names:
            out[api_name] = names[stored]
    return out


# ------------------------------------------------------------------ the check


def _filter_of(module: str, api_name: str) -> str | None:
    from .spreadsheets.fields import extension_of  # local: spreadsheets imports the metadata layer

    return extension_of(module, api_name).get("lookup_filter_expr")


def allowed_for(db: Session, module: str, api_name: str, product: Product) -> bool:
    """Whether the field's own lookup filter lets this product be picked."""
    from .spreadsheets.fields import Directory, matches_filter, product_target

    return matches_filter(_filter_of(module, api_name), product_target(product), Directory(db))


def _refuse(code: str, message: str, details: list[str]) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, refusal(code, message, details))


def check_picks(db: Session, module: str, api_name: str, value: Any, stored: Any) -> None:
    """
    Refuse a pick the catalogue does not offer for this field.

    Checked when the field is SET or CHANGED, never on a save that leaves it
    alone — a Lead still holding what was typed in September must stay
    savable, or the first edit of any other field would be refused.
    """
    several = picks_several(module, api_name)
    new = split_picks(value) if several else ([str(value)] if value not in (None, "") else [])
    old = split_picks(stored) if several else ([str(stored)] if stored not in (None, "") else [])
    if new == old:
        return
    if len(new) > MAX_PICKS:
        raise _refuse(
            "TOO_MANY_PRODUCTS",
            f"That is more than {MAX_PICKS} products.",
            ["Remove some, then save."],
        )
    for pick in new:
        if pick in old and not PRODUCT_ID_PATTERN.match(pick):
            # Typed before the catalogue, and still sitting beside a new pick.
            raise _refuse(
                "TYPED_PRODUCT",
                f"“{pick}” was typed before the product list existed.",
                ["Remove it from the field.", "Pick the products from the list, then save."],
            )
        if pick in old:
            continue
        product = db.get(Product, pick) if PRODUCT_ID_PATTERN.match(pick) else None
        if product is None:
            raise picked_record_missing("product")
        if not product.active:
            raise _refuse(
                "PRODUCT_INACTIVE",
                f"{product.item_name} is no longer sold.",
                ["Pick another product, then save."],
            )
        if not allowed_for(db, module, api_name, product):
            raise _refuse(
                "PRODUCT_NOT_ALLOWED",
                f"{product.item_name} can't be picked in this field.",
                ["Pick one from the list the field offers, then save."],
            )


# ------------------------------------------------------------------ the record


def record_fields(db: Session) -> set[str] | None:
    """
    The api_names a product record holds: every field in the register section
    that holds Product ID. None when nothing is published yet — the caller then
    applies no scope, as it would for any module.
    """
    register = published(db)
    if register is None:
        return None
    fields = register.fields_of(MODULE)
    section = next((f.get("section") for f in fields if f["api_name"] == KEY_FIELD), None)
    if section is None:
        return None
    return {f["api_name"] for f in fields if f.get("section") == section}


def field_label(db: Session, api_name: str) -> str:
    """The field's label as the form shows it, for a refusal that names it."""
    register = published(db)
    for f in register.fields_of(MODULE) if register else []:
        if f["api_name"] == api_name:
            return f.get("label") or api_name
    return api_name.replace("_", " ").title()


def sku_key(value: Any) -> str:
    """A SKU as it is compared: spaces around it and its case do not make it another."""
    return str(value or "").strip().lower()


def guard_sku(db: Session, product: Product) -> None:
    """Refuse a SKU Code another product already has (409 SKU_EXISTS)."""
    wanted = sku_key(product.sku_code)
    if not wanted:
        return
    for other in db.scalars(select(Product).where(Product.product_id != product.product_id)):
        if sku_key(other.sku_code) == wanted:
            label = field_label(db, "sku_code")
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                refusal(
                    "SKU_EXISTS",
                    f"{other.item_name} already has the {label} {other.sku_code}.",
                    [f"Give this product a {label} of its own, then save."],
                    product=other.product_id,
                    fields=[{"api_name": "sku_code", "label": label}],
                ),
            )


def guard_dates(db: Session, product: Product) -> None:
    """Refuse a product that stops being sold before it starts (422 EFFECTIVE_DATES)."""
    start, end = product.effective_from, product.effective_to
    if start is None or end is None or end >= start:
        return
    first, last = field_label(db, "effective_from"), field_label(db, "effective_to")
    raise _refuse(
        "EFFECTIVE_DATES",
        f"{last} is before {first}.",
        [f"Set {last} on or after {first}, then save."],
    )


def records_naming(db: Session, product_id: str) -> list[str]:
    """
    The ids of every Lead and Deal that HOLDS this product's id, sorted — what a
    delete would leave pointing at nothing.

    Not `pursuits_naming`: that lists a pursuit once, as the record it is today,
    and so leaves out a converted Lead. A converted Lead still holds the id,
    and its Opportunity and Deal show the product through it.
    """
    holders = (("leads", Lead, "lead_id"), ("deals", Deal, "deal_id"))
    found: set[str] = set()
    for module, model, id_attr in holders:
        for api_name, several in PRODUCT_PICKS[module].items():
            column = getattr(model, api_name)
            clause = column.contains(product_id) if several else column == product_id
            for record in db.scalars(select(model).where(clause)):
                if api_name in _names(product_id, module, record):
                    found.add(getattr(record, id_attr))
    return sorted(found)


# ------------------------------------------------------------------ related


def _names(product_id: str, module: str, record: Any) -> list[str]:
    """Which of the record's product fields name this product."""
    hits = []
    for api_name, several in PRODUCT_PICKS.get(module, {}).items():
        stored = getattr(record, api_name, None)
        if (product_id in split_picks(stored)) if several else (stored == product_id):
            hits.append(api_name)
    return hits


def pursuits_naming(db: Session, product_id: str) -> dict[str, Any]:
    """
    Every Lead, Opportunity and Deal that names this product, and what they add
    up to.

    An Opportunity or a Deal names it through its Lead (those fields are shown
    From the Lead and stored nowhere else); a Deal also names it itself, in
    Expansion Suites. `fields` says which field did, per record, so the page
    can say "Suite Demonstrated" rather than leave the reader to work it out.
    A pursuit is listed once, as the record it is today: a converted Lead is
    left out, because its Opportunity or Deal is the row.
    """
    from .revenue import revenue_context, revenue_of, root_lead_of

    ctx = revenue_context(db)
    leads = {l.lead_id: l for l in db.scalars(select(Lead))}
    rows: list[dict[str, Any]] = []
    totals = {"pipeline_usd": 0.0, "pipeline_count": 0, "won_usd": 0.0, "won_count": 0}

    sources = (
        ("leads", list(leads.values()), "lead_id"),
        ("opportunities", list(db.scalars(select(Opportunity))), "opportunity_id"),
        ("deals", list(db.scalars(select(Deal))), "deal_id"),
    )
    for module, records, id_attr in sources:
        for record in records:
            root = leads.get(root_lead_of(ctx, module, record) or "")
            named = [("leads", f) for f in (_names(product_id, "leads", root) if root is not None else [])]
            if module != "leads":
                named += [(module, f) for f in _names(product_id, module, record)]
            if not named:
                continue
            # A converted record's pursuit is listed once, as what it became.
            if record.lead_status == "CONVERTED":
                continue
            revenue = revenue_of(ctx, module, record)
            won = module == "deals" and getattr(record, "po_received_date", None) is not None
            if revenue["counted"] and (won or module != "deals"):
                usd = revenue["usd"] or 0.0
                totals["won_usd" if won else "pipeline_usd"] += usd
                totals["won_count" if won else "pipeline_count"] += 1
            rows.append(
                {
                    "module": module,
                    "id": getattr(record, id_attr),
                    "name": (root.opportunity_name if root is not None else None)
                    or getattr(record, "deal_name", None)
                    or getattr(record, id_attr),
                    "stage": getattr(record, "deal_stage", None) or getattr(record, "project_stage", None),
                    "status": record.lead_status,
                    "fields": [{"module": m, "api_name": f} for m, f in named],
                    "revenue": revenue,
                    "won": won,
                }
            )

    totals["pipeline_usd"] = round(totals["pipeline_usd"], 2)
    totals["won_usd"] = round(totals["won_usd"], 2)
    return {"records": rows, "total": totals}
