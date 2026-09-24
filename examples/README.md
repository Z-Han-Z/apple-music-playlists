# Curation evaluations

[`curation-evals.json`](curation-evals.json) contains difficult multilingual playlist briefs and
auditable criteria. It is for comparing **workflows**, not declaring one model or one playlist the
winner forever. The cases intentionally contain no expected tracks.

## Run one case

1. Choose a case and keep its `brief`, target count, storefront, and model fixed for both runs.
2. **Baseline:** ask the model for exactly the target count, then catalog-resolve and dry-run that
   list without a larger candidate pool.
3. **Curation workflow:** keep the original brief visible and write a compact curation contract that
   separates must-haves, avoidances, reference-only anchors, soft context, personalization scope,
   narrative beats, and unknowns. Then ask for 1.5–2× the target count, call
   `am_resolve_candidates`, compare the grounded
   candidates in natural language, assign narrative roles, and dry-run the final list.
4. If useful, call `am_analyze_flow`. Use `am_optimize_order` only inside already chosen narrative
   blocks; keep semantic beat boundaries fixed.
5. Listen blind. Do not reveal which workflow produced which sequence until the evaluator has
   answered the case's `blind_questions`.

A public-catalog case needs no Apple Music library write. Use `am_create_playlist` with
`dry_run=true` to verify the final recordings. The personalized Chinese case additionally needs
local recent-play and multi-year Replay evidence; it should not be used when that private evidence
is unavailable.

## Record the result

Keep facts and judgments separate:

```markdown
## Run metadata
- Case:
- Date:
- MCP client and model:
- Storefront:
- Workflow: baseline | curation

## Catalog funnel
- Proposed candidates:
- Resolved exact recordings:
- Unresolved:
- Wrong or unrequested versions:
- Duplicate recordings:
- Artist-concentration warnings:
- Final dry-run matches:

## Intent coverage
- Must-haves satisfied or missed:
- Avoidances respected or violated:
- Reference-only anchors kept as references:
- Soft context or model inferences used:
- Personalization: required | optional | out of scope; evidence actually used:
- Narrative beats preserved:
- Ambiguities and evidence gaps still unresolved:

## Flow evidence
- Audio-feature coverage and missing reasons:
- Adjacency warnings before/after optional local ordering:
- Narrative boundaries held fixed:

## Curation trace
- Opening / development / turn / release / landing roles:
- One natural-language reason for every retained track:
- Retained claims supported only by model inference and still needing listening or lyric verification:
- Set-level coherence: which individually plausible track, if any, weakens the brief's promise:
- Rejected candidates and reasons:

## Blind listening
- Answers to the case's blind questions:
- Preferred sequence and why:
- Where catalog correctness, semantic fit, and physical flow disagreed:
```

Do not collapse those sections into a single number. A perfect dry-run cannot prove the story is
good; a low ordering cost cannot prove the songs belong; human preference does not excuse a wrong
recording. A successful catalog resolution proves identity and availability, not the model's claim
about lyrics, atmosphere, influence, or narrative role. An individually plausible track can still
make the collection less coherent. A fluent, well-grounded curation explanation makes a decision
easier to audit; it does not prove that the selection is better or that the playlist sounds good.
Curation-contract coverage detects forgotten requirements but does not prove musical quality.
Audio-feature coverage must appear beside any flow result because unmeasured positions were not
evaluated.

## Privacy and sharing

- Never commit Apple Music tokens, cookies, `.p8` files, account identifiers, or raw listening
  history.
- Generated playlists and track choices may reveal personal information. Publish them only when
  the listener has deliberately chosen to share them.
- For the personalized case, share aggregate counts and redacted reasoning by default. Keep the
  source exports local.
- Do not build a permanent leaderboard from these cases. Model versions, catalog storefronts, and
  available recordings change; preserve the run date and context instead.

The goal is a reproducible conversation about musical understanding: what the sequence notices,
what each track contributes, where evidence changed a choice, and whether the listening experience
holds together from beginning to end.
