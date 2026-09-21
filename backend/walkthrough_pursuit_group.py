"""
The EC story, seeded so it can be clicked through — Partner-A and Partner-B bring
the same project, both are pursued, only the primary counts.

    python walkthrough_pursuit_group.py --seed      # create the demo records
    python walkthrough_pursuit_group.py --remove    # delete them again

Not a test (test_pursuit_groups.py is). This leaves real records behind on
purpose, every one named "DEMO — …" so nobody mistakes them for a pursuit, and
prints where to look:

  * Leads board, Stage 1 and Stage 3 columns — the Stage 1 card says
    "Secondary of LEAD-…", and the Stage 1 total leaves its value out.
  * Either lead -> Related tab -> Pursuit Group — both pursuits, one counted.
  * Partners -> either registration -> Conflict — "Both pursued".
  * A third lead for the same End Client — Save asks "join its group?".

Everything goes through the real API as the admin user, so every rule the
screens meet is the rule these records met.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import engine  # noqa: E402

engine.echo = False

from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
sign_in_as_admin(app)

PREFIX = "DEMO — "


def must(response, what: str) -> dict:
    if response.status_code >= 400:
        raise SystemExit(f"  could not {what}: {response.status_code} {response.text[:300]}")
    return response.json() if response.content else {}


def seed() -> None:
    ec = must(client.post("/api/accounts", json={"account_name": f"{PREFIX}EC Smart City Authority"}), "create EC")["id"]
    pa = must(client.post("/api/accounts", json={"account_name": f"{PREFIX}Partner-A Systems"}), "create Partner-A")["id"]
    pb = must(client.post("/api/accounts", json={"account_name": f"{PREFIX}Partner-B Integrators"}), "create Partner-B")["id"]

    reg_a = must(
        client.post("/api/registrations", json={"partner": pa, "end_client": ec, "project_name": f"{PREFIX}EC smart city programme", "estimated_value": 2_000_000}),
        "register Partner-A",
    )["id"]
    reg_b = must(
        client.post("/api/registrations", json={"partner": pb, "end_client": ec, "project_name": f"{PREFIX}EC smart city programme", "estimated_value": 3_000_000}),
        "register Partner-B",
    )["id"]

    conflict = must(
        client.post(
            "/api/conflicts",
            json={
                "registration_a": reg_a,
                "registration_b": reg_b,
                "who_registered_first": "Partner-A, by 14 days.",
                "stronger_client_relationship": "Both have separate access to EC procurement.",
                "better_delivery_capability": "Comparable.",
                "decision": "BOTH_PURSUED",
                "primary_registration": reg_a,
            },
        ),
        "decide the conflict",
    )

    lead_a = must(
        client.post(
            "/api/leads",
            json={
                "opportunity_name": f"{PREFIX}EC via Partner-A",
                "end_client": ec,
                "customer_partner_si": pa,
                "deal_source": "PARTNER_SOURCED",
                "partner_deal_registration": reg_a,
                "project_stage": "3_PRESCRIPTION",
                "lead_status": "OPEN",
                "currency": "USD",
                "estimated_value": 2_000_000,
            },
        ),
        "create Partner-A's lead",
    )
    lead_b = must(
        client.post(
            "/api/leads",
            json={
                "opportunity_name": f"{PREFIX}EC via Partner-B",
                "end_client": ec,
                "customer_partner_si": pb,
                "deal_source": "PARTNER_SOURCED",
                "partner_deal_registration": reg_b,
                "project_stage": "1_DEMO",
                "lead_status": "OPEN",
                "currency": "AED",
                "fx_rate_at_entry": 3.6725,
                "estimated_value": 11_017_500,
            },
        ),
        "create Partner-B's lead",
    )

    print("\n  Seeded:")
    print(f"    End Client        {ec}")
    print(f"    Registrations     {reg_a} (Partner-A, primary)  {reg_b} (Partner-B)")
    print(f"    Conflict          {conflict['id']} — Both pursued → {conflict.get('pursuit_group')}")
    print(f"    Partner-A's lead  {lead_a['id']}  Stage 3  USD 2,000,000  counted: {lead_a['revenue']['counted']}")
    print(
        f"    Partner-B's lead  {lead_b['id']}  Stage 1  AED 11,017,500 (= $3,000,000)  "
        f"counted: {lead_b['revenue']['counted']} ({lead_b['revenue']['excluded']})"
    )
    print("\n  Open the Leads board: Stage 3 counts $2,000,000; Stage 1 shows Partner-B's card as a")
    print("  secondary and leaves its $3,000,000 out. Remove with --remove.")


def remove() -> None:
    def demo(collection: str, name_field: str) -> list[dict]:
        return [r for r in client.get(f"/api/{collection}").json() if str(r.get(name_field) or "").startswith(PREFIX)]

    leads = demo("leads", "opportunity_name")
    for lead in leads:
        if lead.get("pursuit_group"):
            client.post(
                f"/api/pursuit-groups/{lead['pursuit_group']}/members/{lead['id']}/remove",
                json={"reason": "Demo data removed."},
            )
    for lead in leads:
        must(client.delete(f"/api/leads/{lead['id']}"), f"delete {lead['id']}")

    registrations = demo("registrations", "project_name")
    ids = {r["id"] for r in registrations}
    for conflict in client.get("/api/conflicts").json():
        if conflict.get("registration_a") in ids or conflict.get("registration_b") in ids:
            must(client.delete(f"/api/conflicts/{conflict['id']}"), f"delete {conflict['id']}")
    for registration in registrations:
        must(client.delete(f"/api/registrations/{registration['id']}"), f"delete {registration['id']}")
    for account in demo("accounts", "account_name"):
        must(client.delete(f"/api/accounts/{account['id']}"), f"delete {account['id']}")
    print(f"\n  Removed {len(leads)} lead(s), {len(registrations)} registration(s) and their accounts.")


if __name__ == "__main__":
    if "--seed" in sys.argv:
        seed()
    elif "--remove" in sys.argv:
        remove()
    else:
        print(__doc__)
