# -*- coding: utf-8 -*-
"""ARK CRM — field register workbook for the THREE-MODULE pipeline split.

Reads spec/fields.json + spec/extensions.json + spec/picklists.json + spec/criteria.json
+ spec/stages.json and writes one sheet per module, with Leads 0-3, the new
Opportunities module 4-6 and Deals 7-9.

Nothing here hand-edits a generated file. The split is expressed as data below
(SPLIT / READ_THROUGH / OWN / NEW_FIELDS) exactly as spec/module_split.json and
the new_fields array of extensions.json will express it in code.

    python build_split_workbook.py

Output: ARK_CRM_Field_Register_Split_v1.xlsx
"""
import json
import re
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec")
OUT = os.path.join(HERE, "ARK_CRM_Field_Register_Split_v1.xlsx")

HDR = "0D3B45"; GRP = "DCEEF0"; ALT = "F2F6F7"; BORD = "B8C7CE"
GAPBG = "F9EBD2"          # gap-fix rows, as in the earlier workbook
RTBG = "EEF3F6"           # read-through rows
MUT = "55686F"

thin = Side(style="thin", color=BORD)
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)


def load(name):
    with open(os.path.join(SPEC, name), encoding="utf-8") as fh:
        return json.load(fh)


def fix(s):
    """spec/fields.json carries some double-encoded UTF-8 (a EUR " for an em dash)."""
    if not isinstance(s, str):
        return s
    if "â€" in s or "Â§" in s:
        try:
            return s.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    return s


FIELDS = [{k: fix(v) for k, v in f.items()} for f in load("fields.json")]
EXT = load("extensions.json")
PICKS = load("picklists.json")
CRITERIA = [{k: fix(v) for k, v in c.items()} for c in load("criteria.json")]
STAGES = load("stages.json")

# --------------------------------------------------------------------------
# THE SPLIT  — mirrors spec/module_split.json
# --------------------------------------------------------------------------
RANGES = {"leads": (0, 3), "opportunities": (4, 6), "deals": (7, 9)}
PIPELINE = ["leads", "opportunities", "deals"]

# reassignment by capture stage, off the Leads sheet
REASSIGN = {4: "opportunities", 5: "opportunities", 6: "opportunities", 7: "deals"}

# sections that must appear on all three pipeline modules
SHARED_SECTIONS = ("CROSS-CUTTING", "SYSTEM")

# per-record state each module needs its own instance of
OWN = {
    "project_stage": "Each module stores its own stage. Leads 0-3, Opportunities 4-6, Deals 7-9.",
    "probability_pct": "Probability is a property of the live record, not of the parent.",
    "lead_status": "Open / On Hold / Closed Lost / Converted applies to each record separately.",
    "deal_stage": "The Deal's own stage field. NEEDS 7_CLOSE ADDED - the picklist stops at 8. "
                  "Stage options are derived from the module_split range instead of the picklist.",
}

# identity read through the parent chain, rendered read-only, NEVER copied
#
# Country / Theme / ROB-gap pass: sub_segment removed (deleted from the
# register, its picklist deactivated - see spec/picklists.json); segment
# stays; theme, country, lighthouse_project and gorilla_flag added. Mirrors
# spec/module_split.json read_through.fields exactly - keep both in step.
READ_THROUGH = [
    "opportunity_name", "end_client", "customer_partner_si", "pre_bid_alliance_partner",
    "primary_contact", "partner_deal_registration", "segment", "theme",
    "sap_solution_suite", "suite_demonstrated", "currency", "total_project_value",
    "probable_award_date", "deal_source", "opportunity_type", "alliance_structure",
    "bd_owner", "sales_owner", "presales_owner", "consultant_specifier",
    "region", "lighthouse_project", "gorilla_flag",
]

# the ONLY things a conversion copies, each with its reason
COPIED = {
    "opportunities": {
        "fx_rate_at_entry": "Frozen at entry - the rate the pursuit was valued at.",
    },
    "deals": {
        "fx_rate_at_entry": "Frozen at entry - carried through unchanged.",
        "contract_value": "Copied from Opportunity.final_negotiated_value: the agreed number at close.",
        "arr_annual_recurring": "Commercial terms as signed.",
        "one_time_revenue": "Commercial terms as signed.",
        "3rd_party_one_time": "Commercial terms as signed.",
        "3rd_party_recurring_per_year": "Commercial terms as signed.",
        "contract_years": "Commercial terms as signed.",
    },
}

GAPFIX = "Gap fix - 14-stage review"

# --------------------------------------------------------------------------
# NEW FIELDS  — mirrors the new_fields array of extensions.json
# --------------------------------------------------------------------------
def nf(**kw):
    row = dict(module=None, section=None, api_name=None, label=None, type="text",
               max_length=None, picklist=None, lookup_target=None, lookup_filter=None,
               values_note=None, capture_stage=None, capture_any_stage=False,
               mandatory_from=None, blocks_transition=None, requirement="Optional",
               origin=GAPFIX, source_ref="14-stage review", description="", use_case="",
               required_on_skip=None, visibility_condition=None, condition=None,
               computed_formula=None, structural=False)
    row.update(kw)
    return row


NEW_FIELDS = []
for m in PIPELINE:
    NEW_FIELDS.append(nf(
        module=m, section="HEADER", api_name="progression_pct", label="Progression %",
        type="computed", requirement="Computed", capture_stage=None, capture_any_stage=True,
        computed_formula="position of the current stage in the 0-9 list / (count - 1)",
        values_note="0 - 11 - 22 - 33 - 44 - 56 - 67 - 78 - 89 - 100",
        description="How far through the whole 0-9 pursuit this record sits, as a percentage of stage position.",
        use_case="Shown BESIDE Probability, never instead of it. Probability is a commercial judgement inside a band; "
                 "Progression is a positional fact. At Stage 7 they read 78% and 90-100% and that difference is the point. "
                 "Linear-by-position is this build's choice - the register states no progression curve."))

NEW_FIELDS += [
    nf(module="opportunities", section="STAGE 4 - RFP / RFI", api_name="nomination_bid",
       label="Nomination Bid", type="checkbox", capture_stage=4, requirement="Optional",
       description="The client named Astrikos in the tender rather than running an open field.",
       use_case="A nomination materially raises win probability. THE UPLIFT IS NOT IN stages.json - "
                "until it is, the box records the fact and probability is untouched. Logged to Spec Health."),
    nf(module="opportunities", section="STAGE 4 - RFP / RFI", api_name="incumbent_only",
       label="Incumbent Only", type="checkbox", capture_stage=4, requirement="Optional",
       description="Astrikos is the sitting incumbent and the tender is effectively defensive.",
       use_case="Same as Nomination Bid. The playbook records incumbent advantage as a RANGE, not a number, "
                "so no value is applied here. No number is invented."),
    nf(module="opportunities", section="STAGE 6 - COMMERCIAL EVALUATION", api_name="sow_agreed_date",
       label="SoW Agreed Date", type="date", capture_stage=6, requirement="Mandatory",
       description="Date the client and Astrikos agreed the final scope of work.",
       use_case="The scope baseline the Deal is delivered against. Without it a Stage 8 variation cannot be shown to be a variation."),
    nf(module="opportunities", section="STAGE 6 - COMMERCIAL EVALUATION", api_name="bidder_declared_date",
       label="Bidder Declared Date", type="date", capture_stage=6, requirement="Mandatory",
       description="Date the client formally declared the winning bidder.",
       use_case="Separates the commercial decision from the paperwork. Award Type and Contract Signed Date can lag it by weeks; "
                "the gap between the two is the contracting delay KPI."),
    nf(module="opportunities", section="STAGE 4 - RFP / RFI", api_name="parent_lead",
       label="Parent Lead", type="lookup", lookup_target="lead", capture_stage=4,
       requirement="System", structural=True,
       description="The Lead this Opportunity was converted from. Read-only, set by the conversion.",
       use_case="The spine of carry-forward-by-reference. Every identity field on this record is READ THROUGH this link "
                "rather than copied, so the same value can never drift in two places."),
    nf(module="deals", section="ON CONVERSION", api_name="parent_opportunity",
       label="Parent Opportunity", type="lookup", lookup_target="opportunity", capture_stage=7,
       requirement="System", structural=True,
       description="The Opportunity this Deal was converted from. Read-only, set by the conversion.",
       use_case="Second link in the chain. deals.parent_lead is resolved THROUGH this rather than stored twice."),
]

# --------------------------------------------------------------------------
# Country / Theme / ROB-gap pass — value confidence and the header-strip fields
# --------------------------------------------------------------------------
NEW_FIELDS.append(nf(
    module="opportunities", section="STAGE 4 - RFP / RFI", api_name="value_confidence",
    label="Value Confidence", type="picklist", picklist="value_confidence", capture_stage=4,
    requirement="Optional",
    description="How firm the value on this Opportunity is right now - a budgetary estimate or a firm number.",
    use_case="Scoped to Opportunities Stage 4 only, DELIBERATELY - the ROB sheet discriminates Budgetary/Firm at "
             "every stage it covers, including Lead-stage rows, but Lead-stage value confidence is not captured "
             "anywhere in this build. Logged to Spec Health."))

# __header - the key-facts strip above the tabs, editable at any time, not
# tied to a stage. Same shape as the HEADER/progression_pct rows above but a
# DIFFERENT section, kept apart so the two groups render separately in both
# the workbook and the app: progression_pct is computed and read-only,
# these four are current state a person edits directly.
for m in PIPELINE:
    NEW_FIELDS += [
        nf(module=m, section="__header", api_name="overall_rag", label="Overall RAG",
           type="picklist", picklist="overall_rag", capture_any_stage=True, requirement="Optional",
           description="Current red/amber/green health of this record, judged at any time.",
           use_case="Cross-cutting current state, edited from the key-facts strip above the tabs rather than "
                    "through a collapsible section. Carry = Own instance on every module that has it."),
        nf(module=m, section="__header", api_name="next_milestone", label="Next Milestone",
           type="text", max_length=200, capture_any_stage=True, requirement="Optional",
           description="One line naming whatever happens next on this pursuit.",
           use_case="Cross-cutting current state - see Overall RAG for the shared rationale."),
        nf(module=m, section="__header", api_name="next_milestone_date", label="Next Milestone Date",
           type="date", capture_any_stage=True, requirement="Optional",
           description="When the next milestone above is due.",
           use_case="Cross-cutting current state - see Overall RAG for the shared rationale."),
    ]

NEW_FIELDS += [
    nf(module="opportunities", section="__header", api_name="is_low_hanging", label="Low Hanging",
       type="checkbox", capture_any_stage=True, requirement="Optional",
       description="Ticked when this Opportunity is judged one of the 5 easiest active pursuits to close.",
       use_case="Capped at 5 across all Opportunities, enforced server-side. Picking it asks the user to choose "
                "its rank from whichever of 1-5 are still open - see low_hanging_rank. Mutually exclusive with is_top_10."),
    nf(module="opportunities", section="__header", api_name="low_hanging_rank", label="Low Hanging Rank",
       type="number", capture_any_stage=True, requirement="Optional",
       description="This Opportunity's position, 1-5, among the current Low Hanging picks.",
       use_case="Chosen by the user from the ranks still open when is_low_hanging is ticked, cleared when it is "
                "unticked. Rendered as one rank-picker control together with the checkbox, never its own input."),
    nf(module="opportunities", section="__header", api_name="is_top_10", label="Top 10",
       type="checkbox", capture_any_stage=True, requirement="Optional",
       description="Ticked when this Opportunity is judged one of the 10 highest-priority pursuits in the pipeline.",
       use_case="Capped at 10 across all Opportunities, enforced server-side. Picking it asks the user to choose "
                "its rank from whichever of 1-10 are still open - see top_10_rank. Mutually exclusive with is_low_hanging."),
    nf(module="opportunities", section="__header", api_name="top_10_rank", label="Top 10 Rank",
       type="number", capture_any_stage=True, requirement="Optional",
       description="This Opportunity's position, 1-10, among the current Top 10 picks.",
       use_case="Chosen by the user from the ranks still open when is_top_10 is ticked, cleared when it is "
                "unticked. Rendered as one rank-picker control together with the checkbox, never its own input."),
]

# These repeat per module and are each module's OWN COPY of current state,
# not plumbing and not a register field carried through a parent - flagged
# "Own instance" rather than the NEW_FIELDS loop's default "Own" below.
HEADER_STRIP_OWN_INSTANCE = {
    "overall_rag": "Current RAG status is a judgement about the live record, not inherited from a parent.",
    "next_milestone": "What happens next is a property of the live record, not inherited from a parent.",
    "next_milestone_date": "Same as Next Milestone - each module's own copy.",
    "is_low_hanging": "Opportunities' own pick - there is nothing to inherit, this field exists only there.",
    "low_hanging_rank": "Opportunities' own ranking - there is nothing to inherit, this field exists only there.",
    "is_top_10": "Opportunities' own pick - there is nothing to inherit, this field exists only there.",
    "top_10_rank": "Opportunities' own ranking - there is nothing to inherit, this field exists only there.",
}

# --------------------------------------------------------------------------
# criteria index — which criterion each field serves, and where it evaluates
# --------------------------------------------------------------------------
API_NAMES = {f["api_name"] for f in FIELDS} | {f["api_name"] for f in NEW_FIELDS}
TOKEN = re.compile(r"[a-z0-9][a-z0-9_—\-]*")


def fields_in(source):
    if not source:
        return []
    return [t for t in TOKEN.findall(source.lower()) if t in API_NAMES]


def stage_owner(stage):
    for m, (lo, hi) in RANGES.items():
        if lo <= stage <= hi:
            return m
    return "leads"


CRIT_BY_FIELD = {}
for c in CRITERIA:
    for a in fields_in(c.get("source")):
        CRIT_BY_FIELD.setdefault(a, []).append(c["code"])

# --------------------------------------------------------------------------
# place every field
# --------------------------------------------------------------------------
def target_module(f):
    if f["module"] != "leads":
        return [f["module"]]
    sec = (f["section"] or "").upper()
    if sec.startswith(SHARED_SECTIONS):
        return list(PIPELINE)
    if f["api_name"] in OWN:
        return list(PIPELINE)
    st = f["capture_stage"]
    if st in REASSIGN:
        return [REASSIGN[st]]
    return ["leads"]


LABELS = {f["api_name"]: f["label"] for f in FIELDS}
BY_MODULE = {m: [] for m in ["partners", "accounts", "contacts"] + PIPELINE}

for f in FIELDS:
    if f["module"] not in ("partners", "accounts", "contacts", "leads", "deals"):
        continue
    for m in target_module(f):
        row = dict(f)
        row["_home"] = m
        row["_moved"] = ("leads" if f["module"] == "leads" and m != "leads" else "")
        row["_carry"] = "Own"
        if m in ("opportunities", "deals") and f["api_name"] in OWN:
            # Deals already declares deal_stage - it must not also carry project_stage.
            if f["api_name"] == "project_stage" and m == "deals":
                continue
            row["_carry"] = "Own instance"
            row["_carrynote"] = OWN[f["api_name"]]
            word = {"opportunities": "Opportunity", "deals": "Deal"}[m]
            row["label"] = fix(f["label"]).replace("Lead", word)
        BY_MODULE[m].append(row)

for f in NEW_FIELDS:
    row = dict(f)
    row["_home"] = f["module"]
    row["_moved"] = ""
    if f["api_name"] in HEADER_STRIP_OWN_INSTANCE:
        row["_carry"] = "Own instance"
        row["_carrynote"] = HEADER_STRIP_OWN_INSTANCE[f["api_name"]]
    else:
        row["_carry"] = "Own"
    BY_MODULE[f["module"]].append(row)

# read-through rows for the two downstream modules
for m in ("opportunities", "deals"):
    have = {r["api_name"] for r in BY_MODULE[m]}
    parent = "Lead" if m == "opportunities" else "Opportunity"
    for a in READ_THROUGH:
        if a in have or a not in LABELS:
            continue
        src = next((x for x in FIELDS if x["api_name"] == a and x["module"] == "leads"), None)
        if not src:
            continue
        row = dict(src)
        row.update(_home=m, _moved="", _carry="Read-through", requirement="Read-only",
                   _carrynote="Read through the parent %s and rendered read-only. NOT copied." % parent)
        BY_MODULE[m].append(row)

# --------------------------------------------------------------------------
# sheet writing
# --------------------------------------------------------------------------
HEADERS = ["#", "Field Name", "API Name", "Type", "Values / Options",
           "Description - what this field is",
           "Use Case - why it exists / the rule it serves",
           "Capture at Stage", "Mandatory From", "Blocks Transition", "Requirement",
           "Serves Criteria", "Carry", "Moved From", "Origin", "Source Ref",
           "KEEP?", "Decision Notes"]
WIDTHS = [5, 30, 30, 20, 40, 54, 58, 13, 13, 15, 14, 15, 16, 12, 24, 14, 9, 30]


def opts(f):
    bits = []
    p = f.get("picklist")
    if p:
        vals = PICKS.get(p) or []
        labels = " . ".join(fix(v["label"]) for v in vals if v.get("active"))
        bits.append("%s - %s" % (p, labels) if labels else "%s - NO VALUE SET IN THE REGISTER" % p)
    if f.get("lookup_target"):
        bits.append("-> %s" % f["lookup_target"])
    if f.get("lookup_filter"):
        bits.append(fix(f["lookup_filter"]))
    if f.get("computed_formula"):
        bits.append(fix(f["computed_formula"]))
    if f.get("max_length"):
        bits.append("max %s" % f["max_length"])
    if f.get("values_note"):
        bits.append(fix(f["values_note"]))
    if f.get("visibility_condition"):
        bits.append("shown when %s" % fix(f["visibility_condition"]))
    return "\n".join(b for b in bits if b and b != "—")


def blocks(f, module):
    m = f.get("mandatory_from")
    if m in (None, "", "—"):
        return "—"
    try:
        n = int(str(m).strip())
    except ValueError:
        return str(m)
    lo, hi = RANGES.get(module, (0, 9))
    if n == 3 and module == "leads":
        return "3 -> Opportunity"
    if n == 6 and module == "opportunities":
        return "6 -> Deal"
    if n == 9:
        return "9 -> New Lead"
    if n >= hi:
        return "%d -> %d" % (n, n + 1)
    return "%d -> %d" % (n, n + 1)


def section_key(row, module):
    sec = (row.get("section") or "").upper()
    if sec.startswith("__HEADER"):
        return (-2, "KEY FACTS STRIP - above the tabs, editable at any time, not tied to a stage")
    if sec.startswith("HEADER"):
        return (-1, "HEADER - shown on every screen of the record")
    if sec.startswith("CROSS-CUTTING"):
        return (98, "CROSS-CUTTING - applies at every stage")
    if sec.startswith("SYSTEM"):
        return (99, "SYSTEM")
    if row.get("_carry") == "Own instance" and module != "leads":
        return (0, "RECORD STATE - each module keeps its own instance")
    if row.get("_carry") == "Read-through":
        return (97, "READ THROUGH THE PARENT - displayed read-only, never stored here")
    st = row.get("capture_stage")
    if st is None:
        return (96, fix(row.get("section") or "OTHER"))
    name = next((s["name"] for s in STAGES if s["stage"] == st), "")
    return (st, "STAGE %d - %s" % (st, name.upper()))


def write_module(wb, module, title, note):
    ws = wb.create_sheet(title)
    rows = BY_MODULE[module]
    groups = {}
    for r in rows:
        k = section_key(r, module)
        groups.setdefault(k, []).append(r)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(HEADERS))
    c = ws.cell(row=1, column=1, value=note)
    c.font = Font(bold=True, color="FFFFFF", size=11)
    c.fill = PatternFill("solid", fgColor=HDR)
    c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32

    for i, h in enumerate(HEADERS, 1):
        cell = ws.cell(row=2, column=i, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=HDR)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = BOX
        ws.column_dimensions[get_column_letter(i)].width = WIDTHS[i - 1]
    ws.freeze_panes = "C3"

    r = 3
    n = 0
    for key in sorted(groups):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(HEADERS))
        g = ws.cell(row=r, column=1, value=key[1])
        g.font = Font(bold=True, color=HDR)
        g.fill = PatternFill("solid", fgColor=GRP)
        g.border = BOX
        r += 1
        for f in groups[key]:
            n += 1
            crit = " ".join(CRIT_BY_FIELD.get(f["api_name"], [])) or "—"
            carry = f.get("_carry", "Own")
            if f["api_name"] in COPIED.get(module, {}):
                carry = "Copied at conversion"
            notes = f.get("_carrynote", "") or COPIED.get(module, {}).get(f["api_name"], "")
            vals = [n, fix(f["label"]), f["api_name"], f["type"], opts(f),
                    fix(f.get("description") or ""), fix(f.get("use_case") or ""),
                    "any" if f.get("capture_any_stage") else
                    ("—" if f.get("capture_stage") is None else f["capture_stage"]),
                    f.get("mandatory_from") or "—", blocks(f, module),
                    f.get("requirement") or "", crit, carry, f.get("_moved") or "—",
                    fix(f.get("origin") or ""), fix(f.get("source_ref") or ""), "", notes]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=r, column=i, value=v)
                cell.border = BOX
                cell.alignment = Alignment(wrap_text=i in (5, 6, 7, 18), vertical="top")
                if i in (1, 8, 9, 10, 17):
                    cell.alignment = Alignment(horizontal="center", vertical="top")
            bg = None
            if str(f.get("origin", "")).startswith("Gap fix"):
                bg = GAPBG
            elif f.get("_carry") == "Read-through":
                bg = RTBG
            elif n % 2 == 0:
                bg = ALT
            if bg:
                for i in range(1, len(HEADERS) + 1):
                    ws.cell(row=r, column=i).fill = PatternFill("solid", fgColor=bg)
            r += 1
    return n


NOTES = {
    "partners": "PARTNERS - unchanged by the split.",
    "accounts": "ACCOUNTS - unchanged by the split.",
    "contacts": "CONTACTS - unchanged by the split.",
    "leads": "LEADS - Stages 0 Connect, 1 Demo, 2 POC/Pilot, 3 Prescription. "
             "Stage 4-6 fields moved to Opportunities and Stage 7 fields moved to Deals. "
             "A Lead converts on leaving Stage 3 and becomes read-only history.",
    "opportunities": "OPPORTUNITIES - NEW MODULE. Stages 4 RFP/RFI, 5 Technical Eval, 6 Commercial Eval. "
                     "Holds parent_lead. Identity fields are READ THROUGH the Lead and shown read-only - "
                     "only fx_rate_at_entry is copied. Converts to a Deal on leaving Stage 6.",
    "deals": "DEALS - Stages 7 Close, 8 Project Success, 9 Expansion. Opens at Stage 7 with Order Booked FALSE - "
             "booking is the 7 -> 8 advance. Holds parent_opportunity; parent_lead resolves through it.",
}

wb = Workbook()
wb.remove(wb.active)

# ---- Read Me -------------------------------------------------------------
ws = wb.create_sheet("Read Me")
ws.column_dimensions["A"].width = 30
ws.column_dimensions["B"].width = 118
readme = [
    ("ARK CRM - Field Register, three-module pipeline", ""),
    ("", ""),
    ("What this is", "Every field the prototype renders today, re-placed for the pipeline split agreed at the 14-stage "
                     "review. Generated from spec/fields.json + extensions.json + picklists.json + criteria.json + stages.json. "
                     "Edit build_split_workbook.py and re-run - never hand-edit this workbook."),
    ("The split", "Leads 0-3 . Opportunities 4-6 (new) . Deals 7-9. Declared in spec/module_split.json; fields.json is untouched."),
    ("Carry column", "Own = stored on this record. Own instance = each module keeps its own copy of this state field. "
                     "Read-through = resolved from the parent and rendered read-only, NEVER copied. "
                     "Copied at conversion = one of the few values that genuinely freezes, with its reason in Decision Notes."),
    ("Serves Criteria", "Which entry (E) or exit (X) criterion reads this field, from spec/criteria.json. "
                        "Placement follows these: a field is put on the module that owns the stage whose criteria read it. "
                        "The Criteria Check sheet lists every case where a criterion has to look across a module boundary."),
    ("Row shading", "Amber = gap fix, not in the register. Pale blue = read through the parent."),
    ("Not settled", "Nomination Bid and Incumbent Only uplifts are absent from stages.json - the boxes record the fact and "
                    "probability is untouched. Progression % is linear by stage position, this build's choice, not the register's. "
                    "deals__deal_stage still has no 7_CLOSE - stage options are derived from module_split ranges instead."),
    ("v3 changes - Country / Theme / ROB-gap pass",
     "1) Country: leads.country is NEW (read through to Opportunities/Deals, picklist India/MEA/APAC/Americas) and "
     "REPLACES the Region field from the pass before it. It is NOT accounts.country, which is unchanged and still "
     "holds an actual country (UAE/KSA/Qatar/Oman/Kuwait/Bahrain/Other MEA/Outside MEA). "
     "2) sub_segment DELETED from Leads, Opportunities, Deals and Accounts; its picklist deactivated, not removed. "
     "leads.theme is NEW in its place (read through), normalised from the ROB sheet's 9 raw values to 7 distinct. "
     "Segment stays - it overlaps Theme, flagged on Spec Health rather than resolved. "
     "3) Lighthouse Project and Gorilla Flag are NEW Stage 0 identity checkboxes on Leads, read through to "
     "Opportunities and Deals like Country and Theme. "
     "4) Value Confidence is NEW on Opportunities Stage 4 only (Budgetary/Firm) - a deliberate gap, since the ROB "
     "data shows this discriminating at every stage including Lead-stage rows; not captured there. Flagged on Spec Health. "
     "5) Overall RAG, Next Milestone and Next Milestone Date are NEW on Leads, Opportunities and Deals; Pipeline "
     "Rank is NEW on Opportunities only (nullable). All four are __header section - current state with no capture "
     "stage, edited from a key-facts strip above the tabs rather than a collapsible section. See the KEY FACTS "
     "STRIP group on each sheet and the New & Moved sheet for every row this pass touched."),
    ("v4 changes - Region unification",
     "leads.country renamed to leads.region and accounts.country renamed to accounts.region, both now on the SAME "
     "India/MEA/APAC/Americas picklist (\"region\") - the v3 pass had deliberately kept these apart as two different "
     "grains (a business region vs. an actual country) with non-overlapping picklists; this pass was told to unify "
     "them instead. accounts__country's 8 original options (UAE/KSA/Qatar/Oman/Kuwait/Bahrain/Other MEA/Outside MEA) "
     "are deactivated, not deleted. Seed accounts remapped from actual country to MEA (all 15 seeded accounts are "
     "Gulf-based). The two fields are still NOT synced to each other - only the picklist was unified, not the "
     "values. leads.region still shows as a READ-THROUGH row on the New & Moved sheet, same as leads.country did; "
     "accounts.region is a plain rename of an existing field and carries no row of its own there."),
]
for i, (a, b) in enumerate(readme, 1):
    ws.cell(row=i, column=1, value=a).font = Font(bold=True, color=HDR, size=13 if i == 1 else 11)
    c = ws.cell(row=i, column=2, value=b)
    c.alignment = Alignment(wrap_text=True, vertical="top")
    if b:
        ws.row_dimensions[i].height = 46

counts = {}
for m, t in [("partners", "Partners"), ("accounts", "Accounts"), ("contacts", "Contacts"),
             ("leads", "Leads"), ("opportunities", "Opportunities"), ("deals", "Deals")]:
    counts[t] = write_module(wb, m, t, NOTES[m])

# ---- Criteria Check ------------------------------------------------------
ws = wb.create_sheet("Criteria Check")
hdrs = ["Stage", "Module that owns the stage", "Type", "Code", "Criterion", "Source expression",
        "Fields it reads", "Where those fields live", "Cross-boundary?"]
for i, h in enumerate(hdrs, 1):
    c = ws.cell(row=1, column=i, value=h)
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor=HDR)
    c.alignment = Alignment(wrap_text=True); c.border = BOX
for i, w in enumerate([7, 22, 8, 9, 52, 40, 34, 30, 44], 1):
    ws.column_dimensions[get_column_letter(i)].width = w

HOME = {}
for m in PIPELINE:
    for row in BY_MODULE[m]:
        if row.get("_carry") != "Read-through":
            HOME.setdefault(row["api_name"], set()).add(m)

r = 2
for c in sorted(CRITERIA, key=lambda x: (x["stage"], x["type"], x["code"])):
    owner = stage_owner(c["stage"])
    fs = fields_in(c.get("source"))
    where = sorted({m for a in fs for m in HOME.get(a, {"?"})})
    cross = ""
    if fs and owner not in where:
        if where and where != ["?"]:
            cross = ("YES - split boundary. Evaluated on %s but read from %s. Resolve through the parent link; "
                     "the readiness panel must render it as read-through, not as a failure."
                     % (owner, ", ".join(where)))
        else:
            cross = ("Lives on another module (POC / Bid record), not on the pipeline sheets. "
                     "Unchanged by the split.")
    vals = [c["stage"], owner, c["type"], c["code"], c["text"], c.get("source") or "—",
            ", ".join(fs) or "—", ", ".join(where) or "—", cross or "no"]
    for i, v in enumerate(vals, 1):
        cell = ws.cell(row=r, column=i, value=v)
        cell.border = BOX
        cell.alignment = Alignment(wrap_text=i in (5, 6, 7, 9), vertical="top")
    if cross:
        for i in range(1, len(hdrs) + 1):
            ws.cell(row=r, column=i).fill = PatternFill("solid", fgColor=GAPBG)
    r += 1

# ---- New & Moved ---------------------------------------------------------
ws = wb.create_sheet("New & Moved")
hdrs = ["Change", "Field", "API Name", "From", "To", "Stage", "Note"]
for i, h in enumerate(hdrs, 1):
    c = ws.cell(row=1, column=i, value=h)
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor=HDR); c.border = BOX
for i, w in enumerate([14, 32, 32, 12, 16, 8, 96], 1):
    ws.column_dimensions[get_column_letter(i)].width = w
r = 2
for f in NEW_FIELDS:
    vals = ["NEW (structural)" if f.get("structural") else "NEW", f["label"], f["api_name"], "—",
            f["module"], f.get("capture_stage") if f.get("capture_stage") is not None else "header",
            f["use_case"]]
    for i, v in enumerate(vals, 1):
        cell = ws.cell(row=r, column=i, value=v); cell.border = BOX
        cell.alignment = Alignment(wrap_text=i == 7, vertical="top")
        cell.fill = PatternFill("solid", fgColor=GAPBG)
    r += 1
for m in ("opportunities", "deals"):
    for row in sorted(BY_MODULE[m], key=lambda x: (x.get("capture_stage") or 0, x["api_name"])):
        if row.get("_moved") == "leads":
            vals = ["MOVED", row["label"], row["api_name"], "leads", m, row.get("capture_stage"),
                    "Stage %s field. Follows the stage to the module that owns it." % row.get("capture_stage")]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=r, column=i, value=v); cell.border = BOX
                cell.alignment = Alignment(wrap_text=i == 7, vertical="top")
            r += 1
for m in ("opportunities", "deals"):
    for row in BY_MODULE[m]:
        if row.get("_carry") == "Read-through":
            vals = ["READ-THROUGH", row["label"], row["api_name"], "leads", m, row.get("capture_stage"),
                    row.get("_carrynote", "")]
            for i, v in enumerate(vals, 1):
                cell = ws.cell(row=r, column=i, value=v); cell.border = BOX
                cell.alignment = Alignment(wrap_text=i == 7, vertical="top")
                cell.fill = PatternFill("solid", fgColor=RTBG)
            r += 1

wb.save(OUT)
print("wrote", OUT)
for k, v in counts.items():
    print("  %-14s %3d rows" % (k, v))
