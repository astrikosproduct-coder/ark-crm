"""
v1.2.1 — an export never fails on text a worksheet can't hold.

    python run_tests.py test_export_text.py     (against the disposable copy)

Found on production, 22 Oct 2026: one Lead's text held Excel's in-cell line
break (a vertical tab), and every Opportunities export failed with "That didn't
work". The spreadsheet library refuses control characters; the export now
writes a line break for that one and drops the rest, and an import cleans them
as it reads.
"""

import io
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.database import engine  # noqa: E402

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app import requirements  # noqa: E402
from app.main import app  # noqa: E402
from app.spreadsheets.fields import clean_text  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
admin = sign_in_as_admin(app)
requirements.ENFORCED = False

failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {name}")
    else:
        failed.append(f"{name} — {detail}")
        print(f"  FAIL  {name} — {detail}")


PLACE = "Aji Pangeran Tumenggung Pranoto International Airport," + chr(11) + "Samarinda" + chr(1)
CLEAN = "Aji Pangeran Tumenggung Pranoto International Airport," + chr(10) + "Samarinda"

print("=" * 74)
print("  v1.2.1 — exports survive control characters")
print("=" * 74)

check("a vertical tab becomes a line break; other control characters go", clean_text(PLACE) == CLEAN, repr(clean_text(PLACE)))
check("anything that isn't text is left alone", clean_text(42) == 42 and clean_text(None) is None)

r = client.post("/api/leads", json={
    "opportunity_name": "Export text probe", "bd_owner": admin.user_id, "currency": "USD",
    "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN", "city_state": PLACE,
})
check("a Lead holding such text saves (as it did on production)", r.status_code == 201, r.text[:200])
lead = r.json()["lead_id"]
r = client.post("/api/opportunities", json={
    "parent_lead": lead, "project_stage": "4_RFP_RFI", "lead_status": "OPEN", "conversion_note": "Export text probe.",
})
check("…and becomes an Opportunity", r.status_code == 201, r.text[:200])

for module, params in (("opportunities", {"lead_status_ne": "CONVERTED"}), ("opportunities", {}), ("leads", {})):
    r = client.get(f"/api/spreadsheets/{module}/export", params=params)
    check(f"the {module} export still downloads ({params or 'all'})", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        book = load_workbook(io.BytesIO(r.content), read_only=True)
        found = [c for ws in book.worksheets for row in ws.iter_rows(values_only=True) for c in row
                 if isinstance(c, str) and "Samarinda" in c]
        check(f"…with the text on two lines ({module})", CLEAN in found, repr(found[:2]))

print()
if failed:
    print(f"{len(failed)} FAILED")
    for line in failed:
        print(f"  - {line}")
    sys.exit(1)
print("all passed")
