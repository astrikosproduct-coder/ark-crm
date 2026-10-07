"""
Release 1.1 — which POC/Pilot Deals were made without their commercials?

    python release_1_1_pilot_deals.py

READ-ONLY: it changes nothing. Run it on production BEFORE the release (it
works on V1's schema).

Until Release 1.1 a Lead became a POC/Pilot Deal whenever Pilot Commercial
Model held "Paid" — even a Paid left behind, hidden, after Agreed Next Step
moved off POC scoping, when the fields that ask for the fee and PO date were
hidden too (found 7 Oct 2026). Those Deals have no value, count in no total,
and nobody was told. Listed here:

  NO FEE       contract value empty — the Deal counts $0
  NO PO DATE   PO Received Date empty — never counted as Won
  NOT A POC    its Lead's Agreed Next Step isn't POC scoping

What to do with each is a person's call: fill in the Deal's value and PO
date, or erase the pursuit and reopen the Lead.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402

engine.echo = False


def main() -> int:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT d.deal_id, d.deal_name, d.contract_value, d.po_received_date,
                       l.lead_id, l.opportunity_name, l.agreed_next_step
                  FROM deals d
                  LEFT JOIN leads l ON l.lead_id = d.parent_lead
                 WHERE d.lead_status = 'POC_PILOT_DEAL'
                 ORDER BY d.deal_id
                """
            )
        ).mappings().all()

    flagged = []
    for r in rows:
        problems = []
        if r["contract_value"] is None:
            problems.append("NO FEE")
        if r["po_received_date"] is None:
            problems.append("NO PO DATE")
        if r["agreed_next_step"] != "POC_SCOPING":
            problems.append(f"NOT A POC (Agreed Next Step: {r['agreed_next_step'] or 'empty'})")
        if problems:
            flagged.append((r, problems))

    print(f"POC/Pilot Deals checked: {len(rows)}")
    print("=" * 74)
    if not flagged:
        print("\nEvery one has its fee, its PO date and a POC behind it.")
        return 0
    print(f"\n{len(flagged)} to look at:")
    for r, problems in flagged:
        print(f"\n  {r['deal_id']}  {r['deal_name']}")
        print(f"    from {r['lead_id']}  {r['opportunity_name']}")
        print(f"    {' · '.join(problems)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
