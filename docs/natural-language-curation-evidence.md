# Evidence for LLM-native playlist curation

> Research update: 2026-09-24. This note records what the available evidence supports, what it does
> not support, and the validation hypotheses that can be tested without turning taste into a scalar.

The useful claim is narrower than “an LLM understands music.” Natural language lets a listener
state references, exclusions, situations, tensions, and narrative changes that a small set of sliders
cannot preserve. An LLM can compare grounded candidates against that language. It can also omit a
condition, mistake a reference for a request, or invent catalog facts. The workflow therefore needs
both linguistic reasoning and deterministic grounding.

## Evidence map

| Evidence | Result relevant to this project | What it does **not** prove |
|---|---|---|
| Deezer, *Text2Playlist* (ECIR 2025) | A production system separates broad intent from ordinary lookup, uses an LLM for query interpretation and final refinement, and grounds retrieval in catalog tags plus personalization. Generated playlists were listened to later in 45% of observed cases versus 27% for manually created playlists. | The report is an industry deployment analysis, not a randomized proof that LLM curation is musically better. Deezer also has expert tags, audio models, collaborative-filtering embeddings, and usage data that this project does not have. |
| Baranes et al., *MusicRecoIntent* (NLP4MusA 2026) | In 2,291 real music requests, 3,935 descriptors were annotated as desired, rejected, or referential. Named artists and works were usually references: 1,613 of 1,870 named-entity annotations were referential. | Extracting a genre, mood, or entity does not determine how the user meant it. A named artist is not automatically a must-include. |
| Hausberger et al., *Read Between the Tracks* (NLP4MusA 2026) | Five LLMs ranked candidates containing user-relevant, intent-relevant, both-relevant, and irrelevant tracks. The larger models ranked the joint user-and-intent set above distractors; examples from the listener's intent-specific history were more useful than an intent label alone. | Results were modest and preliminary. A model ranking a provided 40-track set is not evidence that it can invent a correct catalog entry or produce a satisfying sequence unaided. |
| Ramos et al., natural-language user profiles (ACL 2024) | Editable language profiles can be transparent and scrutable: changing a written preference changes downstream recommendations without rewriting a long interaction history. | The experiments used movies and hotels in a warm-start setting, not music. The paper also warns that inferred profile facts can hallucinate. |
| Kim et al., intent hallucination (ACL 2025) | Across 20,068 multi-condition prompts, omission and misinterpretation increased with query complexity. Constraint decomposition detected failures better than undifferentiated LLM judging. | Their weighted evaluation score is not a theme-fit score and should not become a song-selection objective. It is evidence for an auditable checklist at evaluation time. |
| Spotify music-search studies (CHI/WWW 2019) | Focused lookup and non-focused exploration are different mindsets. People judge music search by both success and effort, and their behavior changes with the mindset. | A catalog search endpoint that works for a known title is not, by itself, a curation system for an exploratory brief. |

Two findings deserve special care.

First, *MusicRecoIntent* found that the tested model matched the annotated preference-bearing role for
89% of the descriptors shared by human and model annotations, but 17% of true references were
misread as positive preferences. The failure is concrete: “songs like X” can become “include X.”
A named artist can be a reference, not an automatic request to include that artist.
Strong negation with an overall positive goal was also difficult, such as disliking most of a genre
while asking for an entry point into it.

Second, *Read Between the Tracks* does not say an intent name is enough. In that experiment, a few
tracks heard in the relevant situation helped more than the label alone; for one model the reported
NDCG@10 was about 0.37 with implicit listening examples versus 0.29 with the explicit label. That
supports using recent plays or Replay evidence as examples, while keeping the user's present words in
control. It does not justify converting play counts into taste weights.

## Design consequence: keep a curation contract beside the original brief

Before proposing tracks, the host model should write a compact, editable contract in the user's
language:

```text
Must        — literal requirements whose failure invalidates the result
Avoid       — scoped exclusions, including unwanted versions and emotional boundaries
References  — artists, works, scenes, or eras used for similarity or contrast; not automatic inclusions
Soft context — plausible interpretations that may guide choices but are not facts supplied by the user
Narrative   — ordered beats, turns, callbacks, and the intended landing
Unknown     — ambiguities or missing evidence that could materially change the selection
```

This is not a JSON API, a hidden feature vector, or a score table. The MCP service does not persist or
evaluate it. It is a readable reasoning aid that the user can correct. The original brief must remain
visible beside it because every extraction step can lose information.

Three rules follow:

1. **Do not promote references into requirements.** “Like *Blonde*, but no Frank Ocean” means use the
   record as a comparison and exclude the artist. It does not mean silently add a Frank Ocean track.
2. **Do not let inferred context overwrite explicit language.** “Music for work” may suggest focus,
   but the model should label that as inference, not claim the user asked for ambient music.
3. **Decompose for coverage, not optimization.** Must/avoid/reference/narrative checks reveal omission;
   they do not combine into a single “quality” or `theme_fit` number.

## Candidate reasoning remains language-first

The evidence supports a retrieval-and-reranking workflow, but this project has a different catalog
boundary from Deezer:

```text
original brief + readable curation contract
    → LLM proposes a deliberately oversized pool
    → am_resolve_candidates grounds exact Apple Music recordings
    → LLM compares candidates inside narrative roles
    → dry-run exposes catalog and version mistakes
    → optional local flow checks stay inside semantic boundaries
```

Each retained song should have a short reason tied to the original brief or listening evidence. The
reason should make its epistemic status visible:

- **catalog fact** — title, artist, album, date, ISRC, duration, or an explicit version marker returned
  by the service;
- **listening evidence** — a dated recent play or Replay occurrence;
- **model inference** — lyrical meaning, cultural relationship, atmosphere, or narrative role that
  still needs human judgment.

This separation prevents a fluent explanation from masquerading as verified metadata.

## Validation protocol

The implementation and evaluation suite test the following hypotheses:

1. The MCP prompt preserves the original brief and asks for the six-part curation contract.
2. A named reference is not included unless the brief separately requests it.
3. Negative clauses remain attached to the rejected object instead of spreading to the whole mood.
4. Candidate reasons distinguish catalog facts, listening evidence, and model inference.
5. Evaluation reports coverage and unresolved ambiguity rather than one synthetic score.

The multilingual evaluation suite includes a reference-heavy brief with explicit exclusions. It has
no golden track list. A valid comparison keeps the model, storefront, and brief fixed, then records
catalog failures, contract coverage, the trace for retained and rejected candidates, and blind
listening judgments.

## Claims this project should not make

- “The model understands the user's taste” — current evidence is task-specific and model-dependent.
- “Natural language is always better than retrieval” — production systems combine both.
- “Listening history reveals intent” — examples can help, but the current request may intentionally
  depart from past behavior.
- “Constraint coverage proves the playlist is good” — it proves only that stated requirements were
  not silently lost.
- “A lower flow cost proves a better story” — acoustic adjacency and semantic narrative remain
  separate judgments.

## Primary sources

- [Delcluze et al. (2025), *Text2Playlist: Generating Personalized Playlists from Text on Deezer*](https://arxiv.org/abs/2501.05894), industry paper accepted at ECIR 2025; [official Deezer research repository](https://github.com/deezer/text2playlist-ecir2025).
- [Baranes, Hennequin & Epure (2026), *Beyond Musical Descriptors: Extracting Preference-Bearing Intent in Music Queries*](https://aclanthology.org/2026.nlp4musa-1.4/), NLP4MusA; [dataset repository](https://github.com/deezer/MusicRecoIntent-NLP4MusA26).
- [Hausberger, Jósár & Schedl (2026), *Read Between the Tracks: Exploring LLM-driven Intent-based Music Recommendations*](https://aclanthology.org/2026.nlp4musa-1.7/), NLP4MusA.
- [Ramos et al. (2024), *Transparent and Scrutable Recommendations Using Natural Language User Profiles*](https://aclanthology.org/2024.acl-long.753/), ACL.
- [Kim et al. (2025), *Beyond Facts: Evaluating Intent Hallucination in Large Language Models*](https://aclanthology.org/2025.acl-long.349/), ACL.
- [Hosey et al. (2019), *Just Give Me What I Want: How People Use and Evaluate Music Search*](https://research.atspotify.com/publications/just-give-me-what-i-want-how-people-use-and-evaluate-music-search/), CHI.
- [Li et al. (2019), *Search Mindsets: Understanding Focused and Non-Focused Information Seeking in Music Search*](https://doi.org/10.1145/3308558.3313627), WWW.

The sequencing and practitioner evidence remains in
[`how-to-build-a-good-playlist.md`](how-to-build-a-good-playlist.md) and
[`playlist-curation-survey.md`](playlist-curation-survey.md). The operational boundary between the
host model and deterministic tools remains in [`evaluation-signals.md`](evaluation-signals.md).
