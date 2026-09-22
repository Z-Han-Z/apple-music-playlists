# Algorithm review boundary

This document is the review baseline for early heuristic code. The question is not whether an
algorithm is sophisticated; it is whether its responsibility belongs in deterministic code.

## Decision rule

| Responsibility | Owner | Rule |
|---|---|---|
| Interpret a scene, emotion, memory, theme, or “sounds like” description | Host LLM | Compare tracks directly with the user's words; do not replace this with a hidden numeric theme score |
| Decide which songs belong and explain their narrative roles | Host LLM | Use `essential / strong / bridge / optional / reject` or equivalent language-level reasoning |
| Collect listening history and normalize incompatible API payloads | Service code | Preserve provenance, dates, ranks, and counts; do not turn them into aesthetic verdicts |
| Resolve catalog identities, versions, duplicates, and storefront availability | Service code | Objective grounding is deterministic and should remain centralized |
| Report medians, ranges, coverage, and transitions | Service code | Reports are evidence, not definitions of taste or quality |
| Enforce physical adjacency constraints after selection | Optional service code | BPM, key, loudness, and related transition checks may assist ordering but never determine membership |
| Choose a narrative arc | User or host LLM | An explicit qualitative choice is valid; a silent default should not impose a story |

## First reviewed component: `build_pool.py`

The old implementation mixed two distinct jobs. Reading Replay play counts was useful evidence;
expanding favourite artists and equal-step sampling “variety filler” were semantic selection rules.
The latter could not know whether the user wanted nostalgia, rediscovery, continuity, contrast, or
something else.

`build_pool.py` therefore remains, but with a narrower contract:

1. fetch recent tracks and one or more explicit Replay years;
2. merge duplicate catalog identities without losing per-period facts;
3. retain `recent_rank`, period rank, play count, `first_played`, and `last_played`;
4. enrich objective catalog metadata; and
5. write a listening-evidence document for the host LLM.

It does **not** expand artists, inject diversity, fetch audio features as a prerequisite, label a
track “old favourite”, or emit a recommendation score. “Recent” and “old” are conclusions the LLM
draws from the evidence in the context of the user's actual request.

## Remaining review queue

- `profile_library.py`: retain descriptive statistics, with sample-relative labels and no claim
  that the report defines the user's taste.
- `am_optimize_order`: retain an explicitly requested narrative arc and deterministic adjacency
  assistance; review the current implicit default so omitted `arc` can mean adjacency-only.
- playlist audits: keep measurable diagnostics and coverage reporting, while ensuring thresholds
  remain warnings rather than universal aesthetic laws.

Behavioural changes from this queue should be made separately and tested against real playlist
briefs. Published release tags are not rewritten.
