# ARK-RBAC

Access control for ARK CRM — proposal for the Heads · 29 Sep 2026 · **Status: open, awaiting the Heads' review**

Live, editable copy: https://claude.ai/code/artifact/a4154aae-603f-4e58-975b-037c75d9776b
Once the Heads have answered, update this file to match.

## Summary

ARK CRM should decide access from three things per person: a **Profile** (what they can do), a place in the **reporting tree** (whose records they see) and **Responsibilities** (their job on a deal). Today one Roles list mixes all three, and the app only checks "has any role", so a Viewer can edit and delete.

- The Admin sets all of this in Setup, with no code and no release.
- On release day nobody gains or loses access; the Admin then moves people onto the new profiles one by one.
- Region plays no part in access. Visibility follows who reports to whom.
- Sales targets stay paused until this is built; they become its first user.

The Heads are asked to confirm the open questions at the end.

## The problem today

The ten values in today's Roles list describe three different things.

| Today's role | What it really is | What it becomes |
| --- | --- | --- |
| BD Owner, Sales Owner, Presales Owner, Product Owner, Delivery Owner | A job on a deal | Responsibility |
| Commercial Reviewer, Approver | A duty in a process | Responsibility |
| Admin, Viewer, Developer | A level of access | Profile |

What the app checks now:

- Anyone with any role can do everything with business records, including a Viewer.
- Three one-off rules sit in the code: Setup is Developer-only, reading feedback is Developer-only, and targets are Admin or Developer.
- Every new feature would add another one-off rule. This proposal replaces them with one.

## The model: three things per person

Every user gets exactly one profile, one place in the reporting tree, and any number of responsibilities.

| | Answers | Per user | Example |
| --- | --- | --- | --- |
| **Profile** | What can I do? | Exactly one; many people share it | "Sales Rep": create and edit Leads, no delete, sees own target only |
| **Role** (reporting tree) | Whose records can I see? | One place in the tree | Reports to the Sales Head |
| **Responsibilities** | What is my job on a deal? | Any number | BD Owner, Presales Owner |

On a user's page in Setup this reads:

| Field | Rep A |
| --- | --- |
| Profile | Sales Rep |
| Reports to | Sales Head |
| Responsibilities | BD Owner, Sales Owner |

- **A profile is a keycard type.** Everyone on "Sales Rep" opens the same doors.
- **The reporting tree decides whose records flow up to you.** It gives no buttons.
- **Responsibilities grant no access.** They say who can be picked as BD Owner, Sales Owner and so on, and later who gate approvals go to.
- **Developers define the actions; Admins combine them.** An Admin can tick or untick any action on a profile, but cannot invent a new one, because each needs server code behind it.
- **The server enforces every rule.** Hiding a button is never the protection.

On screen we call the tree **"Reports to"**, and today's Roles list becomes **Responsibilities**, so the word "role" never means two things.

## Worked example: two Sales Heads

Two Sales Heads get the **same profile** and sit in **separate branches** of the tree.

```
CEO  (Administrator, sees everything)
 ├── Sales Head 1  (Sales Manager)   ┐
 │     ├── Rep A   (Sales Rep)       │ Sales Head 1 sees these records
 │     └── Rep B   (Sales Rep)       ┘
 ├── Sales Head 2  (Sales Manager)   ┐
 │     ├── Rep C   (Sales Rep)       │ Sales Head 2 sees these records
 │     └── Rep D   (Sales Rep)       ┘
 └── Presales Lead (Presales)
```

- **Same profile, same powers.** Both can export and draft targets for their team; neither can delete. Ticking an action on Sales Manager reaches both at once.
- **Separate branches, separate data.** Each head sees their own records and their reps' records, never the other team's.
- **The CEO sits above both**, so sees every record.
- **A person who runs both teams** sits above the two heads, with no change to their profile.

## What counts as "my record"

**Recommendation: a record is yours if you are named in any of its owner fields.** On Leads, Opportunities and Deals those are BD Owner, Sales Owner and Presales Owner; on Accounts, Account Owner; on Contacts, Engagement Owner. Your managers see it too, through the reporting tree.

Example: the Lead "Dubai Smart Parking" has BD Owner **Rep A**, Sales Owner **Rep B** and Presales Owner **Presales Lead**. **Rep C** entered it after a trade show and handed it over.

| Who | A: BD Owner only | **B: any owner field** | C: B plus the creator |
| --- | --- | --- | --- |
| Rep A, BD Owner | Sees | Sees | Sees |
| Rep B, Sales Owner | Cannot | Sees | Sees |
| Presales Lead | Cannot, though running the demo | Sees | Sees |
| Rep C, created and handed over | Cannot | Cannot | Sees for ever |
| Sales Head, manager of the reps | Sees through Rep A | Sees through Rep A and Rep B | Sees |
| CEO | Sees | Sees | Sees |

- **A** locks out the people doing the work.
- **C** lets a handed-over deal stay visible for ever.
- **B** matches how a deal is staffed. When an owner changes, access moves with the name.

**Seeing is not getting credit.** Visibility uses all three owner fields. Credit stays with the **BD Owner only**: targets, the Won number and the dashboard's BD Owner filter work exactly as today. The Presales Lead can work on the deal, but its revenue counts toward Rep A's target.

**The dashboard follows visibility.** Each person's dashboard is built only from records they can see, so there is one rule, not two.

**Accounts, Contacts and Partners are visible to everyone.** Hiding an Account would break the End Client picker and push people into creating duplicates. Who may edit them is still set by the profile.

## Owners by stage today

The stage table names one accountable owner per stage, but the owner fields do not match it.

| Owner | Filled in at | Required? | Accountable for (stage table) |
| --- | --- | --- | --- |
| BD Owner | Lead, Stage 0 Connect | Yes, to create the Lead | Stages 0–2 |
| Sales Owner | Lead, Stage 3 Prescription | No, never asked for | Stages 3–7 |
| Presales Owner | Lead, Stage 3 Prescription | No, never asked for | No stage |
| Delivery Owner | No field anywhere | — | Stages 8–9 |

On Opportunities and Deals all three owners are shown live from the Lead; they are stored only on the Lead.

**Four gaps, and the fix proposed for each:**

1. **Sales Owner is accountable for Stages 3–7 but never required.** A pursuit can reach Close with nobody accountable. Fix: require Sales Owner to leave Stage 3. A setting in Setup.
2. **Presales comes in too late.** Presales runs the demo at Stage 1 and the POC at Stage 2, but the field appears at Stage 3, so they could not see the Lead while doing that work. Fix: move Presales Owner to Stage 1. A setting in Setup.
3. **Delivery Owner is accountable for Stages 8–9 but has no field.** Nobody can be named. Fix: add Delivery Owner on Deals at Stage 7. A setting in Setup.
4. **Owners cannot change after conversion.** The Lead becomes read-only and the Opportunity and Deal only display its owners. If a Sales Owner leaves mid-Deal, nobody can reassign it. Fix: a new "Change owner" action, audited. Needs building.

## RACI by stage

The **A** column comes from today's stage table; the R, C and I entries are a proposal for the Heads to confirm. **R** does the work, **A** answers for the stage (one per stage), **C** is consulted, **I** is kept informed.

| Stage | BD Owner | Sales Owner | Presales Owner | Delivery Owner | Commercial Reviewer / Approver |
| --- | --- | --- | --- | --- | --- |
| 0 Connect | **A/R** | — | — | — | — |
| 1 Demo Presentation | **A** | I | **R**, runs the demo | — | — |
| 2 POC / Pilot | **A** | I | **R**, runs the POC | C | G1 sign-off, with Gates |
| 3 Prescription | C, hands over | **A** | **R**, the solution | — | — |
| 4 RFP / RFI | I | **A/R** | **R**, technical response | C | G2 Commit to Bid |
| 5 Technical Evaluation | I | **A** | **R** | C | — |
| 6 Commercial Evaluation | I | **A/R** | C | C | **C**, pricing and margin |
| 7 Close | I | **A/R** | I | I, handover | G3 Commercial |
| 8 Project Success | I | C | — | **A/R** | — |
| 9 Expansion | C, new leads | C | — | **A/R** | — |

**Before and after someone is named:**

| | Before | After |
| --- | --- | --- |
| Sales Owner | Cannot see the pursuit; BD runs it alone | Sees the Lead, Opportunity and Deal; accountable for Stages 3–7 |
| Presales Owner | Cannot see it | Sees it and edits technical sections; cannot move the stage |
| BD Owner | Named from creation | Keeps visibility and keeps the credit to the end, though Sales is accountable from Stage 3 |
| Their managers | See it only through the BD Owner's manager | Each named owner's manager sees it too |

## How RACI relates to visibility

**RACI is the plan; owner fields, profiles and the reporting tree are how each person gets the access that plan needs.** The RACI letters never switch access on or off by themselves.

| RACI | Access needed | How they get it |
| --- | --- | --- |
| **A**, accountable | See, edit, move the stage | Named in an owner field; the profile gives edit and stage moves |
| **R**, does the work | See, edit their part | Named in an owner field; the profile decides what they may edit |
| **C**, consulted | See | Not named, so through their profile: "see all" for that module, read-only |
| **I**, informed | See | Managers through the reporting tree; others through a read-only profile |

**Access does not change with the stage.** Once named, a person keeps seeing the record until they are removed from the field, even at stages where RACI marks them only "I". How much they may edit is set by field access on their profile, not by the stage.

Walked through "Dubai Smart Parking" (Commercial Reviewer = Finance Head, Delivery Owner = Delivery Lead):

| Stage | Who is added | Why they can see it |
| --- | --- | --- |
| 0 Connect | Rep A, Sales Head, CEO | Rep A is named; the others are above Rep A |
| 1 Demo | Presales Lead | Named as Presales Owner at Stage 1 (gap 2 fixed) |
| 3 Prescription | Rep B | Named as Sales Owner; Rep A stays, still named |
| 6 Commercial | Finance Head, read-only | Not named; the Read Only profile sees all Opportunities and Deals |
| 7 Close | Delivery Lead | Named as Delivery Owner at Stage 7 (gap 3 fixed) |
| 8 Project Success | Nobody new | Nobody was removed, so everyone above still sees it |

**People consulted but never named** (Finance Head, Product Owner, a future Approver):

- **Now:** a read-only "see all" profile. There are only a few such people.
- **With Gates:** a gate approval sent to someone lets them open that record.
- **Not recommended:** a hand-kept followers list on each deal. People forget to add others.

## Action catalogue

These are the actions an Admin can tick on a profile. Each one already exists in the app; new ones are added by developers.

**Standard actions per module** (a dash means the app cannot do it, so it is not offered):

| Module | View | Create | Edit | Delete | Export | Import |
| --- | --- | --- | --- | --- | --- | --- |
| Leads | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Opportunities | ✓ | — made by conversion | ✓ | ✓ | ✓ | — |
| Deals | ✓ | — made by conversion | ✓ | ✓ | ✓ | — |
| Accounts and Partners | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Contacts | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Deal Registrations | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Conflicts | ✓ | ✓ | ✓ | ✓ | ✓ | — |

Partners use the Accounts actions, because a Partner is an Account.

**Special actions:**

| Area | Action | Covers |
| --- | --- | --- |
| Pipeline | Move stage and convert | Stage moves, skips, moving back, Lead to Opportunity to Deal, marking a pilot Paid |
| Pipeline | Override Progression / Probability % | The written justification is still required |
| Pipeline | Manage pursuit groups | Change the primary, remove a member |
| Pipeline | Erase a whole pursuit | Permanent; today anyone with a role can do it |
| Pipeline | Change owner (new) | Reassign owners on a converted pursuit |
| Partners | Withdraw a registration | |
| Partners | Resolve a conflict | |
| Targets | View targets | own / team / all |
| Targets | Edit draft targets | team / all |
| Targets | Lock and revise targets | |
| Dashboard | View the dashboard | Numbers follow what the person can see |
| Dashboard | Take a pipeline snapshot by hand | |
| Records | View the audit log | |
| Feedback | Read and manage the feedback queue | Everyone can still send feedback |
| Setup | Manage users | Add from the directory, deactivate, set profile, manager and responsibilities |
| Setup | Manage profiles, reporting tree and sharing | |
| Setup | Customise modules, fields, layouts and choices | Edits the draft only |
| Setup | Publish the register | Separate, because a publish is live at once |
| Setup | Developer tools | |

Move stage is separate from Edit on purpose: Presales can fill in technical sections without pushing the deal forward.

## Default profiles

Six profiles to start with. The Admin can change any tick later.

| | Administrator | Sales Manager | Sales Rep | Presales | Read Only | Developer |
| --- | --- | --- | --- | --- | --- | --- |
| **Sees** | all | own + team | own | own | all | all |
| Leads | full | view, create, edit, export, import | view, create, edit | view, edit | view | full |
| Opportunities, Deals | full | view, edit, export | view, edit | view, edit | view | full |
| Accounts, Contacts, Partners | full | view, create, edit, export | view, create, edit | view, create, edit | view | full |
| Registrations, Conflicts | full | view, create, edit | view, create | view | view | full |
| Delete, any module | yes | no | no | no | no | yes |
| Move stage and convert | yes | yes | yes | no | no | yes |
| Override % | yes | yes | yes | no | no | yes |
| Change owner | yes | yes | no | no | no | yes |
| Manage pursuit groups | yes | yes | no | no | no | yes |
| Erase a whole pursuit | yes | no | no | no | no | yes |
| Withdraw / resolve conflicts | yes | yes | no | no | no | yes |
| View targets | all | team | own | no | all | all |
| Edit draft targets | all | team | no | no | no | all |
| Lock and revise targets | yes | no | no | no | no | yes |
| Dashboard | yes | yes | yes | yes | yes | yes |
| Snapshot by hand, audit log | yes | no | no | no | no | yes |
| Feedback queue | no | no | no | no | no | yes |
| Setup: users, profiles, customise, publish | yes | no | no | no | no | yes |
| Developer tools | no | no | no | no | no | yes |

**Why:**

- **Erase moves to Admin only.** It permanently deletes a whole pursuit. Today anyone with a role can do it, the biggest risk in the app now.
- **Nobody below Admin deletes.** Closed Lost and Deactivate already cover "no longer wanted", and they keep the history.
- **Reps may override %.** The written justification is required and audited anyway; otherwise every judgement call waits on a manager.
- **Only an Admin locks targets.** A lock is a commitment; managers draft for their team but do not sign it off.
- **The feedback queue stays with Developers.** It is feedback about the product, for the people who build it.
- **Read Only suits Finance and anyone consulted but not named** on deals (see RACI).

## Exceptions: giving one extra action

**Any single action can be added to or removed from a profile.** Example: to let Sales Managers delete, the Admin opens Setup, Profiles, Sales Manager and ticks Delete on the modules they choose, say Leads and Accounts but not Deals.

- Everyone on that profile gets it on their next click; nobody needs to sign out.
- The change is written to the audit trail.

**When only one person should get it:**

| Option | How | Recommended |
| --- | --- | --- |
| Clone the profile | Make "Sales Manager + Delete" and move that one person onto it | Yes, for V2: each person keeps one profile, so Check access stays easy to read |
| Permission set, as in Salesforce | Add single actions to single people on top of their profile | Later, only if clones start to multiply |

**Guardrails:**

- There is always at least one Administrator.
- An Admin cannot remove their own admin access.
- **Check access** in Setup shows exactly what a person can do and see, before anyone is moved.

## Release plan and build order

**On release day nobody gains or loses access.** Everyone who has any role today goes onto a seventh profile, "Standard (as today)", which grants exactly what they have now. Admins and Developers go onto their own profiles. The six profiles above start empty; the Admin moves people onto them one by one, checking each with Check access first.

Each step ships something usable:

1. **Profiles and one server checkpoint**, seeded so that nothing changes for anyone. Users notice nothing, which is the point.
2. **Setup screens**: Profiles, a profile and "Reports to" on each user, and Check access. Setup opens to Admins; Admins manage access themselves.
3. **Today's one-off rules move onto actions**: feedback, targets, erase, pursuit-group changes, snapshots. The Admin can grant or remove each.
4. **Visibility**: the reporting tree and sharing defaults, applied to lists, search and the dashboard. "Own, team, all" becomes real.
5. **Field access**: per profile, a field can be editable, read-only or hidden, on forms, lists, filters, exports and import files at once.
6. **Sales targets resume**: the targets grid and "My target", built on steps 3 and 4 with no special cases.

The owner-field fixes for gaps 1–3 are settings in Setup and can be made at any time once agreed. "Change owner" (gap 4) is built with step 3.

## Decided so far

| Decision | Detail |
| --- | --- |
| Profiles and reporting tree only | No region or territory access; visibility follows who reports to whom |
| One profile per person | Many people share a profile; two Sales Heads share one and sit in separate branches |
| Names on screen | The tree is called "Reports to"; today's Roles list becomes Responsibilities |
| Admins manage access | ARK CRM is in version 2, so Setup, profiles and users are managed by Admins |
| Server enforces everything | Hiding a button is never the protection |
| Actions come from developers | Admins tick and untick; they cannot invent an action |
| Nobody loses access on release | "Standard (as today)" profile on day one |
| Sales targets paused | The targets grid and "My target" wait until access control is complete |

## Open questions for the Heads

Tick each once agreed; note any change beside it.

**Visibility**

- [ ] A record is "mine" if I am named in any owner field (option B), and credit stays with the BD Owner only.
- [ ] Accounts, Contacts and Partners are visible to everyone; editing is set by profile.
- [ ] Each dashboard shows only the records that person can see.
- [ ] Access does not change with the stage: once named, a person keeps it until removed from the field.
- [ ] People consulted but not named on deals (Finance, Product) get the Read Only profile.

**Owners and RACI**

- [ ] Sales Owner becomes required to leave Stage 3.
- [ ] Presales Owner moves from Stage 3 to Stage 1.
- [ ] A Delivery Owner field is added on Deals at Stage 7.
- [ ] A "Change owner" action is built for converted pursuits.
- [ ] The R, C and I entries of the RACI table are right.
- [ ] Owner dropdowns list only people with that responsibility (Sales Owner picker shows Sales Owners only).

**Actions and profiles**

- [ ] The action catalogue is complete: nothing missing, nothing that should not exist.
- [ ] The six default profiles and their ticks, especially: erase is Admin only; nobody below Admin deletes; reps may override %; only an Admin locks targets.
- [ ] A one-off exception is handled by cloning a profile, not by per-person extras.
- [ ] Sales Reps see only their own target, or everyone's as a leaderboard.
- [ ] Reps see their draft target before it is locked, or only once locked.

**People**

- [ ] For each employee: their profile, who they report to, and their responsibilities. Needed before step 2 can be used.
