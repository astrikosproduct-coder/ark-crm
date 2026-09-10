"""
The pipeline split, read from PostgreSQL.

Leads 0-3, Opportunities 4-6, Deals 7-9 — which module owns which stage, which
module a record reads its identity through, and therefore which field
definitions belong to which business table.

WHY THIS EXISTS
---------------
Until Round-6 gap closure this knowledge lived only in
frontend/spec/module_split.json, and the backend's share of it was a hardcoded
tuple in app/custom_fields.py:

    "opportunities": ("opportunities", "leads")   # a fact with no source

That is fine while /api/opportunities is answered by MSW from localStorage. It
stops being fine the moment FastAPI answers it, because the backend then has to
decide what an Opportunity field is and cannot read a frontend JSON file to find
out. Round 7 removes MSW; this removes the guess before then.

Every answer here comes from `modules.is_pipeline` / `parent_module` /
`parent_link` and `stages.owner_module` — see migration 0005.

WHAT THIS IS NOT
----------------
It is not a port of src/lib/spec/moduleSplit.ts. That file PROJECTS field rows:
it re-homes a Stage 5 Leads field onto Opportunities, adds the shared,
own-instance and read-through copies, relabels them and renumbers the sections.
None of that happens here, and it must not — two implementations of one
projection rule would drift the first time either changed.

This answers only the structural questions, which are facts about modules and
stages rather than about individual fields:

    which modules are pipeline modules
    which stages does each own
    which module is which module's parent, through which link
    which field definitions may supply values for a given business table

The projection stays where it is, and reads its inputs from here.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Module, Stage


def pipeline_modules(db: Session) -> list[str]:
    """Pipeline modules in stage order — leads, opportunities, deals."""
    modules = {
        m.module_key: m
        for m in db.scalars(select(Module).where(Module.is_pipeline.is_(True)))
    }
    ordered = sorted(
        modules.values(),
        key=lambda m: (range_of(db, m.module_key) or (99, 99))[0],
    )
    return [m.module_key for m in ordered]


def range_of(db: Session, module_key: str) -> tuple[int, int] | None:
    """
    The inclusive stage range a module owns, DERIVED from stages.owner_module.

    Derived rather than stored, so a stage that changes hands cannot leave a
    range behind saying otherwise. There is one place a stage's owner is
    written down, and this reads it.
    """
    stages = [
        s.stage
        for s in db.scalars(select(Stage).where(Stage.owner_module == module_key))
    ]
    return (min(stages), max(stages)) if stages else None


def owner_of_stage(db: Session, stage: int) -> str | None:
    row = db.get(Stage, stage)
    return row.owner_module if row else None


def parent_of(db: Session, module_key: str) -> tuple[str | None, str | None]:
    """(parent module, the lookup field holding its id) for a pipeline module."""
    module = db.get(Module, module_key)
    if module is None:
        return (None, None)
    return (module.parent_module, module.parent_link)


# source_modules_for() USED TO LIVE HERE. It walked the module parent chain to
# answer "which field_metadata modules may supply values for this business
# table" — the guess that existed only because placement was computed in the
# browser and the backend had to reconstruct the answer.
#
# The question is now answered directly, because a placement's module_key IS
# the business table:
#
#     app/metadata_resolver.py::placements_of(db, table, storage="custom_fields")
#
# Nothing derives placement any more. What remains in this file are STRUCTURAL
# facts about modules and stages — which modules are pipeline modules, which
# stages each owns, which is whose parent — and those are still facts, still
# read from `modules` and `stages`, and still not a projection.


def split_config(db: Session) -> dict:
    """
    The DB-owned blocks of spec/module_split.json.

    regenerate_spec.py writes these into the file, so the values the frontend
    splits on come from PostgreSQL rather than from a hand-edited JSON that
    nothing verifies. The blocks this does NOT produce — `own`, `read_through`,
    `shared`, `section_order`, `relocated_fields`, `register_corrections` — are
    hand-authored judgement calls with no database representation, and are
    preserved from the existing file untouched. See regenerate_spec.py.
    """
    modules = pipeline_modules(db)
    return {
        "pipeline": modules,
        "ranges": {m: list(range_of(db, m) or []) for m in modules},
        "stage_field": {
            m: db.get(Module, m).stage_field
            for m in modules
            if db.get(Module, m).stage_field
        },
        "reassign": _reassign(db, modules),
        "parent_of": {
            m: parent_of(db, m)[0] for m in modules if parent_of(db, m)[0]
        },
        "parent_link": {
            m: parent_of(db, m)[1] for m in modules if parent_of(db, m)[1]
        },
    }


def _reassign(db: Session, modules: list[str]) -> dict[str, dict[str, str]]:
    """
    Stage -> owning module, for every stage a module does NOT own itself.

    module_split.json expresses this keyed by the register sheet the fields are
    filed on, which is `leads` for the whole 0-7 pipeline. Derived here from
    stage ownership so the two cannot disagree.
    """
    register_sheet = modules[0] if modules else None
    if not register_sheet:
        return {}

    out: dict[str, str] = {}
    for stage in db.scalars(select(Stage).order_by(Stage.stage)):
        if stage.owner_module and stage.owner_module != register_sheet:
            out[str(stage.stage)] = stage.owner_module
    return {register_sheet: out} if out else {}
