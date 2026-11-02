# CODEBASE_REVIEW_SUGGESTIONS.md

**Project:** Vintage Wardrobe Watcher  
**Status:** Proposal for independent review; not an implementation or test report  
**Date:** 2026-11-02  
**Repository:** Aurelius314-code/Clothing  
**Branches reviewed:** `feature/tradera`, `feature/deepeval-measurements`; `main` used as comparison baseline.

## Executive recommendation

Stabilize and consolidate the existing codebase before adding further automated marketplaces. Claude's `feature/tradera` branch is a useful foundation: it implements official Tradera API access, Swedish search terms, result normalization, image and description retrieval, pagination and offline tests. However, the parallel branches overlap and diverge. Avoid merging directly to `main` until data migration, retrieval and measurement behavior have been validated.

This document records recommendations, risks and proposed acceptance criteria for external evaluation. Nothing below should be interpreted as a claim that changes were implemented or live-tested.

## P0 — Correctness and data protection

### 1. Reconcile the development branches
- Compare `feature/tradera` against `feature/deepeval-measurements` and `main` file by file.
- Create a dedicated integration branch; explicitly resolve conflicts in `app.py`, `watcher.py`, `fit.py` and measurement code.
- Preserve functionality introduced independently: Tradera scheduled search and Swedish queries; European manual importer; group priority; search filters; DeepSeek evidence/provenance.
- Do not overwrite changes or merge into `main` without review.

**Acceptance:** Branch reconciliation documented; all previously supported workflows have regression coverage.

### 2. Unify listing identity and deduplication
Current schemes include eBay IDs such as `v1|317521940472|0`, Tradera `tradera:753582030`, and generic manual-import URL hashes.
- Define a single source-aware identity contract with native marketplace IDs where available.
- Canonicalize URLs by removing tracking parameters; distinguish genuine relistings from the same listing.
- Preserve existing SQLite IDs wherever possible, or provide an explicit, tested migration for listings, photos, analysis, measurements, review history and snapshots.
- Never deduplicate merely similar garments from different sellers automatically.

**Acceptance:** Re-importing a known listing does not create duplicates; all existing foreign-key-like associations remain valid.

### 3. Protect local SQLite data
- Introduce versioned, idempotent schema migrations and pre-migration backups.
- Keep the permanent project folder, local database, photographs, `.env`, settings and existing venv intact.
- Test migrations against representative copies of older databases; test repeated migration runs.
- Do not store API keys in source control.

**Acceptance:** Existing listings, reviews and human-verified measurements survive upgrade unchanged.

### 4. Audit the end-to-end measurement and fit pipeline
- Explicitly distinguish measurement **source** (`seller_reported`, `photo_extracted`) from **verification status** (`human_verified`, `unverified`, `uncertain`). Treat these as orthogonal concepts rather than replacing existing DB values without migration.
- Keep provenance: original text or photo URL/index, extracted value, unit, flat/circumference convention, model, timestamp and confidence/evidence notes.
- Never present AI estimates or seller claims as human-verified facts.
- Incomplete or contradictory evidence must not generate a definitive green/red verdict.
- Preserve human-verified measurements when re-fetching or re-analyzing.
- Use independently checked Cordings jacket and Burberry trousers examples as regression fixtures; do not treat model predictions as ground truth.
- Evaluate strict vs lenient photo-evidence behavior using actual labeled cases.

**Acceptance:** Fit verdicts are appropriately gated, and regression fixtures identify incorrect values or measurement types.

## P1 — Tradera reliability

### 5. Preserve the complete image gallery
In `tradera.py`, `photos()` selects images based on a globally highest available format. If different photos have different offered sizes, some photos may be omitted.
- Select the best available rendition **for each distinct photograph** while preserving listing order.
- Avoid duplicates across thumbnail, gallery and detailed-image variants.
- Verify on real sanitized Tradera API responses, including measurement photographs.

**Acceptance:** Mixed-resolution listings retain every distinct photograph, with the best available URL for each.

### 6. Make pricing semantics explicit
- Separate auction current bid, next/minimum bid and buy-now price.
- Do not display a bid as a fixed purchase price.
- Keep original currency; use NOK conversion for comparison only with a dated exchange-rate source.
- Record shipping-to-Norway as known/unknown/unavailable rather than assuming Swedish shipping prices apply.

**Acceptance:** Auction and fixed-price listings are correctly labeled and filtering cannot silently confuse bid and buy-now values.

### 7. Harden API and URL handling
- Validate Tradera URLs by parsed hostname and item-path structure, not substring matching in arbitrary text.
- Standardize HTTP timeouts, 429 handling, retries/backoff, transient errors and expired listings.
- Confirm Tradera REST v4 search parameters, response fields, limits and image shapes against live API results.
- Keep fixture-based tests, but distinguish them from live smoke tests.

**Acceptance:** Errors are actionable and isolated; no silent fabricated data or false success.

## P2 — Shared marketplace architecture

### 8. Introduce a provider interface
Suggested conceptual interface (not mandated exact signature):

```python
class MarketplaceAdapter(Protocol):
    def get_listing(self, listing_id: str) -> Listing: ...
    def search(self, query: SearchQuery) -> list[Listing]: ...
```

- Define a normalized `Listing` containing source, native ID, canonical URL, title, original price/currency, listing text, condition, photos in order, retrieval timestamp, availability and shipping-to-Norway status.
- Expose capability flags (`search`, `get_listing`, `full_images`, `shipping`) per provider; unavailable capabilities must fail explicitly.
- Refactor source-specific branching in `watcher.py` (notably `_analyze_one`) toward adapter dispatch without breaking eBay or Tradera.
- Keep retrieval, normalization, persistence, DeepSeek analysis and UI separate.

**Acceptance:** eBay and Tradera both satisfy the same adapter contract and existing workflows remain functional.

### 9. Consolidate Streamlit inspection
- Replace duplicated eBay-only and European-only inspector flows with one **Inspect Listing** tab.
- Detect marketplace from URL; show supported retrieval capabilities and clear fallbacks.
- Provide a single workflow for viewing seller data/photos, associating a wardrobe target, importing, analyzing and verifying measurements.
- Avoid sending any listing to DeepSeek until the user explicitly initiates analysis or opts into batch processing.
- Show original source links, analysis provenance and uncertainty.

**Acceptance:** One listing inspection workflow works for eBay and Tradera, and manual-only sources display honest capability limits.

## P2 — Search quality and prioritization

### 10. Implement weighted search allocation
Current garment-group priorities influence search order but do not necessarily reserve search capacity.
- Add independently adjustable weights for garment groups.
- Allocate query/result budgets by need and weight; respect enabled targets and existing individual priorities.
- Record when a source/query was last searched; avoid repetitive API usage and duplicate analysis.
- Maintain separate source-specific query terms (e.g. Swedish Tradera terms) while sharing filtering and ranking.

**Acceptance:** Higher group weights result in measurably higher search allocation under a fixed budget, without starving other enabled groups unexpectedly.

### 11. Improve cost and cross-market comparison
- Keep original currencies and distinguish listing price, shipping, fees, taxes and estimated total landed cost.
- Do not infer Norway shipping eligibility from domestic rates.
- Apply filters with explicit currency semantics; avoid applying GBP numeric thresholds directly to SEK/EUR.
- Keep historical price observations and first/last-seen timestamps.

**Acceptance:** Cross-market rankings never silently compare nominal values in different currencies.

## P3 — Additional marketplaces

| Marketplace | Feasibility and recommended approach |
| --- | --- |
| Tradera | Complete and validate the official REST integration first |
| Grailed | No verified public buyer/listing API; investigate permitted public listing retrieval, otherwise manual import |
| Sellpy | No documented public developer API found; investigate permitted listing retrieval, otherwise manual import |
| Vestiaire Collective | Restricted seller-oriented API; do not assume buyer catalogue search access |
| Kleinanzeigen | Evaluate authorized partner/commercial data providers and cost/terms; otherwise manual import |
| Vinted | Pro API is allowlisted and seller-oriented; do not rely on unofficial catalogue endpoints |

Do not circumvent login, CAPTCHAs, rate limits or access restrictions. Implement new automated adapters only after confirming a reliable permitted retrieval path. Add one provider at a time with source-specific tests.

## Testing and release gates

- [ ] Reconciled branches preserve prior features.
- [ ] Database backup and migrations tested on representative older DB copies.
- [ ] Existing eBay search and inspector work.
- [ ] Tradera live item and search responses verified with authorized credentials.
- [ ] Tradera complete mixed-resolution photo galleries retained.
- [ ] Auction price and buy-now price correctly distinguished.
- [ ] Re-imports do not duplicate listings or orphan related data.
- [ ] Human-verified measurements survive refresh and re-analysis.
- [ ] Uncertain or contradictory measurements cannot produce definitive fit verdicts.
- [ ] API errors and rate limits do not crash unrelated searches.
- [ ] Offline tests pass; opt-in live smoke-test results documented.
- [ ] Streamlit starts and the unified inspection UI works.
- [ ] `main` is not changed before explicit approval.

## Suggested sequence

1. **Consolidation:** reconcile branches, define identities and migrations, establish adapter contract.
2. **Measurement reliability:** fix Tradera photo selection, audit evidence and fit gating, add labeled regression tests.
3. **Marketplace expansion:** validate Tradera live, consolidate Streamlit inspection, then pilot Grailed or Sellpy where authorized retrieval is feasible.
4. **Search optimization:** weighted category budgets, currency-safe filtering and historical tracking.

## Questions for independent reviewer

1. What is the safest minimal-diff reconciliation plan across the divergent branches?
2. Are there existing SQLite schema constraints or UI assumptions that make the proposed identity model unsafe?
3. Which concrete failure modes exist in Tradera photo selection, auction pricing and response parsing?
4. Does the current measurement parser actually guarantee that uncertain readings cannot trigger definitive red/green fit results?
5. Which changes should be blocked pending live API fixtures versus handled by offline tests?
6. Are there smaller architectural changes that achieve the same reliability without overengineering?
7. What should be the minimal acceptance suite before merging to `main`?
