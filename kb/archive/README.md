# Archived knowledge base files

Nothing in this directory is indexed. The indexed set is every top-level `kb/*.md` that carries the six front-matter keys, plus `kb/plans.json`; the loader in `backend/app/rag/chunker.py` never descends into subfolders, and `backend/scripts/validate_kb.py` fails if a knowledge file appears anywhere else.

These files are kept only for provenance: the source URLs, the original wording and the earlier review notes. Do not copy content back into `kb/`; if a claim from here is needed, add it to the canonical file for that topic.

Two generations are archived:

## `website-2026-10-02/` — built from the public website and blog pages

| Archived file | Canonical file now | Reason |
|---|---|---|
| `about.md` | `kb/app_how_to.md`, `kb/policies.md` | Second "about" file; getting-started and the website's values/uptime lines split by topic |
| `faq.md` | `kb/faq.md` | Second FAQ with competing answers |
| `modules-reservations.md` | `kb/bookings.md` | Reservations duplicated |
| `modules-rooms.md` | `kb/rooms_pricing.md` | Rooms duplicated |
| `modules-accounts.md` | `kb/finances.md`, `kb/invoices.md` | Accounts duplicated |
| `modules-restaurant-events.md` | `kb/bookings.md`, `kb/app_how_to.md` | Restaurant and events duplicated; its events note said the features were unknown after the dashboard screens had documented them |
| `modules-staff-inventory.md` | `kb/app_how_to.md` | Staff and inventory duplicated |
| `modules-customers-branches.md` | `kb/customers.md`, `kb/app_how_to.md`, `kb/rooms_pricing.md` | Customers and branches duplicated |

## `reviewed-2026-10-15/` — the reviewed build, itself superseded by the topic layout

| Archived file | Canonical file now | Reason |
|---|---|---|
| `hotela-about.md` | `kb/faq.md`, `kb/policies.md` | "What Hotela is" duplicated the FAQ; the plan summary duplicated policies |
| `hotela-plans-and-subscription.md` | `kb/policies.md`, `kb/rooms_pricing.md` | Plan features and price facts were split across two topics |
| `policies-limits.md` | `kb/policies.md` | Same topic, renamed |
| `support-contact.md` | `kb/app_how_to.md` | Contact details and signup duplicated getting-started |
| `hotela-getting-started-and-support.md` | `kb/app_how_to.md` | Same topic, merged |
| `hotela-feature-availability.md` | `kb/app_how_to.md` | The availability ledger duplicated the FAQ and the block for the channel manager |
| `hotela-hotel-management.md` | `kb/bookings.md`, `kb/rooms_pricing.md`, `kb/customers.md` | Split by topic |
| `hotela-restaurant-management.md` | `kb/bookings.md`, `kb/invoices.md` | Split by topic |
| `hotela-accounting-finance.md` | `kb/finances.md`, `kb/invoices.md` | Split into money tracking and billing records |
| `hotela-events.md` | `kb/bookings.md`, `kb/finances.md` | Event bookings and event money split |
| `hotela-multi-branch-reporting.md` | `kb/app_how_to.md`, `kb/finances.md` | Branch management and reporting split |
| `hotela-staff-inventory-customers.md` | `kb/app_how_to.md`, `kb/customers.md` | Split by topic |
| `hotela-visitor-faq.md` | `kb/faq.md` | Same topic, renamed |

The review that produced the current layout, the duplicate measurements and the claims that still need a human decision are recorded in `kb_audit.md`, `kb_changelog.md` and `kb/GAPS.md`.
