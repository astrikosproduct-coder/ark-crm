"""
THE REGISTER AS LAST PUBLISHED: what the live app runs on.

Decided 21 Sep 2026: a change made in Administration and published reaches
the live app with no rebuild. That needs both halves of the app to read the
same thing at runtime:

    the browser   GET /api/spec at start-up (app/routers/spec.py), which
                  replaces the copy of fields/picklists/stages built into it
    the server    the required-field check (app/requirements.py)

Both read the latest PUBLISHED snapshot in `metadata_versions`, rendered by
the same `spec_documents()` that writes spec/*.json on publish. The draft (the
tables Administration edits directly) has no effect until someone publishes
it, which is what publishing is for.

The rendered documents are cached per version, and each read costs one small
query for the latest version number. A publish makes a new version, so the
next request sees it; a browser already open sees it on its next page load.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .metadata_spec import FIELDS_JSON, PICKLISTS_JSON, STAGES_JSON, spec_documents
from .models import MetadataVersion


@dataclass
class Published:
    version_no: int
    fields: list[dict[str, Any]]
    picklists: dict[str, list[dict[str, Any]]]
    stages: list[dict[str, Any]]
    by_module: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    #: key -> label, per picklist, for conditions written against labels.
    labels: dict[str, dict[str, str]] = field(default_factory=dict)
    #: module -> (first, last) stage it owns, from `stages.owner_module`.
    ranges: dict[str, tuple[int, int]] = field(default_factory=dict)

    def fields_of(self, module: str) -> list[dict[str, Any]]:
        return self.by_module.get(module, [])

    def label(self, picklist: str | None, key: Any) -> str | None:
        if not picklist or key is None:
            return None
        return self.labels.get(picklist, {}).get(str(key))

    def stage_range(self, module: str) -> tuple[int, int] | None:
        """The stages a pipeline module owns. Never `applies_to`, which is stale."""
        return self.ranges.get(module)


_lock = threading.Lock()
_cache: dict[int, Published] = {}


def _latest_id(db: Session) -> tuple[int, int] | None:
    row = db.execute(
        select(MetadataVersion.id, MetadataVersion.version_no)
        .where(MetadataVersion.status == "published")
        .order_by(MetadataVersion.version_no.desc())
        .limit(1)
    ).first()
    return (row.id, row.version_no) if row else None


def published(db: Session) -> Published | None:
    """The latest published register, or None on a database never published."""
    latest = _latest_id(db)
    if latest is None:
        return None
    version_id, version_no = latest
    cached = _cache.get(version_id)
    if cached is not None:
        return cached

    snapshot = db.scalar(select(MetadataVersion.snapshot).where(MetadataVersion.id == version_id)) or {}
    documents = spec_documents(snapshot)
    fields = documents[FIELDS_JSON]
    by_module: dict[str, list[dict[str, Any]]] = {}
    for row in fields:
        by_module.setdefault(row["module"], []).append(row)
    picklists = documents[PICKLISTS_JSON]
    owned: dict[str, list[int]] = {}
    for stage in snapshot.get("stages", []):
        if stage.get("owner_module") and stage.get("active", True):
            owned.setdefault(stage["owner_module"], []).append(stage["stage"])
    result = Published(
        version_no=version_no,
        fields=fields,
        picklists=picklists,
        stages=documents[STAGES_JSON],
        by_module=by_module,
        labels={key: {str(v["key"]): v["label"] for v in values} for key, values in picklists.items()},
        ranges={module: (min(s), max(s)) for module, s in owned.items()},
    )
    with _lock:
        _cache.clear()  # only the latest is ever wanted
        _cache[version_id] = result
    return result
