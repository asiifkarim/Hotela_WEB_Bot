# KB audit — duplicate and near-duplicate inventory

Run date: 2026-10-15 · Branch: `kb-reconcile` · Baseline commit: `178bfc3` (nothing was under version control before it)

Reproduce every number in this file:

```bash
python scripts/kb_audit.py            # stdlib only, no app dependencies
python scripts/kb_audit.py --root kb --threshold 0.25
```

## What was audited

`kb/` before this pass held **24 files in two generations** of the same knowledge:

| Generation | Location | Files | Front matter | Written |
|---|---|---|---|---|
| Legacy, built from the public website and blog pages | `kb/archive/` | 8 docs + README | `topic`, `source`, `updated` | 2026-10-02 |
| Reviewed pass, built from the Hotela dashboard screens plus the website | `kb/curated/` | 13 docs | `topic`, `source`, `source_urls`, `updated` | 2026-10-09 → 2026-10-15 |
| Registers, not knowledge | `kb/GAPS.md`, `kb/plans.json` | 2 | none | 2026-10-15 |

Estimated tokens for the whole tree, including the registers: **13,866**.

## Inventory (measured)

| File | sha256 | Bytes | Lines | Est. tokens | topic | Front matter |
|---|---|---|---|---|---|---|
| `kb/archive/about.md` | `6789a1906107` | 1111 | 30 | 277 | about | yes |
| `kb/archive/faq.md` | `6b5e2380b2b2` | 1405 | 43 | 351 | faq | yes |
| `kb/archive/modules-accounts.md` | `fecc982c0df7` | 518 | 23 | 129 | accounts | yes |
| `kb/archive/modules-customers-branches.md` | `0bf932f0a67d` | 896 | 30 | 224 | customers-branches | yes |
| `kb/archive/modules-reservations.md` | `f4f31aebd3a1` | 1067 | 33 | 266 | reservations | yes |
| `kb/archive/modules-restaurant-events.md` | `9ce95c787cc1` | 639 | 27 | 159 | restaurant-events | yes |
| `kb/archive/modules-rooms.md` | `86e370cde8a9` | 612 | 24 | 153 | rooms | yes |
| `kb/archive/modules-staff-inventory.md` | `852e3ca1de0f` | 462 | 22 | 115 | staff-inventory | yes |
| `kb/archive/README.md` | `34948b055fab` | 1706 | 19 | 426 | – | no |
| `kb/curated/hotela-about.md` | `e6149c3e8789` | 2584 | 55 | 646 | about-hotela | yes |
| `kb/curated/hotela-accounting-finance.md` | `fd240d86cf2a` | 1937 | 43 | 484 | accounting-and-finance-features | yes |
| `kb/curated/hotela-events.md` | `f4bad44eb008` | 1043 | 31 | 260 | event-management-features | yes |
| `kb/curated/hotela-feature-availability.md` | `97cb76a1bb0b` | 3868 | 74 | 967 | feature-availability | yes |
| `kb/curated/hotela-getting-started-and-support.md` | `779e24d6dc7e` | 1415 | 36 | 353 | getting-started-and-support | yes |
| `kb/curated/hotela-hotel-management.md` | `8f54522a6e54` | 2970 | 64 | 742 | hotel-management-features | yes |
| `kb/curated/hotela-multi-branch-reporting.md` | `c7fbcc648857` | 1887 | 38 | 471 | multi-branch-and-reporting | yes |
| `kb/curated/hotela-plans-and-subscription.md` | `86509aef43ec` | 2940 | 52 | 735 | plans-and-subscription | yes |
| `kb/curated/hotela-restaurant-management.md` | `3048da41fa98` | 2147 | 46 | 536 | restaurant-management-features | yes |
| `kb/curated/hotela-staff-inventory-customers.md` | `d3e467282f7f` | 1817 | 40 | 454 | staff-inventory-customers-features | yes |
| `kb/curated/hotela-visitor-faq.md` | `260fb5ba6d8f` | 10129 | 141 | 2402 | visitor-faq | yes |
| `kb/curated/policies-limits.md` | `8749600ded3f` | 2149 | 44 | 537 | policies-limits | yes |
| `kb/curated/support-contact.md` | `b13d9e753c24` | 1261 | 34 | 315 | support-contact | yes |
| `kb/GAPS.md` | `73a0657516e7` | 10380 | 140 | 2594 | – | no |
| `kb/plans.json` | `f4dea39fd209` | 1083 | 45 | 270 | – | no |

**Exact duplicates (identical sha256): none. Content duplicates after line-ending normalisation: none. Topic collisions on the `topic:` field: none.** The duplication is not literal copying, it is *the same subject written twice in different words*, which is why a hash check alone would have missed it and a similarity check finds it.

## Near-duplicate pairs (measured, similarity ≥ 0.25)

Similarity = the higher of token-set Jaccard and 5-word-shingle Jaccard on the body text. 25 pairs crossed 0.25; the strongest:

| Similarity | Tokens | Shingles | File A | File B | Overlapping subject |
|---|---|---|---|---|---|
| 0.39 | 0.39 | 0.05 | `curated/hotela-getting-started-and-support.md` | `curated/support-contact.md` | Onboarding steps, trial, contact details |
| 0.36 | 0.36 | 0.02 | `curated/hotela-feature-availability.md` | `curated/hotela-visitor-faq.md` | Channel manager, mobile app, not-confirmed list |
| 0.34 | 0.34 | 0.05 | `curated/hotela-plans-and-subscription.md` | `curated/policies-limits.md` | Plans, prices, billing, cancellation |
| 0.31 | 0.31 | 0.04 | `curated/hotela-about.md` | `curated/hotela-visitor-faq.md` | What Hotela is and who it is for |
| 0.31 | 0.31 | 0.01 | `curated/hotela-about.md` | `curated/hotela-feature-availability.md` | Confirmed-vs-unconfirmed feature claims |
| 0.29 | 0.29 | 0.01 | `curated/hotela-hotel-management.md` | `curated/hotela-multi-branch-reporting.md` | Branch filter on hotel screens |
| 0.29 | 0.29 | 0.03 | `curated/hotela-hotel-management.md` | `curated/hotela-staff-inventory-customers.md` | Customer and guest records |
| 0.28 | 0.28 | 0.08 | `curated/policies-limits.md` | `curated/support-contact.md` | Trial, support hours |
| 0.27 | 0.27 | 0.02 | `archive/modules-customers-branches.md` | `curated/hotela-multi-branch-reporting.md` | Multi-property access, price per branch |
| 0.27 | 0.27 | 0.03 | `archive/faq.md` | `curated/policies-limits.md` | Free trial, price per branch, encryption |
| 0.27 | 0.27 | 0.02 | `curated/hotela-plans-and-subscription.md` | `curated/hotela-visitor-faq.md` | Plan names and features |
| 0.26 | 0.26 | 0.05 | `curated/hotela-getting-started-and-support.md` | `curated/policies-limits.md` | Getting-started path and support claims |
| 0.26 | 0.26 | 0.04 | `archive/faq.md` | `archive/modules-customers-branches.md` | Multi-property access |
| 0.25 | 0.25 | 0.00 | `curated/hotela-accounting-finance.md` | `curated/hotela-events.md` | Event revenue and payments |
| 0.25 | 0.25 | 0.01 | `curated/hotela-events.md` | `curated/hotela-restaurant-management.md` | Events run by restaurants |
| 0.25 | 0.25 | 0.01 | `curated/hotela-about.md` | `curated/hotela-plans-and-subscription.md` | What the plans are |
| 0.25 | 0.25 | 0.03 | `archive/faq.md` | `curated/hotela-visitor-faq.md` | FAQ answers, channel manager |
| 0.25 | 0.25 | 0.02 | `archive/about.md` | `curated/hotela-getting-started-and-support.md` | Getting started in four steps |

The remaining pairs are the same pattern at 0.25. Every pair above is a claim that could be answered from two files with different wording, which is exactly how a RAG bot produces two different answers to the same question.

## Duplicate groups, merged into one canonical file each

Nine canonical files replace twenty-one knowledge files. `kb_changelog.md` carries the same map with the reason per file.

| Canonical file | Merged from | Claims resolved |
|---|---|---|
| `kb/bookings.md` | `curated/hotela-hotel-management.md`, `curated/hotela-events.md`, `curated/hotela-restaurant-management.md`, `archive/modules-reservations.md`, `archive/modules-restaurant-events.md` | 1 |
| `kb/rooms_pricing.md` | `archive/modules-rooms.md`, `curated/hotela-hotel-management.md`, `curated/hotela-plans-and-subscription.md` | 1 |
| `kb/invoices.md` | `curated/hotela-accounting-finance.md`, `curated/hotela-restaurant-management.md`, `archive/modules-accounts.md` | 1 |
| `kb/finances.md` | `curated/hotela-accounting-finance.md`, `curated/hotela-events.md`, `curated/hotela-multi-branch-reporting.md` | – |
| `kb/customers.md` | `curated/hotela-staff-inventory-customers.md`, `archive/modules-customers-branches.md`, `curated/hotela-hotel-management.md` | – |
| `kb/policies.md` | `curated/hotela-plans-and-subscription.md`, `curated/policies-limits.md`, `kb/plans.json` | 3 |
| `kb/app_how_to.md` | `curated/hotela-getting-started-and-support.md`, `curated/support-contact.md`, `curated/hotela-feature-availability.md`, `curated/hotela-multi-branch-reporting.md`, `curated/hotela-staff-inventory-customers.md`, `archive/about.md`, `curated/hotela-about.md` | 2 |
| `kb/faq.md` | `curated/hotela-visitor-faq.md`, `archive/faq.md`, `curated/hotela-about.md` | 1 |
| `kb/glossary.md` | new file; terms collected from the files above | – |
| `kb/plans.json` | unchanged, still the only source for plan names, prices and plan features | 1 |

## Contradictions: resolved in this pass

| # | Claim | Where it conflicted | Resolution kept | Evidence |
|---|---|---|---|---|
| 1 | Channel manager / OTA sync | Confirmed in `archive/modules-reservations.md`, `archive/faq.md` and `plans.json`; denied as "not confirmed" in `curated/hotela-feature-availability.md`, `curated/hotela-hotel-management.md` and `curated/hotela-visitor-faq.md` | **Confirmed**, and listed for Hotela Stay and Hotela Suite. Platform names stay unconfirmed | Features page ("Channel Manager — Sync availability and rates across OTAs and booking platforms"), pricing page, `plans.json` |
| 2 | 7-day free trial | Stated in `archive/faq.md`, `curated/policies-limits.md` and `curated/support-contact.md`; absent from `curated/hotela-plans-and-subscription.md`, which read as a denial | **Confirmed**: every plan starts with a 7-day free trial, full access, no charge to begin | Pricing page ("Every plan starts with a 7-day free trial"), home page, signup page |
| 3 | Hotela Suite feature set | `plans.json` says "Everything in Stay & Dine, Unified dashboard, Multi-branch & roles, Channel manager, Priority 24/7 support"; `curated/hotela-about.md` and `curated/hotela-visitor-faq.md` said "Advanced Analytics" and left the combination to be confirmed | **`plans.json` / pricing-page wording, verbatim.** "Advanced Analytics" was dropped because no published source lists it | Pricing page; `plans.json` |
| 4 | Plans vs limits (price per branch, branch counts, billing) | `archive/modules-customers-branches.md` and `archive/faq.md` said prices are per branch and that a branch selector offers one to five; the reviewed files varied between "branch limit not published", "per branch" and the `plans.json` note "1 branch" | **Prices are per branch, not per room; six-month billing; every plan card reads "per branch · 1 branch · billed every 6 months" while the same page offers a branch selector and says "need more? Contact us after signup".** What a second branch costs is still unpublished, so it stays a human decision | Pricing page, re-read 2026-10-15: "Prices in PKR, per branch", "How many branches does your business have?", "Pricing is per branch · need more? Contact us after signup" |
| 5 | Prices repeated in prose | Prices appeared both in FAQ/prose files and in `plans.json` | **`plans.json` is the only source for plan names, prices, billing period and plan features**; no price numbers are written into any Markdown file | `plans.json` matches the pricing page |
| 6 | Events "features unknown" | `archive/modules-restaurant-events.md` said event features were not found; `curated/hotela-events.md` documents them from the dashboard | **Documented**, with the dashboard screens named as the source | Hotela dashboard Event Management screen |

### Pages re-read live on 2026-10-15

The two pages the contested claims depend on were fetched again during this pass, both HTTP 200:

- `https://hotelaapp.com/features` — "Channel Manager: Sync availability and rates across OTAs and booking platforms, never double-book"; "Accounts & Billing: Invoices, expenses, transactions and cash or bank payment records with reporting across every property"; "HR Management: Staff schedules, payroll and records for every department"; "Customer Support: 24/7 expert support and onboarding"; "Anywhere access: Works on every device, Windows & Mac desktop app, Real-time cloud sync, Offline-ready POS & front desk".
- `https://hotelaapp.com/pricing` — "Every plan starts with a 7-day free trial. Choose 6-month or annual billing. Prices in PKR, per branch."; "Pricing is per branch · need more? Contact us after signup"; plan cards "PKR 20,000 / PKR 35,000 per branch · 1 branch · billed every 6 months" with the feature lists quoted in `plans.json`; "Hotela Stay — priced per branch, not per room"; "Every plan includes: 7-day free trial, Free onboarding, No setup fees, Cancel anytime".

The claims that could not be checked against a page — the dashboard-screen facts — are listed as item 17 below.

## Claims escalated to a human

Every item below is unresolved and lives in `kb/GAPS.md`, which is not indexed and therefore can never be quoted to a visitor. Count: **17**.

| # | Claim needing a decision | Owner |
|---|---|---|
| 1 | "Advanced Analytics" as a Suite feature — keep it out, or publish it and add it to `plans.json` | Product, marketing |
| 2 | Offline-ready POS and front desk, Windows/Mac desktop apps, "works on every device" | Product |
| 3 | Mobile app: the footer shows App Store and Google Play buttons that link nowhere | Product, marketing |
| 4 | Which OTAs and booking platforms the channel manager connects to | Product |
| 5 | Every plan card says "1 branch" while the same page asks how many branches the business has and says "need more? Contact us after signup" — what does a second branch cost, and does the price multiply? | Sales |
| 6 | What happens after day 7 of the trial and whether a card is required | Product |
| 7 | Annual prices: offered on the pricing page, never published | Sales |
| 8 | Refund terms and the cancellation steps behind "cancel anytime" | Operations, legal |
| 9 | The exact branch limit per plan | Sales |
| 10 | How the 99.9% uptime figure is measured, and what the support targets are | Operations |
| 11 | May the assistant repeat the marketing figures (2,000+ teams, 15+ cities, 4.9/5)? | Marketing |
| 12 | Guest notifications (SMS/WhatsApp/email), payment gateway, online payment collection | Product |
| 13 | WhatsApp as a contact channel — no number is published and `HANDOFF_WHATSAPP` is empty | Support |
| 14 | Retention period and privacy notice for the chatbot's own stored messages and leads | Operations, legal |
| 15 | Evaluation questions that check English words against Roman Urdu or Urdu answers | Evaluation owner |
| 16 | **New:** Hotela Stay and Hotela Suite are both listed at PKR 35,000 for six months — confirm the Suite price is intentional | Sales |
| 17 | **New:** the facts marked "from the dashboard screens" have no published page behind them, so they can only be re-verified against the product; name the screenshots or seed data that back them | Product |

## Source quality

Two kinds of claim now sit in the knowledge base, and the files say which is which:

- **Published**: the website, pricing page, features page, about page and `plans.json`. Re-verifiable by anyone with the URL.
- **Dashboard-derived**: screen contents such as the reservation statuses, the petty-cash totals or the payroll tabs. These came from reviewing the Hotela dashboard; the files state the screen they came from, and item 17 above asks for the evidence to be pinned down.

Nothing was invented to fill a gap: every unresolved claim became a "not confirmed" line in the canonical file *and* an entry in `kb/GAPS.md`.

## Result

- Knowledge files: **21 → 9** canonical files (24 → 3 non-knowledge files counting the archive and registers, which are not indexed).
- Duplicate groups merged: **9**, listed above with the contributing files.
- Contradictions resolved: **6**; escalated: **17**.
- Estimated tokens for the indexed set: see `kb_changelog.md` for the before/after and `REPORT.md` for the measured chunk counts.
