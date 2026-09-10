"""
PostgreSQL -> frontend/spec/*.json. The one supported direction.

Run:  python regenerate_spec.py                 # dry run: what differs, nothing written
      python regenerate_spec.py --check         # same, but exits 1 on any difference
      python regenerate_spec.py --apply         # write fields/picklists/stages.json
      python regenerate_spec.py --version 3 --apply

Writes three GENERATED ARTIFACTS:

    frontend/spec/fields.json
    frontend/spec/picklists.json
    frontend/spec/stages.json

Do not hand-edit them. An edit there is a local change with no path back into
the database — PostgreSQL does not read them — and the next publish overwrites
it. To change the register, change it in Administration and publish.

Three spec files are NOT written and are not the metadata layer's business:
extensions.json (hand-maintained sidecar), criteria.json, gates.json and
thresholds.json (still generated from the workbook by build_spec.py). Round 6
does not own them.

WHY --check COMPARES MEANING, NOT BYTES
----------------------------------------
Three of the register's 566 rows carry their 24 keys in a different order to
the other 563. Same keys, same values — a byte comparison would report a
difference every time, forever, and teach everybody to ignore the check. What
matters is whether the frontend would read the same configuration, so that is
what is compared. See compare_documents() in app/metadata_spec.py.

The parity check is how Round 6 was verified before anything trusted it: the
bootstrap loaded 566 rows out of the register, and --check confirmed the
database writes the same register back.
"""

import sys

from sqlalchemy import select

from app.database import SessionLocal, engine
from app.metadata_spec import (
    SPEC_DIR,
    build_snapshot,
    compare_documents,
    orphaned_sidecar_refs,
    read_spec_documents,
    spec_documents,
    validate_snapshot,
    write_spec_documents,
)
from app.models import MetadataVersion

# app.database sets echo=True, which is useful when debugging a request
# and unreadable in a command-line script that writes 566 rows. The
# engine's own configuration is left alone; only this process is quiet.
# app.database creates the engine with echo=True, which is useful when
# debugging a request and unreadable in a script that writes 566 rows.
# echo is an engine flag that bypasses logger levels, so it is turned
# off on the object; this process only, the module is left alone.
engine.echo = False


def snapshot_for(db, version_no: int | None):
    """The live draft, or a published version's frozen copy of itself."""
    if version_no is None:
        return build_snapshot(db), "the live draft"

    version = db.scalar(
        select(MetadataVersion).where(MetadataVersion.version_no == version_no)
    )
    if version is None:
        print(f"No metadata version {version_no}.")
        sys.exit(1)
    return version.snapshot, f"published version {version_no}"


def main(argv: list[str]) -> None:
    apply = "--apply" in argv
    check = "--check" in argv

    version_no = None
    if "--version" in argv:
        version_no = int(argv[argv.index("--version") + 1])

    db = SessionLocal()
    try:
        snapshot, source = snapshot_for(db, version_no)
    finally:
        db.close()

    documents = spec_documents(snapshot)

    print(f"Source: {source}")
    print(f"  fields.json      {len(documents['fields.json'])} rows")
    print(f"  picklists.json   {len(documents['picklists.json'])} picklists")
    print(f"  stages.json      {len(documents['stages.json'])} stages")

    # A configuration that will not validate must not be written to disk, even
    # by hand from the command line: the frontend imports these files at build
    # time and a broken one takes the whole application down at startup.
    result = validate_snapshot(snapshot)
    if result.errors:
        print(f"\n{len(result.errors)} error(s) — refusing to write:")
        for error in result.errors:
            print(f"  ! {error}")
        sys.exit(1)
    if result.warnings:
        print(f"\n{len(result.warnings)} warning(s) — register gaps, not blockers:")
        for warning in result.warnings[:10]:
            print(f"  · {warning}")
        if len(result.warnings) > 10:
            print(f"  · … and {len(result.warnings) - 10} more")

    orphans = orphaned_sidecar_refs(snapshot)
    if orphans:
        print(
            f"\n{len(orphans)} spec/extensions.json key(s) name a field this "
            f"configuration no longer carries:"
        )
        for ref in orphans[:10]:
            print(f"  · {ref}")

    differences = compare_documents(documents, read_spec_documents())

    if not differences:
        print("\nThe files on disk already match the database.")
    else:
        print(f"\n{len(differences)} difference(s) against the files on disk:")
        for line in differences[:40]:
            print(f"  · {line}")
        if len(differences) > 40:
            print(f"  · … and {len(differences) - 40} more")

    if apply:
        written = write_spec_documents(documents)
        print("\nWritten:")
        for path in written:
            print(f"  {path.relative_to(SPEC_DIR.parent.parent)}")
        return

    if check and differences:
        sys.exit(1)

    if not check:
        print("\nDry run. Re-run with --apply to write the files.")


if __name__ == "__main__":
    main(sys.argv[1:])
