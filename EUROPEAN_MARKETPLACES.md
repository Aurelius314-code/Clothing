# European marketplace integration research (2026-11-02)

Base: Claude's `feature/tradera` branch. This document is research and implementation guidance, **not evidence of working API access**.

## Source status

| Source | Public buyer/listing API | Proposed approach |
| --- | --- | --- |
| eBay | Official Browse API | Existing production adapter |
| Tradera | Official REST v4 | Existing feature branch; verify live with credentials |
| Grailed | No verified official public listings API | User-provided listing URL; evaluate permitted page reading |
| Sellpy | No documented public developer API found | User-provided listing URL; evaluate permitted page reading |
| Vestiaire Collective | Restricted professional **seller** API | User-provided listing URL; do not assume seller API allows public catalogue search |
| Kleinanzeigen | Restricted partner API, commercial third-party data services | Evaluate authorized provider terms and costs; manual URL import otherwise |
| Vinted | Allowlisted Pro integrations API for seller inventory | Manual URL import; not a public catalogue API |

## Sources

- Vinted official: https://pro-docs.svc.vinted.com/
- Vestiaire seller API: https://seller-api-docs.vestiairecollective.com/
- Vestiaire professional eligibility: https://faq.vestiairecollective.com/hc/en-gb/articles/4408904364561-Professional-seller-Listing-Solutions
- Kleinanzeigen commercial API docs: https://developer.kleinanzeigen.de/docs/listing/api
- Kleinanzeigen third-party provider example (not official): https://api.sh/kleinanzeigen-api
- Sellpy API discovery (no public contract found): https://apis.io/providers/sellpy/
- Grailed search UI: https://www.grailed.com/

## Design requirements before more providers

1. **Unify source identity**: eBay `v1|...`, Tradera `tradera:<id>`, and the earlier generic importer currently use different schemes. Use marketplace-native item IDs where available; use a canonical URL only as a fallback. Provide a migration strategy and avoid duplicate entries.
2. **Separate retrieval and normalization**: Each adapter must return an item ID, canonical URL, title, original currency/price, listing text, ordered full-resolution images, condition, availability, shipping-to-Norway status (or unknown), and retrieval provenance.
3. **Fail closed**: No fabricated prices, shipping costs, descriptions or photo measurements. Report unavailable/blocked/expired distinctly.
4. **Preserve human verification**: A refresh or DeepSeek re-analysis must not overwrite human-verified measurements. AI estimates remain provisional.
5. **Minimize network access**: Prefer official APIs or explicit provider agreements. Do not circumvent login, CAPTCHAs, rate limits, or access controls.
6. **Retain history**: Archive source text, photo references, observation timestamps and original listing IDs, while keeping secrets in local `.env` and avoiding seller identity logs when unnecessary.
7. **Tests**: Fixture-based parser tests per marketplace plus opt-in live smoke tests; do not label mocks as proof of live compatibility.

## Recommended order

1. Validate Tradera live API response, search paging, photos, shipping and auction semantics.
2. Fix Tradera photo selection: prefer the largest rendition **per distinct photo**, not the globally highest rendition that may omit other photos.
3. Add a single generic URL inspection workflow with explicit retrieval capability/status, shared by all sources.
4. Pilot one permitted external source (Grailed or Sellpy) using user-provided URLs before scheduled searches.
5. Evaluate Kleinanzeigen's commercial provider cost/terms before purchasing credits.
6. Leave Vinted and Vestiaire on manual import unless a suitable authorized buyer-facing data route is established.

## Branch policy

Keep `main` unchanged until tests and integration review pass. This research branch intentionally starts from `feature/tradera` and does not merge the divergent `feature/deepeval-measurements` branch.
