# Hotela bot — improvement report

Branch `kb-reconcile` (baseline: `178bfc3` on `master`, the first commit this repo has ever had). This report covers **pass 1: repository baseline and the knowledge base**. The RAG quality and latency work is the next pass, so this file states no retrieval-quality or latency claims yet — only what was measured.

## 1. What was found before any change

| Finding | Detail |
|---|---|
| Nothing was under version control | `git log` failed: the branch had no commits. No rollback point existed for any of the work. |
| The project virtualenv was dead | `venv/` was created with Python 3.12.10 (`venv/pyvenv.cfg`), which is no longer installed on this machine (only 3.14.2 is). `venv/Scripts/python.exe` fails with `No Python at 'C:\...\Python312\python.exe'`, so no test, validator or index build could run. |
| The knowledge base held two generations of the same topics | 21 knowledge files (8 built from the website on 2026-10-02, 13 from the reviewed pass on 2026-10-09 → 2026-10-15), 25 near-duplicate pairs, and claims answered differently depending on which file was retrieved. |
| Duplication was semantic, not literal | **Zero** byte-identical and **zero** line-ending-normalised duplicates. A hash check alone would have declared the KB clean. Highest similarity pair: 0.39 (`getting-started-and-support` ↔ `support-contact`). |
| Prices lived in prose as well as `plans.json` | Two sources for the same numbers, which is how a bot quotes two prices. |
| The bot read one KB file by path | `backend/app/chat/service.py` read `kb/curated/support-contact.md` directly, so a KB restructure would have broken the contact path silently. |

## 2. Baseline commit and repository footing

- `178bfc3` on `master` commits the workspace as it stood (76 files, 6,157 lines), before any change.
- Secrets verified excluded rather than assumed: `git check-ignore` confirms `backend/.env`, `data/hotela.db`, `backend/chroma_db/*`, `venv/`, `frontend/node_modules/`, `frontend/dist/` are ignored, and a pattern scan of every file that is committed (`AIza…`, `sk-…`, `ghp_…`, private keys, `password=`/`api_key=`) found nothing. `*.tsbuildinfo` was added to `.gitignore` so the TypeScript build cache stays out.
- `.venv/` (Python 3.14.2, gitignored) was created with the FastAPI stack, `chromadb 1.5.9`, `google-genai`, `tiktoken`, `sentence-transformers 6.1.0` and `torch 2.14.1`, so the suite, the validator and the index build run again on this machine.

## 3. The knowledge base now

One canonical file per topic, in `kb/`, each with `title`, `topic`, `source`, `source_urls`, `last_updated`, `version`, `audience` front matter:

| File | Coverage |
|---|---|
| [kb/bookings.md](kb/bookings.md) | Room reservations and statuses, check-in/out, table reservations, event bookings, channel manager/OTA sync |
| [kb/rooms_pricing.md](kb/rooms_pricing.md) | Rooms, bed types, categories, housekeeping, room status, rates, plan pricing and the branch selector |
| [kb/invoices.md](kb/invoices.md) | Hotel, restaurant and food invoices, invoice fields, what is not documented |
| [kb/finances.md](kb/finances.md) | Transactions, cash/bank records, expenses, petty cash, event money, dashboard reporting |
| [kb/customers.md](kb/customers.md) | Customer records, guests at the front desk, where customers appear |
| [kb/policies.md](kb/policies.md) | The three plans, subscription screen, trial, fees, cancellation, security, support, assistant limits |
| [kb/app_how_to.md](kb/app_how_to.md) | Getting started, signup, branches, dashboard, staff/payroll, inventory, contacts, the confirmed/not-confirmed ledger |
| [kb/faq.md](kb/faq.md) | 36 Q&A sections in English, Roman Urdu and Urdu |
| [kb/glossary.md](kb/glossary.md) | One term per concept plus the words visitors use |

Registers and provenance, none of them indexed: [kb/GAPS.md](kb/GAPS.md) (17 human decisions), [kb/plans.json](kb/plans.json) (the only price source), [kb/archive/](kb/archive/README.md) (both old generations), [kb_audit.md](kb_audit.md), [kb_changelog.md](kb_changelog.md).

### Measured before and after

| Metric | Before | After |
|---|---|---|
| Knowledge files | 21 | **9** |
| Files under `kb/` | 24 | 33 (21 archived, kept for provenance) |
| Indexed documents | 14 | **10** |
| Indexed chunks | 71 | **59** (−16.9%) |
| Indexed tokens (tiktoken cl100k_base) | 7,576 | **7,422** (−2.0%) |
| Files with the full front-matter schema | 0 | **9** |
| Exact / normalised duplicates | 0 / 0 | 0 / 0 |
| Near-duplicate pairs ≥ 0.25 (indexed set) | 25 over 21 files | 15 over 9 files |
| Longest identical passage between two indexed files | 26 words | **15 words** (the `plans.json` feature list and the channel-manager sentence, both quoted deliberately) |
| TODO/CONFLICT notes in indexed prose | 0 | 0 |

Chunk and token counts were computed with the same estimator on both layouts (`tiktoken`), because the chunker falls back to a character estimate when `tiktoken` is missing and that alone changes the chunk count: the same final KB yields **59 chunks with `tiktoken` and 61 without it**. Both scripts now print which estimator they used, so a count from a different environment cannot be mistaken for the indexed one.

### Contradictions: 6 resolved, 17 escalated

Resolved (evidence in [kb_audit.md](kb_audit.md), both pages fetched again during this pass, HTTP 200):

1. **Channel manager / OTA sync** — confirmed for Hotela Stay and Hotela Suite; the reviewed files had denied it.
2. **7-day free trial** — confirmed for every plan; one reviewed file had dropped it.
3. **Suite feature set** — the `plans.json` / pricing-page wording verbatim; "Advanced Analytics" removed because no published source lists it.
4. **Plans vs limits** — prices per branch, not per room; six-month billing; plan cards say "1 branch" while the page offers a branch selector; the price for a second branch is *not* published.
5. **Prices in prose** — no price numbers anywhere in Markdown; `plans.json` is the only source.
6. **Event features** — one old file said they were unknown; they are documented from the dashboard screens.

Escalated to a human, all in [kb/GAPS.md](kb/GAPS.md): second-branch price and branch limits, annual prices, "Advanced Analytics"/offline/desktop claims, OTA platform names, post-trial behaviour, refunds and cancellation steps, uptime and support service levels, marketing figures, guest notifications and payments, WhatsApp as a channel, chatbot data retention, the eval expectations written in English, the identical Stay/Suite price, the evidence behind dashboard-derived claims, and the review cadence.

## 4. Code changes

| File | Change |
|---|---|
| [backend/app/rag/chunker.py](backend/app/rag/chunker.py) | `kb_documents()` is now the single definition of the indexed set (top-level `kb/*.md` with the six front-matter keys; subfolders and registers excluded by construction). Front matter parsing handles CRLF. Chunk metadata gained `audience` and `last_updated`. New `section_text()` lets the prompt read one curated section instead of a whole file. |
| [backend/app/rag/index.py](backend/app/rag/index.py) | `kb_version()` hashes exactly the files the index is built from, via `kb_documents()`, so a stale index is detectable. |
| [backend/app/chat/service.py](backend/app/chat/service.py) | The hard-coded `kb/curated/support-contact.md` read is now `section_text(kb/app_how_to.md, "Support and contact")`. Public API unchanged. |
| [backend/scripts/validate_kb.py](backend/scripts/validate_kb.py) | Rewritten: required topic files, `topic` must equal the file name, duplicate topics rejected, front-matter schema and values checked, `plans.json` schema checked, `GAPS.md` must stay unindexable, and any 60-character line repeated across two indexed files fails the check. It also prints the indexed chunk count. |
| [backend/scripts/build_index.py](backend/scripts/build_index.py) | Document count comes from `kb_documents()`. |
| [backend/tests/test_chunker.py](backend/tests/test_chunker.py) | Tests the new layout: the indexed set is exactly the nine topic files, registers and archive are excluded, every indexed file carries the schema, and every chunk carries `topic`/`audience`/`kb_version`. |
| [scripts/kb_audit.py](scripts/kb_audit.py) | New, stdlib-only: hashes, exact duplicates, line-ending-normalised duplicates, near-duplicate similarity, longest shared passage, topic collisions. `--root`, `--threshold`, `--exclude`. |
| [README.md](README.md) | Layout, indexing rule, maintenance rules and the re-index/eval commands updated to `kb/`. |

## 5. Verification actually run

| Check | Command | Result |
|---|---|---|
| Validator | `.venv/Scripts/python.exe backend/scripts/validate_kb.py` | **exit 0** — `Canonical KB files: 9 (9 topics)`, `Indexed chunks: 59 (sized with tiktoken:cl100k_base)`, `TODO 0`, `CONFLICT 0` |
| Backend test suite | `PYTHONPATH=backend .venv/Scripts/python.exe -m pytest backend/tests -q` | **16 passed** in 84.7s |
| Duplicate audit, before | `python scripts/kb_audit.py` | 24 files, 0 exact duplicates, 25 near-duplicate pairs |
| Duplicate audit, after | `python scripts/kb_audit.py --root kb --exclude kb/archive` | 11 files, 0 exact duplicates, 0 topic collisions, 15 vocabulary-level pairs, longest shared passage 15 words |
| Index build (end to end) | `PYTHONPATH=backend python backend/scripts/build_index.py` | **exit 0** — `Documents loaded: 10`, `Built collection: 59 chunks`, `Embeddings generated: 59`, `kb_version: 13517bf5c3e6…`, `Token total: 7422` |
| Retrieval smoke test | 5 contradiction-related questions against the rebuilt collection | Top hit is the correct chunk 5/5, similarity 0.65–0.85 (sanity check, **not** an evaluation) |
| Secret exposure | `git check-ignore` on 7 secret/build paths, then a regex scan of committed files | All ignored, no matches |

**Not run, and why:** the 60-question evaluation suite (`backend/eval/run_eval.py`) needs live Gemini answers, and the provider path is not reliable in this environment yet; its baseline belongs to the next pass. No retrieval-quality (hit rate, MRR, faithfulness) or latency (p50/p95) number is claimed here for the same reason.

## 6. The evaluation instrument and its baseline (pass 2)

### What was built

| Artifact | What it does |
|---|---|
| [backend/eval/questions.yaml](backend/eval/questions.yaml) | **56 questions** drawn from the canonical `kb/` topics: 25 easy, 10 multi-step (two different sections must both be in context), 12 not-confirmed/handoff, 4 Roman Urdu or Urdu, 3 injection or off-topic, 2 greetings. Every question carries the expected answer, the machine-checkable facts and the exact `kb/` section(s) that can answer it. |
| [backend/eval/run_eval.py](backend/eval/run_eval.py) | The runner. Retrieval metrics are computed through the same embedder, collection and `retrieve()` the service uses; generation metrics run through the real `/api/chat` SSE surface. Validation of the set against `kb/` happens before any scoring. |
| [backend/eval/baseline.json](backend/eval/baseline.json) | The recorded baseline the runner gates against, with the KB version, chunk count, estimator, embedding model and retrieval settings so a comparison can never silently mix configurations. |
| [backend/tests/test_eval_set.py](backend/tests/test_eval_set.py) | Keeps the set honest: sources must exist in `kb/`, kinds must cover the taxonomy, handoff/redirect questions must not assert facts, and a non-English question may not require an English-only fact (the fix for the [kb/GAPS.md](kb/GAPS.md) item that made Urdu answers fail English checks). |
| [backend/tests/test_llm_timeout.py](backend/tests/test_llm_timeout.py) | Proves the model call is bounded: a hanging provider raises within the deadline, a timeout is never retried, an SDK-reported timeout is not retried, quota errors short-circuit, and the service falls back to the grounded answer. |

### Baseline for the current pipeline (retrieval half, measured)

| Metric | Baseline | How it behaves |
|---|---|---|
| Questions scored | 50 of 56 | Six have no sources by design (injection, greetings, and one question the KB does not cover) |
| hit@1 | **0.600** | either of the acceptable sections at rank 1 |
| hit@6 (k = `TOP_K`) | **0.860** | 7 misses |
| MRR | **0.729** | misses count as zero, so runs are comparable |
| Multi-step hit@6 | **0.700** | 10 questions needing two sections; 3 miss one of the two |
| IDK context hit@6 | **0.727** | 11 not-confirmed questions; 3 never retrieve the section that documents the gap |
| Retrieval latency | p50 23-52 ms, p95 32-172 ms | local model, warm cache; machine-dependent, so it is reported but not gated |
| Provider-independent | yes | retrieval is measured on the raw question because the LLM rewrite step needs the provider |

### What the baseline already exposes

The seven retrieval misses cluster in one place: **questions whose answer is an exact term rather than a topic**. "Is my data encrypted?", "What is your refund policy?", "Can I import customers?" and "Is there an Urdu interface?" retrieve *nothing* above the similarity threshold, even though `kb/policies.md`, `kb/customers.md` and `kb/app_how_to.md` all document those answers (as facts or as documented gaps). The FAQ's 36 Q&A chunks are strong topic matches and out-rank the section that actually holds the fact. That is the concrete case for the next pass's hybrid BM25 + vector retrieval, and for chunking that keeps the section that holds a fact retrievable on its own.

### Unmeasured, and exactly why

| Metric | Status |
|---|---|
| Answer correctness | **NOT MEASURED** - the Gemini preflight fails with `RuntimeError: Gemini quota is exhausted` (HTTP 429) |
| Faithfulness (facts traceable to context) | **NOT MEASURED** - same preflight failure |
| Unsupported numbers (hallucinated prices) | **NOT MEASURED** - same |
| Handoff correctness | **NOT MEASURED** - same |
| Redirect correctness | **NOT MEASURED** - same |
| Language correctness (Roman Urdu / Urdu) | **NOT MEASURED** - same |
| Request errors / per-question timeouts | **NOT MEASURED** - no generation calls were made |

The runner reports these as `NOT MEASURED` with the reason and still exits 0 on the retrieval half; `--require-generation` turns that into exit 3 for anyone who needs the full gate. A provider must answer for the numbers above to exist.

### Latency and timeout work in this pass

- Every model call now carries an explicit deadline (`LLM_TIMEOUT_SECONDS`, default 20 s): the blocking call runs in a daemon thread that the deadline abandons, and streaming enforces a first-token deadline plus a per-chunk idle deadline. A timeout is **never retried** (previously a timeout would be retried three times), so a request reaches the documented grounded fallback instead of stalling.
- The SDK client is built with the same timeout in milliseconds, so the transport gives up too.
- `GeminiLLMClient.preflight()` gives the evaluator a bounded way to distinguish "the provider is down" from "the answers are bad".
- The eval runner additionally bounds every question (`--question-timeout`, default 90 s) in a daemon thread, so one hung request cannot hang a 56-question run.
- Measured effect on the failure path: with the provider returning 429, a full 56-question run finishes in seconds and reports generation as unmeasured (previously the preflight path alone could sit through three retries per call).

### Prompt correctness found while building the instrument

The generation prompt's style examples still taught two facts the reconciled KB dropped: "Hotela Suite adds Advanced Analytics" and a restaurant feature list that did not match `plans.json`. They are fixed in a separate commit, on the generation side only, and are **not measured** in this pass because no provider answered - retrieval metrics are unaffected by the change.

## 7. Risks

1. **The merge is unproven at retrieval level.** Fewer, bigger topic files could retrieve worse than the old focused ones, even though the KB is cleaner. The evaluation pass decides; the merge is one revert away in `kb/archive/`.
2. **Dashboard-derived facts have no published page** behind them (reservation statuses, payroll tabs, stock counters). They are attributed in each file, and `kb/GAPS.md` item 16 asks for the evidence to be pinned down.
3. **Everything is still manual.** No scheduled re-check, so a price change or a renamed screen silently makes answers wrong.
4. **The archive stays in the repository** (21 files). It is excluded from the index by construction and the validator fails if a knowledge file appears outside `kb/`, but it is still 21 files a maintainer can accidentally copy from.
5. **Environment is rebuilt, not restored**: `.venv` runs Python 3.14 while the app was developed on 3.12. Test suite and index build pass, but this is a different interpreter than the project's original.
6. **Chunk counts depend on `tiktoken` being installed.** With it, the KB indexes as 59 chunks; without it the fallback estimator produces 61. The dependency is declared in `requirements.txt` and both scripts now name the estimator they used.

## 8. Next steps (in order)

1. **Fix the retrieval misses the baseline exposes**: the four exact-term questions and the three multi-step misses are the same failure - the fact is in the KB but not in the retrieved context. Hybrid BM25 + vector retrieval, heading-aware chunk sizes, similarity threshold and MMR tuning, each measured against `backend/eval/baseline.json` with `--no-generation` so the number is provider-independent.
2. **Get generation metrics from a provider**, then keep them: the six unmeasured metrics (correctness, faithfulness, unsupported numbers, handoff, redirect, language) need a working key or a local model; once available, `--require-generation` makes them a hard gate.
3. **Latency profiling**: per-stage p50/p95 over 50+ requests (rewrite, embed, retrieve, LLM first token and total), then parallel retrieval, caching keyed on the KB version, and startup-time model loading. The runner already reports retrieval latency percentiles per run.
4. **Registers as guard rails**: keep `kb/GAPS.md` in sync so "not confirmed" answers stay honest, and add the review cadence owner.

## 9. Commands that reproduce every number here

```bash
python scripts/kb_audit.py                                   # duplicate audit (stdlib only)
python backend/scripts/validate_kb.py                        # KB layout + chunk count
python -m pytest backend/tests -q                            # 28 tests
python backend/eval/run_eval.py --no-generation               # retrieval metrics vs baseline
python backend/eval/run_eval.py --update-baseline             # re-record after an intended change
```
