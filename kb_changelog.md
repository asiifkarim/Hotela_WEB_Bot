# KB changelog — old file to new file

Scope: the knowledge base only. The chat API, the frontend and the database schema are untouched. Work landed on branch `kb-reconcile` after the baseline commit `178bfc3`.

## Measured before and after

| Metric | Before | After | How it was measured |
|---|---|---|---|
| Knowledge files (one topic each) | 21 | **9** | `find kb -name '*.md'` split by generation; canonical files are `kb/<topic>.md` |
| Files under `kb/` in total | 24 | 33 | `find kb -type f`; after: 9 canonical + `GAPS.md` + `plans.json` + `archive/README.md` + 21 archived files |
| Indexed documents | 14 (13 Markdown + `plans.json`) | **10** (9 Markdown + `plans.json`) | `kb_documents()` in `backend/app/rag/chunker.py` |
| Indexed chunks | 71 | **61** (−14%) | chunker run over the old `kb/curated/` set and the new `kb/*.md` set |
| Estimated KB tokens (validator) | 10,722 | **10,132** | `python backend/scripts/validate_kb.py` |
| Estimated tokens, whole `kb/` tree | 13,866 | 10,939 indexed + archive | `python scripts/kb_audit.py` |
| Files with the full front matter (title, topic, source, last_updated, version, audience) | 0 | **9** | validator |
| Exact or line-ending-normalised duplicates | 0 | 0 | `scripts/kb_audit.py` |
| Near-duplicate pairs ≥ 0.25 similarity (indexed set) | 25 over 21 files | 15 over 9 files | same script; the residual pairs share topic vocabulary, not claims |
| Longest identical passage between two indexed files | 26 words | **15 words** | same script; the 15 words are the `plans.json` feature list quoted in the plan table and the channel-manager sentence quoted in the FAQ |
| TODO/CONFLICT notes inside indexed prose | 0 | 0 | validator |
| Validator result | exit 0 (13 files, no front-matter schema) | **exit 0 (9 files, 61 chunks)** | `python backend/scripts/validate_kb.py` |

Retrieval quality (hit rate, MRR, faithfulness) is *not* measured here: that baseline arrives with the evaluation pass, because the provider path (Gemini for generation, local sentence-transformers for embeddings) is not reliable in this environment yet. Nothing in this change is claimed as a quality improvement until that pass measures it.

## Old to new map

### Generation 1 — the website build (2026-10-02), archived to `kb/archive/website-2026-10-02/`

| Old file | New file | Why |
|---|---|---|
| `about.md` | `kb/app_how_to.md`, `kb/policies.md` | Getting-started steps, values and the uptime support statements split into how-to and policy topics |
| `faq.md` | `kb/faq.md` | Superseded by the fuller FAQ; its trial, multi-property and booking-channel answers were checked and kept |
| `modules-reservations.md` | `kb/bookings.md` | Reservations and the channel-manager statement; the "not found" note for OTA names is now an explicit "not published" line |
| `modules-rooms.md` | `kb/rooms_pricing.md` | Rooms, housekeeping and the Stay plan feature list |
| `modules-accounts.md` | `kb/finances.md`, `kb/invoices.md` | Accounts split into money tracking and billing records |
| `modules-restaurant-events.md` | `kb/bookings.md`, `kb/app_how_to.md` | Restaurant features and the events note that wrongly said event features were unknown |
| `modules-staff-inventory.md` | `kb/app_how_to.md` | Staff, payroll and inventory screens |
| `modules-customers-branches.md` | `kb/customers.md`, `kb/app_how_to.md`, `kb/rooms_pricing.md` | Customers, multi-branch access and the per-branch pricing statement |

### Generation 2 — the reviewed build (2026-10-09 → 2026-10-15), archived to `kb/archive/reviewed-2026-10-15/`

| Old file | New file | Why |
|---|---|---|
| `hotela-about.md` | `kb/faq.md`, `kb/policies.md` | "What Hotela is" belongs in the FAQ; the plan summary belongs in policies |
| `hotela-plans-and-subscription.md` | `kb/policies.md`, `kb/rooms_pricing.md` | Plan features and subscription terms into policies; price and branch facts into rooms_pricing |
| `policies-limits.md` | `kb/policies.md` | Trial, cancellation, security, support and the assistant's limits |
| `support-contact.md` | `kb/app_how_to.md` | Contact channels and signup steps merged into the how-to file |
| `hotela-getting-started-and-support.md` | `kb/app_how_to.md` | Getting-started steps, dashboard walkthrough, staff, inventory |
| `hotela-feature-availability.md` | `kb/app_how_to.md` | The confirmed / website-stated / not-confirmed ledger, now the closing section of the how-to file |
| `hotela-hotel-management.md` | `kb/bookings.md`, `kb/rooms_pricing.md`, `kb/customers.md` | Reservations and check-in into bookings; rooms and housekeeping into rooms_pricing; guests into customers |
| `hotela-restaurant-management.md` | `kb/bookings.md`, `kb/invoices.md` | Table reservations into bookings; food and restaurant invoices into invoices |
| `hotela-accounting-finance.md` | `kb/finances.md`, `kb/invoices.md` | Transactions, expenses and petty cash into finances; invoice records into invoices |
| `hotela-events.md` | `kb/bookings.md`, `kb/finances.md` | Event bookings into bookings; event revenue and expenses into finances |
| `hotela-multi-branch-reporting.md` | `kb/app_how_to.md`, `kb/finances.md` | Branch management and the branch filter into how-to; reporting into finances |
| `hotela-staff-inventory-customers.md` | `kb/app_how_to.md`, `kb/customers.md` | Staff and inventory into how-to; customers into customers |
| `hotela-visitor-faq.md` | `kb/faq.md` | The FAQ, now with one answer per question and no price numbers in prose |

### New files

| File | Why it exists |
|---|---|
| `kb/glossary.md` | One term per concept plus the words visitors use, so the same question cannot be answered with two different names |
| `kb_audit.md` | The duplicate audit this change was based on, with hashes and similarity numbers |
| `kb_changelog.md` | This map |
| `scripts/kb_audit.py` | Reproduces the audit; stdlib only |
| `kb/archive/README.md` | Points at the two archived generations and the canonical file for each old file |

### Kept unchanged

| File | Why |
|---|---|
| `kb/plans.json` | Still the single source for plan names, prices, billing period and plan features. No price number was moved into Markdown |
| `kb/GAPS.md` | The human-decision register; extended in this pass (see below) |

## Contradictions resolved in this pass

1. **Channel manager / OTA sync** — confirmed for Hotela Stay and Hotela Suite. The old files both confirmed and denied it; the features and pricing pages plus `plans.json` all list it. Platform names stay unconfirmed.
2. **7-day free trial** — confirmed for every plan ("Every plan starts with a 7-day free trial", pricing page). One reviewed file had dropped it, which read as a denial.
3. **Hotela Suite feature set** — the `plans.json` / pricing-page wording kept verbatim: everything in Stay & Dine, unified dashboard, multi-branch & roles, channel manager, priority 24/7 support. "Advanced Analytics" was dropped because no published source lists it.
4. **Plans vs limits** — prices are per branch, not per room; six-month billing; the pricing page offers a branch selector and says "need more? Contact us after signup", while every plan card reads "1 branch". What a second branch costs is *not* published and is escalated.
5. **Prices in prose** — price numbers were removed from Markdown; `plans.json` is the only price source.
6. **Event features** — one old file said event features were unknown; the dashboard screens document them, so they are recorded from those screens.

Evidence pages were re-read live on 2026-10-15 (both HTTP 200): `hotelaapp.com/features` and `hotelaapp.com/pricing`. Quotes are in `kb_audit.md`.

## Claims escalated to a human

Seventeen items, all in `kb/GAPS.md`, which is never indexed. The four that block the most answers:

1. What a second branch costs, and what the branch limit per plan is.
2. Annual prices (offered on the pricing page, never published).
3. Whether the assistant may say "Advanced Analytics", offline POS and the desktop apps.
4. Which OTAs the channel manager connects to.

## How to use this KB now

```bash
python backend/scripts/validate_kb.py     # exit 0 means the layout, front matter and registers are sound
python backend/scripts/build_index.py     # rebuilds the Chroma index from kb/*.md + kb/plans.json
```
