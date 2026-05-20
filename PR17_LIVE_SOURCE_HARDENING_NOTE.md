# PR 17 Live Source Reliability Hardening Note

## Summary

After updating live source URLs, the Convergence Monitor live proof improved materially.

## Before hardening

Earlier live runs showed repeated degraded source outcomes including:

- source_network_error:bis
- source_network_error:rba
- source_network_error:ecb
- source_empty:imf

Some runs had only 1–2 sources OK.

## Source changes applied

- BIS source updated to the broader official BIS RSS feed.
- RBA source updated away from the failing rss-cb.xml URL to the current media releases RSS feed.
- ECB was left unchanged for this pass.

## After hardening

Latest live-history shows:

- runs_available: 8
- review_packs_found: 8
- usable_run_count: 8
- rejected_run_count: 0
- accepted_degraded: 8
- latest documents_ingested: 16
- latest documents_classified: 16
- latest sources_ok: 4
- latest source_failure_count: 1
- remaining warning: source_empty:imf

## Verdict

PR 17 source hardening materially improved live reliability.

The MVP Release Candidate status remains valid, with the remaining live-source caveat focused mainly on IMF empty-feed behavior.

## Next Recommendation

Do not add dashboard or new scenarios yet.

Next narrow improvement, if required:

- investigate IMF RSS behavior
- add clearer empty-source accounting
- add configurable timeout
- optionally add fallback source URLs
