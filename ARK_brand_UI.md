# ARK Brand UI — Zoho CRM Visual Reference

## Purpose & Scope (read this first, agent)

This document is a **visual styling reference only**. It was reverse-engineered from 9 screenshots of Zoho CRM (Setup grid, module field-builder, Deals kanban, Leads record detail, Leads list view, Accounts filter panel, Home dashboard, Reports list).

The goal is to make ARK CRM's existing screens **look and feel like Zoho CRM's dark UI** — nothing more.

### Non-negotiable constraints

- **Do not** change any business logic, data models, API contracts, routing, permissions, or feature behavior.
- **Do not** rename, delete, or restructure existing components, files, or props — apply styling in place (CSS/theme layer, class names, design tokens) rather than rewriting components.
- **Do not** add new functional features (no new modules, no new workflows) even if a Zoho screen implies one ARK doesn't have yet. If a visual pattern (e.g. Kanban stage view) doesn't exist in ARK yet, flag it as an open question rather than building the underlying feature — the ask here is re-skinning what already exists.
- **Do** implement this as a design-token/theme layer (CSS variables, a Tailwind theme extension, a styled-components theme, or equivalent for ARK's actual stack) so it can be toggled/reverted cleanly.
- **Do** preserve all existing accessibility behavior (focus states, ARIA, keyboard nav) — restyle, don't strip.
- **Color source of truth**: the palette in §1.1 is now the **exact CSS custom properties extracted from Zoho's own night-mode stylesheet** (devtools-inspected, not estimated) — use these hex/rgb values as-is, don't re-guess them. Layout proportions, spacing, and component *structure* in §2–§3 were still reverse-engineered visually from the 9 reference screenshots and remain approximate — nudge those against the screenshots (in `Zoho CRM UI/` on the user's Desktop) during implementation.
- Before writing code: map each "Zoho pattern" below to the actual ARK component that plays that role, and list the mapping back to the user for confirmation if anything is ambiguous.

---

## 1. Design Tokens

### 1.1 Color Palette (dark theme) — exact values from Zoho's night-mode CSS

These are mapped 1:1 from Zoho's real `.zmNightMode` / `.zsNightMode` custom properties (devtools-extracted by the user), renamed into a semantic `--ark-*` layer. The original Zoho variable is noted in each comment for traceability — **do not alter the hex/rgb values**, only the variable names may be adapted to fit ARK's existing token conventions.

**Layering model — corrected.** Pure black (`#0C0C0C`) is a **sidebar-rail color**, confirmed by the variable name itself: `zs-primaryLHSBGColor` — LHS = Left-Hand Side, i.e. the sidebar. It is NOT the dominant background of the working area. The gray (`#222427`, `zs-primaryBGColor` — literally "primary background") is what actually fills most of the screen: table/list views, record detail pages, cards, popups. Only the sidebar (and a couple of overlay-specific contexts, like the global-search modal) are true black. If most of ARK's screen currently reads as black, that's the bug — swap the dominant fill to the gray tier and reserve black for the sidebar rail only.

```css
:root {
  /* ===== Backgrounds ===== */
  --ark-bg-page: #222427;              /* zs-primaryBGColor — THE dominant fill: main content area behind tables, record views, the header strip */
  --ark-bg-page-alt: #151415;          /* zs-dashboard-bg-color — Home/Dashboard specifically renders darker than other pages; don't use this outside Home */
  --ark-bg-sidebar: #0c0c0c;           /* zs-primaryLHSBGColor — true black, sidebar rail ONLY, not the main content */
  --ark-bg-sidebar-dark: #2f2f2f;      /* zs-primaryLHSBGDarkColor — sidebar sub-section / settings-app bg */
  --ark-bg-sidebar-compact: #3a3d46;   /* zssmaller--primaryLHSBGColor — collapsed/icon-only sidebar rail */
  --ark-bg-panel: #222427;             /* zs-primaryPopupBGColor / zs-profile-naviBackgroundColor — same gray tier as page bg; popups/dropdowns sit at this level, not above it */
  --ark-bg-panel-light: #35373e;       /* zs-primaryBGLightColor — slightly lifted panel variant */
  --ark-bg-panel-raised: #3a3d46;      /* zs-primaryAutoSuggBGColor — the next tier up: autosuggest, kanban cards, tour footer, table-row hover-adjacent surfaces */
  --ark-bg-input: #3a3d46;             /* reuse autosuggest bg for text inputs / search boxes */
  --ark-bg-hover: #2f2f2f;             /* zs-primaryHoverBGColor */
  --ark-bg-selected-hover: #222427;    /* zs-primarySelectedBGLightHoverColor */
  --ark-bg-selected-onlight: #e1eef5;  /* zs-primarySelectedBGLightColor — selected state on a light surface, rare in dark theme */
  --ark-bg-selected-solid: #000000;    /* zs-primarySelectedBGDarkColor */
  --ark-bg-loader: #3a3d45;            /* zs-primaryServicesBGLoaderColor — skeleton/loading placeholder */
  --ark-bg-loader-icon: #53555c;       /* zs-primaryServicesIconLoaderColor */
  --ark-bg-services-selected: #313131; /* zs-selectedServicesBGColor */
  --ark-bg-settings-app: #2f2f2f;      /* zs-bgcolor-gsSettingAppColor */

  /* ===== Borders ===== */
  --ark-border: #6d6d6d;               /* zs-borderColor — NOTE: a clearly visible mid-gray, not a subtle near-invisible line */

  /* ===== Brand / accent (confirmed blue, not purple) ===== */
  --ark-accent: #2c66dd;               /* zs-primaryButtonBGColor / zs-primarySelectedBGColor — primary filled buttons, selected states */
  --ark-accent-light: #6b94e7;         /* zs-primaryBorderColor / zs-primaryThemeIconColor / zs-DarkBGIconColor / zs-DarkBGTextColor / zs-primarySelectedTextColor — accent icon color, accent border, selected text tint on dark bg */
  --ark-link: #00a6ff;                 /* zs-primaryHyperLink — brighter cyan-blue, distinct from button blue; use for inline hyperlinks only */

  /* ===== Text ===== */
  --ark-text-primary: #f5f5f5;         /* zs-primaryTextColor */
  --ark-text-secondary: #c4c4c4;       /* zs-secondaryTextColor / zs-primaryIconColor */
  --ark-text-tertiary: #939393;        /* zs-resultRightTextColor */
  --ark-text-muted: #808080;           /* zs-lightTextColor */
  --ark-text-generic: #bababa;         /* zs-primaryColor — general-purpose secondary tone, close to muted */
  --ark-text-invert: #ececec;          /* zs-InvertTextColor */
  --ark-text-sidebar: #ffffff;         /* zs-primaryLHSTextColor / zs-primaryLHSLogoTextColor */
  --ark-text-on-accent: #ffffff;       /* text on filled accent buttons; also zs-servicesPanelTextColor */
  --ark-icon: #c4c4c4;                 /* zs-primaryIconColor */
  --ark-icon-light: #f2f2f2;           /* zsicon-LHSService / zs-tour-primary-IconColor / zsicon-ppColor(#EFEFEF) */

  /* ===== Search overlay (if ARK has a global/universal search modal) ===== */
  --ark-search-query-text: #777777;    /* zs-gsSearchQueryBoxColor */
  --ark-search-top-band-bg: #0c0c0c;   /* zs-bgcolor-gsSearchTopBandHolder */
  --ark-search-mini-top-band-bg: #222427; /* zs-bgcolor-gsSearchMiniTopBandHolder */
  --ark-search-bottom-bg: #222427;     /* zs-bgcolor-gsSearchBottomHolder */
  --ark-search-result-area-bg: #0c0c0c;/* zs-bgcolor-gsSearchResultMiddle */

  /* ===== Dashboard-specific ===== */
  --ark-dashboard-bg: #151415;                                              /* zs-dashboard-bg-color */
  --ark-dashboard-header-shadow: 0 2px 8px 0 rgba(255,255,255,0.16);        /* zs-dashboard-header-shadow */
  --ark-dashboard-thumb-header-shadow: 0 10px 12px -12px rgba(255,255,255,0.24) inset;  /* zs-dashboard-thumbail-header-shadow */
  --ark-dashboard-thumb-footer-shadow: 0 -10px 12px -12px rgba(255,255,255,0.24) inset; /* zs-dashboard-thumbail-footer-shadow */
  --ark-dashboard-info-desc: #cccccc; /* zs-dashboard-info-desc-color */

  /* ===== Onboarding / tour tooltips (if ARK has a product-tour component) ===== */
  --ark-tour-icon: #f2f2f2;
  --ark-tour-text: #ffffff;
  --ark-tour-bg: #4a4a4a;
  --ark-tour-tagline-text: #606060;
  --ark-tour-footer-bg: #3a3d46;
  --ark-tour-leg-bg: #3a3d46;

  /* ===== Semantic (not present in the extracted vars — kept as reasonable estimates, verify before relying on these) ===== */
  --ark-success: #35c26a;
  --ark-success-bg: #1c3327;
  --ark-warning: #e0a63b;
  --ark-danger: #e5484d;           /* required-field left border, destructive actions */
  --ark-info-teal: #16c2c2;        /* kanban active-stage accent, info badges */
  --ark-info-teal-bg: #12302f;
  --ark-avatar-accent: #a34fc9;    /* user avatar circle — NOT in the extracted token set; screenshots show a purple/magenta circle, but confirm the exact value via devtools before shipping */

  /* ===== Focus ===== */
  --ark-focus-ring: 0 0 0 2px rgba(44, 102, 221, 0.4); /* built from --ark-accent */
}
```

**Corrections vs. the original screenshot-based draft**:
1. The accent/brand color is **blue** (`#2c66dd` primary, `#6b94e7` light-accent), not the purple/indigo guessed from compressed screenshots. Anywhere in §2–§3 below that says "purple" or references the old `#5b5fe6`/`#a34fc9`-style indigo, treat `--ark-accent` (`#2c66dd`) as the correct value; only the avatar-circle color remains an open question (see the `--ark-avatar-accent` note above).
2. Borders are a clearly visible mid-gray (`#6d6d6d`), not the near-invisible dark-on-dark border originally assumed — use it at full or near-full opacity, don't fade it down to a hairline.
3. **(Round 2 fix, from direct visual comparison against a live ARK screenshot)** Black is a sidebar-only color, not the dominant page fill. The first pass of this doc set `--ark-bg-page` to near-black and told the agent to apply it broadly, which produces a screen that's mostly black — visually wrong. Zoho's actual visual weight is **mostly gray** (`#222427`) with black confined to the sidebar rail. If ARK currently looks like "majority black, minority gray," that's this bug; it should be closer to "majority gray, black sidebar strip on the left."

### 1.1a Optional: Chat / Messaging Widget Tokens

Only relevant if ARK has (or will have) an in-app chat/messaging panel. These came from a separate Zoho widget theme (`wms-*` = their messaging widget), distinct from the core CRM chrome above — treat as a supplementary palette for that one component, not the general theme:

```css
:root {
  --ark-chat-primary: rgb(32, 138, 237);        /* wms-primary-color — a third, brighter blue used only inside chat */
  --ark-chat-bg: rgb(39, 39, 39);               /* wms-chat-bg-color */
  --ark-chat-bg-secondary: rgb(39, 39, 39);     /* wms-secondary-chat-bg-color */
  --ark-chat-schedule-bg: rgb(42, 61, 67);      /* wms-schedulechat-bg-color */
  --ark-chat-bubble: rgba(49, 49, 49, 1);       /* wms-bubble-color */
  --ark-chat-bubble-secondary: rgb(49, 49, 49); /* wms-secondary-bubble-color */
  --ark-chat-bubble-other-user: rgb(31, 31, 31);/* wms-otheruser-bubble-color */
  --ark-chat-text: rgb(186, 186, 186);          /* wms-primary-text-color */
  --ark-chat-glow: rgb(250, 228, 163);          /* wms-chatwin-glow-color — notification/attention glow */
  --ark-chat-list-hover: rgb(46, 46, 46);       /* wms-listhoverbg-color */
  --ark-chat-border: rgb(72, 72, 72);           /* wms-border-color */
  --ark-chat-hover: rgb(53, 53, 53);            /* wms-hover-color */
  --ark-chat-heading: rgb(58, 58, 58);          /* wms-heading-color */
  --ark-chat-icon: rgb(126, 126, 126);          /* wms-icon-color */
  --ark-chat-fileimg-ext-text: rgb(255, 255, 255); /* wms-fileimg-extension-text-color */
  --ark-chat-fileimg-ext-bg: rgb(72, 72, 72);      /* wms-fileimg-extension-bg-color */
}
```

### 1.2 Typography

**Confirmed (devtools-inspected, computed styles on a top-bar element — the global search input):**

```css
font-family: Zoho_Puvi_Regular, sans-serif;
font-size: 14px;
color: rgb(211, 214, 222);      /* #D3D6DE — text color inside the search input specifically */
font-variant-ligatures: no-contextual;
font-variant-numeric: tabular-nums;
text-rendering: optimizeLegibility;
unicode-bidi: isolate;
```

- **"Puvi" is Zoho's in-house webfont**, used across Zoho One. Two different `font-family` names surfaced across the two devtools pulls: the search-input element's computed style resolves to `Zoho_Puvi_Regular`, while the `@font-face` block the user found (scoped to Zoho's global-search widget specifically, note the `gs_zohosearch` prefix on the family name and all its sibling `--zs-gs*` CSS variables) declares the family as `gs_zohosearchPuvi`. Both point at the same underlying files, just aliased differently per widget — don't worry about which literal string to use; what matters is the files.
- **Confirmed weight lineup**, all served from `/zohofonts/zohopuvi/4.0/` (host-relative — see prior message for how to resolve the real domain via the Network tab):

  | Weight | Style | File |
  |---|---|---|
  | 100 (Thin) | normal | `Zoho_Puvi_Thin` |
  | 300 (Light) | normal | `Zoho_Puvi_Light` |
  | 400 (Regular) | normal | `Zoho_Puvi_Regular` |
  | 600 (Semibold) | normal | `Zoho_Puvi_Semibold` |
  | 700 (Bold) | normal | `Zoho_Puvi_Bold` |
  | 900 (Black) | normal | `Zoho_Puvi_Black` |
  | 300/400 | italic | `Zoho_Puvi_Regular_Italic` |
  | 700/900 | italic | `Zoho_Puvi_Bold` *(Zoho's own CSS reuses the upright Bold file for bold-italic — not a true italic cut; don't replicate that quirk, just skip bold-italic or fake it with `font-style: oblique` if ARK needs it)* |

  Each weight is available as `.woff2` (grab this, it alone covers all modern browsers — skip `.eot`/`.ttf`/`.otf`/`.svg`, those are legacy fallbacks in Zoho's own multi-format `src` list).

- **Licensing note that changes the recommendation**: Zoho's own CSS falls back from Puvi to **Lato**, then **Roboto**, for extended character-set coverage (visible in the same stylesheet dump — full Lato and Roboto families with per-script `unicode-range` splits). Both Lato and Roboto are openly licensed (SIL Open Font License / Apache 2.0) and freely available via Google Fonts — unlike Puvi, which is proprietary to Zoho. So instead of chasing Puvi at all: **`"Lato", -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`** is a legitimate, low-risk substitute — it's literally in Zoho's own fallback chain, so text that isn't rendered in Puvi-specific chrome will already look identical, and the parts that are Puvi-specific will be close in weight/proportion since Lato was chosen as its visual fallback in the first place.
- If the user still wants pixel-exact Puvi: pull the six `.woff2` files above via devtools (Network tab, resolve the real domain), hand them over, and this doc gets a working `@font-face` block + local file paths in return. Until then, ship with Lato.
- Add `--ark-text-input: #d3d6de;` as a token — this is the confirmed color for text *typed inside* input/search fields, distinct from `--ark-text-primary` (#F5F5F5) used for static labels/values elsewhere. Slightly dimmer than primary text, since it sits on the `--ark-bg-input` fill.
- **`font-variant-numeric: tabular-nums` is important for a CRM** — apply it globally to any numeric column (deal values, ARR, GM%, contract years, KPI figures in the dashboard/reports) so digits align vertically in tables instead of jittering with proportional-width numerals.
- Base body font-size is confirmed **14px** (not 13–13.5px as originally estimated) — update the scale below accordingly.
- `text-rendering: optimizeLegibility` and `font-variant-ligatures: no-contextual` are safe global `body`/`:root` rules to carry over regardless of font choice.

- Scale (sizes/weights below the 14px body baseline are still visual estimates from the screenshots, not devtools-confirmed):
  | Token | Size | Weight | Usage |
  |---|---|---|---|
  | `--ark-font-page-title` | 20px | 700 | Page header ("Leads", "Deals", "Setup") |
  | `--ark-font-record-title` | 18px | 700 | Record detail title ("Mr. Arun Sundaram - Karat") |
  | `--ark-font-section-header` | 14px | 700 | Card/section headers ("Lead Information", "General") |
  | `--ark-font-body` | 14px | 400 | Table cells, field values, input text *(confirmed)* |
  | `--ark-font-label` | 13px | 400–500 | Field labels, column headers |
  | `--ark-font-meta` | 12px | 400 | Timestamps, secondary meta, breadcrumb crumbs |
  | `--ark-font-button` | 13.5px | 600 | Button labels |

- Column headers in tables are medium-weight, `--ark-text-secondary` colored, not fully bold.
- Field labels in record/detail views are `--ark-text-secondary`; values are `--ark-text-primary`; text typed into inputs is `--ark-text-input`.

### 1.3 Spacing & Radius

```css
:root {
  --ark-radius-sm: 4px;    /* checkboxes, small badges */
  --ark-radius-md: 6px;    /* buttons, inputs, table row hover highlight */
  --ark-radius-lg: 8px;    /* cards, panels, kanban cards, modals */
  --ark-radius-pill: 999px; /* segmented tabs, status pills, avatar */

  --ark-space-1: 4px;
  --ark-space-2: 8px;
  --ark-space-3: 12px;
  --ark-space-4: 16px;
  --ark-space-5: 24px;
  --ark-space-6: 32px;

  --ark-header-height: 56px;   /* global top bar */
  --ark-sidebar-width: 232px;  /* left nav, expanded */
  --ark-sidebar-width-collapsed: 56px;
}
```

- Card padding: 16–20px internal, 16–24px gap between cards in a grid (see Setup screen).
- Table row height: ~44–48px, comfortable but dense; no zebra striping — separation is a single 1px `--ark-border` bottom border per row (this border is a visible mid-gray, not a faint hairline — see §1.1 correction note).
- Shadows are mostly absent in the base UI — depth comes from background-color layering (page < panel < raised) for most surfaces. The one confirmed exception is the dashboard: use `--ark-dashboard-header-shadow` / `--ark-dashboard-thumb-header-shadow` / `--ark-dashboard-thumb-footer-shadow` on dashboard widget cards specifically. For other floating elements (dropdowns, tooltips, modals) a generic `box-shadow: 0 4px 16px rgba(0,0,0,0.4);` is a reasonable estimate.

---

## 2. Global Layout Components

### 2.1 Top Bar (global header, present on every screen)

Left to right:
1. Back arrow (only on drill-in/settings screens) or brand logo mark (small rounded-square icon + wordmark, e.g. "Zoho CRM") on top-level screens.
2. Page title, bold, left-aligned right after logo/back-arrow.
3. *(spacer)*
4. Global search box — pill/rounded-rect, `--ark-bg-input` fill, left-aligned search icon, muted placeholder text ("Search records"), gets focus ring `--ark-accent` on focus. **Confirmed via devtools**: `height: 34px`, `width: 411px` (at default viewport — likely responsive below this), inner layout is `display: flex; align-items: center;`, `overflow: hidden` both axes, text color `--ark-text-input` (#D3D6DE), `font: 14px Zoho_Puvi_Regular` (see §1.2).
5. Quick-create "+" button — small square, accent-outlined or accent-filled, `--ark-radius-md`.
6. Utility icons (calendar, "app grid"/store icon, settings gear) — plain outline icons, muted color, no background until hover (`--ark-bg-hover` circle/rounded-square on hover).
7. User avatar — filled circle, `--ark-avatar-accent` background, single-letter initial, white bold text.
8. App-switcher "waffle" grid icon — rightmost.

```
[Logo]  Page Title                [Search box]  [+]  [🗓][🏪][⚙]  (Avatar)  [⠿]
```

Height: `--ark-header-height` (56px). Background: `--ark-bg-page` (same as page — the header does *not* sit on a visibly distinct panel, it's flush).

### 2.2 Left Sidebar Navigation

Two nested levels observed:
- **Primary rail** (Home, Reports, Modules-search, then a flat list of module links: Leads, Contacts, Accounts, Deals, Tasks, Meetings, Calls, Campaigns, Documents, Visits, Projects…).
- **Settings/Setup rail** (different content when inside Setup: Frequently Used, General, Security Control, Channels, Customization, Automation, Data Administration, Marketplace, Developer Hub — each a collapsible group with chevron, sub-items indented).

Pattern:
- Background `--ark-bg-sidebar`, full height, fixed width `--ark-sidebar-width`.
- Each nav item: icon (18–20px outline, `--ark-text-secondary`) + label (`--ark-font-label`), full-width clickable row, `--ark-radius-md` corners, `--ark-space-2` vertical padding.
- **Active item**: background `--ark-accent-subtle-bg` OR solid `--ark-bg-panel` fill with `--ark-text-primary` (white) label + icon; screenshots show two active-state variants — a light-gray filled pill (Setup sidebar: "Modules and Fields" selected = light-gray/white filled bg with dark text) and a plain bold-white-text style with no background (main sidebar: "Home" selected = just bold blue-ish text + icon tinted, subtle bg). Implement as: **active = `--ark-bg-hover` background + `--ark-text-primary` text + accent-tinted icon**; keep it configurable since Zoho itself isn't fully consistent between these two contexts.
- Hover state (non-active): `--ark-bg-hover` background, no border.
- Collapsible section header (Setup sidebar groups): label + chevron icon that rotates on expand/collapse, `--ark-font-label` weight 600.
- A small colored square icon (pink/magenta) marks the "Modules" search entry point in the main sidebar — treat as one-off accent, not a pattern to replicate broadly.
- Sidebar can collapse to icon-only rail (`--ark-sidebar-width-collapsed`) — toggle icon top-left of sidebar (seen as a small rectangle icon next to the logo).

### 2.3 Bottom-Right Utility Dock

A slim, fixed, dark strip pinned to the bottom-right of the viewport across nearly every screen, containing small icon buttons (feedback/megaphone, history/undo, alarm, restore/undo-circular, info) followed by a pill-shaped **"Help"** button (`--ark-avatar-accent` fill — the reference screenshots show this pill in the same purple/magenta as the avatar, not the blue `--ark-accent`; treat both as the same unconfirmed accent — white text, `--ark-radius-pill`), and a print icon. Implement as a persistent low-profile toolbar, `--ark-bg-page` background, icons `--ark-text-muted`, hover → `--ark-text-primary`.

---

## 3. Page-Level Patterns

### 3.1 List / Table View (e.g. Leads list, Accounts list)

- Header row above the table: view-name dropdown (e.g. "All Leads ▾"), overflow "…" menu, right-aligned primary action button pair — **filled accent button** ("Create Lead") + attached **dropdown caret** in a slightly darker shade, plus a square icon-only "…" secondary button.
- Sub-header toolbar: `Filter` (funnel icon + label), `Sort` (up/down arrows + label), then 2–3 view-mode icon toggles (list view / kanban / split view), left-aligned. All plain text+icon buttons, no border until hover/active (active = `--ark-bg-hover` or accent-tinted icon).
- Table:
  - Checkbox column first (row select), then a "select-all" checkbox in the header.
  - Sortable column headers rendered in **`--ark-text-primary` (near-white), not muted gray** — video confirms headers are as bright as the row content, distinguished by weight/position rather than color. An "All ▾" mini-filter dropdown sits embedded in the first column header.
  - Rows: 1px bottom divider, hover = `--ark-bg-hover`, no zebra. **Divider correction**: `--ark-border` (`#6d6d6d`) is an *input/control* border value — table row dividers in the live UI are considerably fainter than that. Use a low-opacity divider (roughly `rgba(255,255,255,0.06–0.09)`, or `--ark-border` at ~15–20% opacity) for row separators; reserve full-strength `--ark-border` for input fields, buttons, and card outlines.
  - **Row height is roomy, not cramped** (~50–55px at 1080p). Don't over-compress rows chasing "enterprise density" — Zoho's tables breathe.
  - Primary column value rendered as a colored link (`--ark-link`), rest of columns plain `--ark-text-primary`/secondary.
  - Rightmost column header has a small "column chooser" icon (sliders/settings glyph) to configure visible columns.
  - Horizontal scroll for wide tables — visible, styled scrollbar track in `--ark-bg-panel`.
  - Footer bar: "Total Records N" left, pagination controls ("1 to 10", prev/next chevrons) right, sits on its own thin footer strip, same page background.

### 3.2 Kanban / Stage View (e.g. Deals "Stageview")

- Horizontal scrolling column set, one column per pipeline stage.
- Column header: stage name (bold) + a small circular count badge (`--ark-info-teal-bg` fill, `--ark-info-teal` text, or neutral gray when count = 0) + percentage value + currency total beneath, all inside a card-like header block with a **colored top border/accent on the currently-relevant or in-focus stage** (teal in the reference).
- Column body: vertical stack of record cards, `--ark-bg-panel-raised`, `--ark-radius-lg`, `--ark-space-3` internal padding, `--ark-space-2` gap between cards; each card shows: title (bold), 2–3 secondary lines (stage, contact names), a small colored status/date line (e.g. a due-date in accent/warning color) at the bottom.
- Empty column state: centered muted text "No Deals found." plus a "Create Deal" link and a collapse/expand arrow control at the column's bottom edge.
- A small pencil/edit icon sits next to the "STAGEVIEW" section label, and a "Filter Deals by" collapsible side panel can appear to the left of the board (see 3.4).

### 3.3 Record Detail View (e.g. Lead detail)

- Header: back-chevron + record title (Name — Company) bold, primary action button (filled accent, e.g. "Send Email"), 2–3 secondary buttons (outline/filled-neutral: "Convert", "Edit"), an overflow "…" menu, then prev/next record chevrons at the far right.
- Left rail *within* the record page: "Related List" navigation (Notes, Attachments, Open Activities, Closed Activities, Emails, Campaigns, …) — same nav-item styling as the global sidebar but scoped to this record.
- Main panel:
  - A pill/segmented control at the top: **Overview | Timeline** (rounded-full container, active segment = solid `--ark-bg-panel-raised`/white pill with dark text, inactive = transparent with muted text) plus a small "last update" meta timestamp aligned right.
  - Field rows: label left (`--ark-text-secondary`, fixed-width column) → value right (`--ark-text-primary`), one per row, generous vertical rhythm (~40px row height). Empty values render as an em-dash "–".
  - Inline-edit affordance: hovering a value reveals a bordered input box + small edit-pencil icon (seen on "Mobile" field) — restyle existing inline-edit UI to match this bordered-box-on-hover pattern rather than building new inline-edit behavior if ARK doesn't have it.
  - Collapsible section divider: "Hide Details" / "Show Details" text link, full-width, acts as a section boundary before deeper field groups (e.g. "Lead Information").
  - Section header ("Lead Information") is bold, sits inside its own subtle-bordered block, with a settings-gear icon aligned right for section-level configuration (admin context only).

### 3.4 Filter Side Panel (e.g. Accounts filters)

- Appears as a left-inset panel within the content area (not the global sidebar) — background `--ark-bg-panel`, `--ark-space-3` padding, `--ark-radius-lg`.
- Header: "Filter [Module] by" bold, then a search box (`Search`, same input styling as global search).
- Grouped, collapsible sections with a bold header + chevron: **"System Defined Filters"**, **"Filter By Fields"** — each a checkbox list, `--ark-font-body`, `--ark-space-2` row spacing, hover-state tooltip showing the full label when truncated (dark tooltip, `--ark-bg-panel-raised`, small rounded box, appears above/beside the item).

### 3.5 Setup / Admin Grid (e.g. Setup home)

- Card grid, responsive columns (5 → wraps on width), each card:
  - Header row: small category icon (outline, `--ark-text-secondary`) + bold title.
  - List of plain-text nav links beneath, one per line, `--ark-text-link`-less (these are plain `--ark-text-primary`/secondary links, underline-on-hover only), `--ark-space-1`–`--ark-space-2` line spacing.
  - Card background `--ark-bg-panel-raised`, `--ark-radius-lg`, no border needed (background-layer contrast is enough), `--ark-space-4` internal padding.
  - A local "Search Setup" input sits above the grid, same input styling, slightly wider, with a subtle **focus glow ring** in accent color (visible in the reference on click).

### 3.6 Field Builder / Customization Canvas (e.g. Modules → Leads layout editor)

- Left palette: grid of field-type "chips" (icon + label, e.g. "Single Line", "Email", "Pick List"), 2-column grid, each chip a bordered rounded rect, draggable, hover = `--ark-bg-hover`.
- Center canvas: the actual form preview, grouped into bordered sections with a header bar (bold title + settings-gear icon, right-aligned).
- Each field row in the canvas: icon + label inside a bordered box (`--ark-radius-md`, `--ark-border`), a "⋮⋮⋮" three-dot handle/menu at the row's right edge, and **required fields get a colored left border accent** (`--ark-danger` red bar, ~3px, flush left of the field box) instead of an asterisk.
- Top action bar for this screen: module name + variant dropdown ("Standard ▾") + gear icon on the left; tab switcher **Create | Quick Create | Detail View** (underline-style tabs, active = accent underline + bold text) centered; Cancel / Save and Close / Save buttons on the right (Save = filled accent, primary; the other two = neutral/outline).

### 3.7 Home Dashboard

- Card-based widget grid (e.g. "My Open Tasks", "My Meetings"), each card: bold title + inline icon-buttons (refresh, overflow "⋮") in the header, a `Sort` control, a mini-table beneath with its own column headers, and a muted centered empty-state message ("No Tasks found.") when empty.
- Page-level control: a view-switcher dropdown top-right ("[User]'s Home ▾") + overflow menu, plus a refresh icon next to the page welcome banner.

---

## 4. Component Inventory → Likely ARK Mapping

Use this as a checklist when applying the theme. Confirm actual component names in the ARK codebase before editing.

| Zoho pattern | Likely ARK equivalent (verify) | Priority |
|---|---|---|
| Global top bar | `<AppHeader>` / `<TopNav>` | High |
| Left sidebar nav | `<Sidebar>` / `<NavRail>` | High |
| List/table view | `<DataTable>` / `<RecordList>` | High |
| Record detail page | `<RecordDetail>` / `<EntityView>` | High |
| Buttons (primary/secondary) | shared `<Button>` component + variants | High |
| Inputs / search box | shared `<Input>` / `<SearchBox>` | High |
| Filter side panel | `<FilterPanel>` | Medium |
| Kanban/Stage view | `<KanbanBoard>` / `<PipelineView>` (flag if absent) | Medium |
| Segmented tabs (Overview/Timeline) | `<Tabs>` / `<SegmentedControl>` | Medium |
| Status pill / toggle switch | `<Switch>` / `<Badge>` | Medium |
| Setup/admin card grid | `<SettingsGrid>` (flag if absent) | Low |
| Field builder canvas | admin-only, likely out of scope for a v1 pass | Low |
| Bottom-right utility dock | new/flag if ARK has no equivalent | Low |

---

## 5. Do / Don't Summary

**Do:**
- Centralize all colors/spacing/radii as tokens (CSS variables, Tailwind `theme.extend`, or ARK's existing theming mechanism) so the whole re-skin is togglable.
- Match the *layering* model: page background < panel background < raised/card background, rather than relying on borders/shadows for depth.
- Keep dense, data-heavy tables — this is a CRM, not a marketing site; don't add whitespace Zoho itself doesn't have.
- Preserve existing keyboard/focus/ARIA behavior; only change the focus ring's *appearance* to `--ark-focus-ring`.

**Don't:**
- Don't introduce a light theme unless asked — none of the reference screenshots show one.
- Don't invent new icons/features to "complete" a pattern ARK doesn't have (e.g. don't build a Kanban board from scratch just because Zoho has one) — restyle what exists, flag what doesn't.
- Don't rename routes, component props, or IDs to match Zoho's naming ("Deals", "Stageview", etc.) — keep ARK's existing terminology; only the *visual* system changes.
- Don't hardcode hex values inline across components — always reference the token layer so future palette tweaks are a one-file change.

---

## 5a. Video-Derived Findings (Round 3)

Sourced from a 2:52 screen recording of the live Zoho CRM org. These supersede the screenshot-only guesses where they conflict.

### 5a.1 Sidebar is far richer than the screenshots showed

Top-to-bottom structure:

1. **Product switcher** — Zoho logo mark + "Zoho CRM ▾" (dropdown to other Zoho apps) + a sidebar-collapse toggle icon on the right.
2. **Flat top-level items** — Home, Reports, Analytics, My Requests. (Each with a distinctly *colored* icon — Reports pink/red, Analytics purple, etc. — not monochrome.)
3. **Teamspace selector** — a square avatar chip ("CT") + "CRM Teamspace ▾" + a "…" overflow. This is a scoping/context switcher above the module list.
4. **Sidebar-scoped search box** — separate from the global top-bar search.
5. **Workqueue** — standalone item with an ✨ AI-sparkle icon suffix.
6. **Collapsible module groups**, each with a group header (folder icon + name + a `+` quick-add button + chevron):
   - **Sales** → Pre Leads, Leads, Contacts, Accounts, Deals, Forecasts, Documents, Campaigns
   - **Inventory** → Products, Price Books, Quotes, Sales Orders, Purchase Orders, Invoices, Vendors
   - **Activities**, **Support** (further groups below the fold)
7. Each module row reveals a "…" overflow menu **on hover**.
8. **Active module** = solid lighter-gray pill filling the full sidebar width, brighter icon + white text.

**Implication for ARK**: ARK's sidebar is currently a flat 13-item list. Zoho's is grouped/collapsible with a teamspace scope on top. Grouping ARK's modules (e.g. Sales: Leads/Opportunities/Deals/Accounts/Contacts · Commercial: Quotes/Products/Approvals · Delivery: Gates/Activities) would match the reference much more closely — but this is a **structural nav change, so confirm with the user before doing it**; it's not a pure restyle.

### 5a.2 Toolbar has 6–8 view-mode toggles, not 2–3

The row reads: `Filter` · `Sort` │ then a run of view icons — **list, kanban, table/grid, chart/donut, canvas, sheet-view**, plus a map-pin on location-bearing modules, a refresh icon, and a `⌄` "more views" chevron. Then right-aligned: **`Create <Module>` split-button** (blue filled + attached `▾` caret) and a separate square `…` icon button.

Note the Create button label is **dynamic per module** ("Create Lead", "Create Pre Lead", "Create Account", "Create Product", "Create Purchase Order").

### 5a.3 Confirmed patterns

- **View-name chip** ("All Leads", "All Accounts", "All Products") is a **filled gray rounded-rect pill**, not plain text, with a `…` beside it.
- **Row hover** reveals left-edge inline icons: `⋯` menu, comment/note icon, checkbox, and a small activity/pulse icon — exactly as documented in §3.1.
- **Footer** confirmed on every list view: `Total Records N` left, `1 to N` + prev/next chevrons right.
- **Green is a real palette color** (not just my estimate): used for tertiary CTAs ("Get Started") and as the primary chart/data series color on dashboards. Treat `--ark-success` as confirmed-in-spirit, though the exact hex still isn't extracted.

### 5a.4 Empty-state pattern (new — not in the screenshots)

A module with no records shows: a large panel containing a **bold title**, a **descriptive paragraph** explaining what the entity is ("Purchase Orders are legal documents for placing orders…"), and a **primary filled CTA** ("Create Purchase Order"). Optionally a right-hand promo/related panel with an icon row, bullet list, and its own green CTA. Worth copying — ARK's empty states should explain the entity, not just say "No records found."

### 5a.5 Dashboard/Analytics page (confirms the darker page variant)

- The Analytics page background is **visibly darker than list pages** — this validates `--ark-bg-page-alt` (`#151415`) being scoped to dashboards only.
- Widget cards: **UPPERCASE titles**, an inline refresh icon next to the title, `⋮` menu top-right, chart area below.
- Header controls: `All ▾` filter + a starred `Org Overview ▾` dashboard selector on the left; refresh icon, **`Add Component` (dark secondary, bordered)** + **`Create Dashboard` (blue primary filled)** + `…` on the right — a clean example of the secondary/primary button pairing.

### 5a.6 Bottom dock is a full-width bar, not a right-corner cluster

Correction to §2.3. The actual bar spans the full viewport width:
- **Left**: `Chats` · `Channels` · `Contacts` tabs (icon above label).
- **Center**: a Smart Chat input hint — "Here is your Smart Chat (Ctrl+Space)".
- **Right**: ~8 utility icons, then the purple **`Help`** pill, then a panel-toggle icon.

For ARK this is almost entirely Zoho-product surface area (chat, channels) that ARK doesn't have — **don't build it**. Only the Help pill is worth considering.

### 5a.7 Top bar has more icons than documented

Full run, left→right after the page title: global **Search records** box · **`+`** (blue-outlined square quick-create) · **AI/sparkle** icon · **bell** (notifications) · **calendar** · **marketplace/store** · **settings gear** · **org logo** (the customer's own brand mark — Astrikos, in this org) · **waffle grid** app-switcher.

The **org logo slot** is notable: Zoho renders the tenant's own brand mark in the top bar. ARK could use this slot for the Astrikos mark.

---

## 6. Reference Assets

Source screenshots (Zoho CRM, dark theme) live at:
`C:\Users\Admin\Desktop\Zoho CRM UI\`

Screens covered: Setup home grid · Setup → Modules and Fields list · Leads field-builder/layout editor · Deals Kanban (Stageview) · Lead record detail (Overview tab) · Leads list/table view · Accounts list with Filter panel · Home dashboard · Reports list.

Source video (2:52, 1920×1080) at `C:\Users\Admin\Desktop\Zoho CRM .mp4` — covers Leads kanban, Pre Leads / Accounts / Products list views with filter panels, Purchase Orders empty state, and the Analytics dashboard. Findings from it are in §5a.

**Confirmed color values** came from the user's own devtools extraction of Zoho's `.zmNightMode` / `.zsNightMode` custom properties, and the typography facts from computed styles on the global-search input. Those are authoritative; layout/spacing/structure notes remain visual estimates.
