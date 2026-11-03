# GAPS — claims that need a human decision

Maintainer file. It is **not** indexed: the retriever reads top-level `kb/*.md` files that carry front matter, plus `kb/plans.json`, and this file carries none. Nothing here is ever retrieved or shown to a visitor. Resolve an item, update the canonical file, then delete the item from this list.

Owner of this list: whoever owns the Hotela knowledge base. Every item below is a claim that cannot be settled from the published website, the dashboard screens or `plans.json`.

## What was already reconciled

The knowledge base carried two generations of the same topics, which produced contradictory answers. The review on 2026-10-15 merged them into one file per topic under `kb/`, re-read the pages the claims cite, and moved the older generations to `kb/archive/`. Measurements and the full old-to-new map are in `kb_audit.md` and `kb_changelog.md`.

Resolved from published sources:

| Claim | Was | Now | Evidence |
|---|---|---|---|
| Channel manager and OTA sync | Confirmed in `archive/website-2026-10-02/modules-reservations.md`, denied in `hotela-feature-availability.md` and `hotela-visitor-faq.md` | Confirmed, and listed as a Hotela Stay and Hotela Suite feature (`kb/bookings.md`) | Features page: "Channel Manager — Sync availability and rates across OTAs and booking platforms, never double-book" |
| 7-day free trial | Stated in `archive/website-2026-10-02/faq.md` and `policies-limits.md`, missing from `hotela-plans-and-subscription.md` | Confirmed for every plan (`kb/policies.md`, `kb/faq.md`) | Pricing page: "Every plan starts with a 7-day free trial" |
| Hotela Suite feature set | `plans.json` said "Everything in Stay & Dine"; two files added "Advanced Analytics" | The `plans.json` wording verbatim (`kb/policies.md`) | Pricing page plan cards match `plans.json` |
| Prices written into prose | Prices appeared in FAQ and policy text as well as `plans.json` | `kb/plans.json` is the only source for plan names, prices, billing period and plan features | Pricing page |
| Duplicate topic files | 21 knowledge files across two generations, 25 near-duplicate pairs | 9 canonical files, one per topic, fields checked by the validator | `python backend/scripts/validate_kb.py` rejects a duplicate or mismatched `topic:` |
| Event features said to be unknown | `modules-restaurant-events.md` said events were not found | Recorded from the Event Management screens (`kb/bookings.md`) | Hotela dashboard |

## Decisions needed

### 1. "Advanced Analytics" as a Hotela Suite feature

- The knowledge base and the system prompt examples once described Hotela Suite as adding "Advanced Analytics". The pricing page lists Suite as "Everything in Stay & Dine, Unified dashboard, Multi-branch & roles, Channel manager, Priority 24/7 support", and `plans.json` matches the pricing page.
- Current default: the label is not used anywhere in the knowledge base. A plan feature that `plans.json` does not list must not be claimed.
- Decision: keep it out, or add it to the pricing page and to `plans.json` so the knowledge base follows automatically.
- Owner: product and marketing.

### 2. Offline mode, desktop apps and "works on every device"

- The features page states "Offline-ready POS & front desk", "Windows & Mac desktop app", "Real-time cloud sync" and "Works on every device"; nothing else in the sources describes them.
- Current default: repeated as website statements in `kb/app_how_to.md`, with the details marked as not published.
- Decision: confirm whether offline POS and the desktop apps are shipping, and if so describe the real limits (which screens work offline, how syncing behaves).
- Owner: product.

### 3. Mobile app

- The website footer shows Google Play and App Store buttons, but they point to `href="#"`, and no store listing is linked. The dashboard has no mobile screens.
- Current default: not confirmed, and the FAQ points the visitor to the Hotela team.
- Decision: is a mobile app shipping, and should the footer buttons link to real listings?
- Owner: product and marketing.

### 4. Channel manager platform names

- The channel manager is confirmed, but no page lists which OTAs and booking platforms are connected.
- Current default: the module is confirmed, the platform names are not.
- Decision: publish the supported platform list so visitors can be answered directly.
- Owner: product.

### 5. Price for a second branch, and the branch limit per plan

- The pricing page states "Prices in PKR, per branch", asks "How many branches does your business have?", offers a selector and says "Pricing is per branch · need more? Contact us after signup". Every plan card also reads "per branch · 1 branch · billed every 6 months".
- It is not published whether the price multiplies per branch, whether bundles are cheaper, or what the per-plan branch limit is, while `plans.json` carries the matching note "1 branch".
- Current default: prices are described as per branch, and larger branch counts are answered by pointing to the Hotela team.
- Decision: confirm the price for two to five branches and the limit per plan, then update `plans.json` billing notes and `kb/rooms_pricing.md`.
- Owner: sales.

### 6. What happens after the 7-day trial

- The website states a 7-day free trial, full access, no charge to begin and cancel anytime. It does not state what happens on day 8 or whether a card is required.
- Current default: the trial length, full access, no charge to begin and cancel anytime are confirmed; everything else is not.
- Decision: publish the post-trial behaviour and whether a payment method is needed to start.
- Owner: product.

### 7. Annual pricing

- The pricing page offers six-month and annual billing but publishes only six-month prices. The evaluation suite contains "Can you provide annual prices?" and expects a handoff.
- Current default: annual billing is mentioned, annual prices are not published.
- Decision: publish annual prices and update `plans.json`, or stop advertising annual billing.
- Owner: sales.

### 8. Refunds and cancellation steps

- The website states customers can cancel anytime, with no refund terms, cancellation steps or post-cancellation access rules.
- Current default: cancel anytime is confirmed; refunds and cancellation steps are not, and the visitor is pointed to the team.
- Decision: publish the refund and cancellation policy.
- Owner: operations and legal.

### 9. Uptime and support service levels

- The website states 99.9% uptime and 24/7 support from real people, with no definition of how uptime is measured, no response times and no service levels.
- Current default: the statements are reported as the website's claims, and the definitions are not confirmed.
- Decision: publish how uptime is measured and what the support targets are, or confirm that these stay as marketing statements.
- Owner: operations.

### 10. Marketing figures

- The website claims "trusted by 2,000+ hospitality teams", "trusted in 15+ cities", a 4.9/5 rating and a "Trusted and loved by hospitality teams" logo wall.
- Current default: recorded as the website's own claims, with a note that they are not product documentation, so the assistant does not repeat them as facts.
- Decision: confirm whether the assistant may quote these figures to visitors.
- Owner: marketing.

### 11. Guest notifications and payments

- No page confirms SMS, WhatsApp or email notifications to guests, a payment gateway, or online payment collection. The pricing page does list "Online orders" for Hotela Dine, which is ordering, not payment.
- Current default: all of these are not confirmed.
- Decision: confirm which notification channels and payment methods are available, then add them to `plans.json` or the canonical files.
- Owner: product.

### 12. WhatsApp as a contact channel

- The website lists email, phone, Facebook, Instagram and LinkedIn. No WhatsApp number or link is published, and the bot's `HANDOFF_WHATSAPP` setting is empty, so the handoff action offers email and phone only.
- Current default: not confirmed.
- Decision: publish a WhatsApp contact if one exists.
- Owner: support.

### 13. Retention of visitor data

- The backend stores every chat message in `data/hotela.db` and no feature reads those tables. Lead records hold name, phone, email and business details.
- Current default: nothing is deleted automatically, and no retention period or privacy notice is published.
- Decision: set a retention period and a privacy statement for the chatbot's own data.
- Owner: operations and legal.

### 14. Evaluation expectations written in English only

- Three evaluation questions answer in Roman Urdu or Urdu script, but their `expected_facts` are English nouns: "Kya multiple branches manage ho sakti hain?" expects `[multiple, properties]` and the Urdu reservations question expects `[reservations]`. A correct Roman Urdu or Urdu answer cannot contain those exact English words, so those questions fail even when the answer is right.
- Two evaluation questions also expected a handoff for features the knowledge base confirms (inventory and events); those two were corrected on 2026-10-15 and now expect facts.
- Decision: either restate those expectations with tokens the correct answer must contain in its own language, or mark them as language checks instead of fact checks.
- Owner: whoever owns the evaluation suite.

### 15. Hotela Stay and Hotela Suite cost the same

- Both plans are listed at PKR 35,000 per branch for six months; Hotela Dine is PKR 20,000. Suite includes everything in Stay and Dine, so the equal price is worth confirming before the assistant states it as intentional.
- Current default: prices are quoted from `plans.json` exactly as published, with no comment on why they match.
- Decision: confirm the Suite price, or publish the difference.
- Owner: sales.

### 16. Evidence behind the dashboard-screen facts

- Facts such as the reservation statuses, the petty-cash totals, the payroll tabs and the stock counters have no published page behind them; they came from reviewing the Hotela dashboard screens.
- Current default: each canonical file names "Hotela dashboard screens" as the source, and the facts are treated as product evidence rather than marketing copy.
- Decision: name the screenshots, demo tenant or seed data that back these claims so a future reviewer can re-check them, and say who confirms a change in the product.
- Owner: product.

### 17. Who refreshes the knowledge base, and when

- The knowledge base is now generated from the website and the dashboard review. Nothing schedules a re-check, so drift (a new plan, a price change, a renamed screen) will silently make answers wrong.
- Current default: manual review, recorded per file in `last_updated`.
- Decision: agree a review cadence and an owner for each canonical file.
- Owner: knowledge base owner.

## Facts still not documented

Recorded here instead of inside the indexed files, so the assistant cannot read maintainer notes into an answer. Add a canonical file entry when the fact is published.

- Founding date and company address for IdeoMetriX.
- The exact fields on the new event form, event packages, menus, venue halls and event booking rules.
- The individual fields and screens behind menu management, order management and table reservations.
- How the Upgrade and Renew flows in the subscription screen behave, and whether an upgrade is prorated.
- Room status types beyond Dirty and Available, room-type limits and maintenance workflows.
- Cancellation, payment and modification rules inside the reservation Manage action.
- Tax configuration, tax invoicing, government integrations, accounting software integrations and report export formats.
- Attendance, leave tracking, payslips, purchase orders, supplier management, customer import and customer segmentation.
- Export or backup of the owner's own data, and data retention periods inside the Hotela product.
