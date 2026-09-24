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
| Spotify, *Text2Tracks* (2025) | Generating artist and track names with an off-the-shelf LLM creates an entity-resolution boundary: titles are ambiguous, versions differ, and names are poor descriptions of sound. A fine-tuned generative retriever performed better when its track identifiers encoded collaborative relationships instead of literal names. | The evaluation used offline relevance labels and Spotify-specific training data. It does not show that resolving a generated title proves semantic fit, or that a generic host LLM can reproduce a catalog-trained retriever. |
| Spotify, *Hypothesis-Driven Shelf Generation* (RecSys 2026) | A production pipeline separates a natural-language concept from catalog fulfilment, then runs a distinct set-level alignment stage. Its authors report that plausible individual items can still form an incoherent collection or break the promise made by its title. | The system generates Spotify Home shelves rather than user-authored playlists. Its offline judges were not validated against human agreement, and mixed early online results do not establish a general quality advantage. |
| Penha et al., descriptive reasoning traces (RecSys 2026 workshop) | In a controlled 2 × 2 study, more grounded and interpretable natural-language reasoning traces did not consistently improve conventional offline recommendation effectiveness; adding explicit traces reduced effectiveness under the tested standard SFT and RL setups. | The study used three Amazon product domains and a Qwen3-1.7B backbone, not music or human listening tests. It does not show that explanations are useless; it shows that explanation quality is not a proxy for recommendation quality. |
| Baranes et al., *MusicRecoIntent* (NLP4MusA 2026) | In 2,291 real music requests, 3,935 descriptors were annotated as desired, rejected, or referential. Named artists and works were usually references: 1,613 of 1,870 named-entity annotations were referential. | Extracting a genre, mood, or entity does not determine how the user meant it. A named artist is not automatically a must-include. |
| Hausberger et al., *Read Between the Tracks* (NLP4MusA 2026) | Five LLMs ranked candidates containing user-relevant, intent-relevant, both-relevant, and irrelevant tracks. The larger models ranked the joint user-and-intent set above distractors; examples from the listener's intent-specific history were more useful than an intent label alone. | Results were modest and preliminary. A model ranking a provided 40-track set is not evidence that it can invent a correct catalog entry or produce a satisfying sequence unaided. |
| Buzaev et al., *Learning When to Personalize* (NLP4MusA 2026) | A production system classified 5,000 real requests by whether they called for strong personalization, then varied the contribution of listening-history signals. In a blind study, query-aware personalization beat both always-personalized and non-personalized variants. | The study had 20 users and 254 pairwise judgments, used Russian-language queries and proprietary embeddings, and tested retrieval quality rather than narrative sequencing. It does not supply a universal personalization formula for this project. |
| Ramos et al., natural-language user profiles (ACL 2024) | Editable language profiles can be transparent and scrutable: changing a written preference changes downstream recommendations without rewriting a long interaction history. | The experiments used movies and hotels in a warm-start setting, not music. The paper also warns that inferred profile facts can hallucinate. |
| Kim et al., intent hallucination (ACL 2025) | Across 20,068 multi-condition prompts, omission and misinterpretation increased with query complexity. Constraint decomposition detected failures better than undifferentiated LLM judging. | Their weighted evaluation score is not a theme-fit score and should not become a song-selection objective. It is evidence for an auditable checklist at evaluation time. |
| Epure et al., *Music Recommendation with Large Language Models* (2025; revised 2026, accepted at ACM TORS) | The music-recommendation review argues that retrieval accuracy alone does not answer what makes a good generative recommendation, and identifies hallucination, non-determinism, opaque training data, and evaluation validity as risks. | It is a research review, not a listening study demonstrating that a natural-language workflow produces better playlists. |
| Schweiger et al., playlist coherence in user-curated music playlists (EPJ Data Science 2025) | Analysis of more than 650,000 playlists formalizes coherence as the relation between variation across the whole playlist and variation among nearby tracks. Overall diversity and local transitions are distinct: a playlist can vary across the full arc while moving smoothly between neighbors. | The 11 feature/metadata measures are computational proxies, not direct listener ratings. The authors state that user response to their proposed reordering tools remains to be evaluated; higher measured coherence is not proof of a better listening experience. |
| Jeong et al., *The Comparative Trap* (BlackboxNLP 2025) | In general NLG evaluation, LLM judges in pairwise comparisons were more vulnerable to superficial cues such as verbosity and authoritative tone than pointwise judgments; the proposed hybrid reduces that bias in their tested benchmarks. | This is not a music-preference experiment. It warns against treating an LLM's A/B verdict as ground truth, not against using pairwise reasoning to compare grounded candidate songs. |
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

Third, personalization is part of the request, not a default setting. *Learning When to Personalize*
separated requests that depend on the listener (for example, “my favorites”) from catalog-style or
externally constrained requests. Its dynamic variant won 125 pairwise comparisons, versus 73 for the
always-personalized variant and 37 for the non-personalized retriever, with 19 ties. The sample is too
small and platform-specific to copy its scoring formula, but the failure boundary is useful: history
can make an explicitly personal request less generic, and can also pull a self-contained brief away
from what it actually asks for.

Fourth, catalog fulfilment and collection-level fit are separate decisions. Spotify's 2026
hypothesis-driven shelf work plans a narrow concept in language, retrieves real catalog items, and
then checks whether the items cohere as a set and keep the promise made by the displayed title. The
reported alignment gains use non-overlapping cohorts and unvalidated LLM judges, so they are not a
causal estimate of listener preference. The architectural boundary is still useful here: a track can
be individually plausible and correctly resolved while making the playlist as a whole less legible.

## Design consequence: keep a curation contract beside the original brief

Before proposing tracks, the host model should write a compact, editable contract in the user's
language:

```text
Must        — literal requirements whose failure invalidates the result
Avoid       — scoped exclusions, including unwanted versions and emotional boundaries
References  — artists, works, scenes, or eras used for similarity or contrast; not automatic inclusions
Soft context    — plausible interpretations that may guide choices but are not facts supplied by the user
Personalization — whether history should influence this request, which evidence is relevant, and what must not be inferred
Narrative       — ordered beats, turns, callbacks, and the intended landing
Unknown         — ambiguities or missing evidence that could materially change the selection
```

This is not a JSON API, a hidden feature vector, or a score table. The MCP service does not persist or
evaluate it. It is a readable reasoning aid that the user can correct. The original brief must remain
visible beside it because every extraction step can lose information.

Three rules follow:

1. **Do not promote references into requirements.** “Like *Blonde*, but no Frank Ocean” means use the
   record as a comparison and exclude the artist. It does not mean silently add a Frank Ocean track.
2. **Do not let inferred context overwrite explicit language.** “Music for work” may suggest focus,
   but the model should label that as inference, not claim the user asked for ambient music.
3. **Personalize only when the request calls for it.** “My rediscovered favorites” requires listening
   evidence; a self-contained historical or stylistic brief should not be silently bent toward Replay.
4. **Decompose for coverage, not optimization.** Must/avoid/reference/narrative checks reveal omission;
   they do not combine into a single “quality” or `theme_fit` number.

## Candidate reasoning remains language-first

The evidence supports a retrieval-and-reranking workflow, but this project has a different catalog
boundary from Deezer:

```text
original brief + readable curation contract
    → LLM proposes a deliberately oversized pool
    → am_resolve_candidates grounds exact Apple Music recordings
    → LLM compares candidates inside narrative roles
    → LLM checks set-level coherence against the brief's promise
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

*Text2Tracks* sharpens the catalog boundary. A successfully resolved `Title - Artist` string proves
that a recording exists in the chosen storefront; it does **not** prove that the title describes its
sound, that the model remembered the song correctly, or that the selected edition carries the
claimed lyrical or cultural role. The resolver should therefore expose exact metadata and version
markers, while the curation trace records which retained reasons still rest only on model inference.
Unresolved candidates return to the language comparison as evidence gaps; they are not silently
replaced by the first search result.

Natural-language reasons remain useful because a listener can inspect and challenge them. They are
not a quality metric. Penha et al. found a disconnect between more grounded, interpretable reasoning
traces and conventional offline recommendation effectiveness in the product domains they tested.
Accordingly, this workflow records reasons to expose omissions, unsupported claims, and narrative
decisions; it never treats fluency, detail, or explanation-grounding scores as proof that the songs
belong or that the playlist will sound good.

## Evaluation: let the listener decide whether the playlist works

Music-recommendation evaluation research cautions that retrieval accuracy does not capture the full
quality of a generative recommendation. That supports keeping catalog correctness, intent coverage,
discovery, set-level coherence, and listening preference as distinct observations; it does not
establish that any particular LLM workflow wins. The proposed protocol therefore treats a blind
listening comparison as the evidence about musical experience, while deterministic checks establish
only identity, availability, explicit constraints, duplicates, and measurable flow.

Playlist-coherence research also cautions against equating local smoothness with sameness or quality.
Its operational definition compares variation across the whole sequence with variation among nearby
tracks, so broad musical diversity can coexist with locally intelligible transitions. This supports
reporting whole-playlist variety separately from adjacent-track flow and keeping semantic turns intact.
The study's computational coherence measures and proposed rearrangement were not validated against
listener preference; they are diagnostics, not an objective to maximize.

An LLM judge may help flag a missed constraint or make two curator traces easier to inspect, but its
preference is not a substitute for listening. General NLG research found pairwise LLM judgments can
overweight superficial presentation cues such as verbosity and confidence. For the listening test,
hide curator notes and workflow labels, balance which playlist is heard first, and ask listeners to
record criterion-specific impressions before stating an overall preference. If an LLM judge is also
used, report it separately, randomize and swap presentation order, and do not resolve a human/LLM
disagreement by averaging into a single quality score. The pairwise-evaluator finding is from NLG,
not music, so this is a precaution for the measurement method rather than a claim about musical
judgment.

## Validation protocol

The implementation and evaluation suite test the following hypotheses:

1. The MCP prompt preserves the original brief and asks for the seven-part curation contract.
2. A named reference is not included unless the brief separately requests it.
3. Negative clauses remain attached to the rejected object instead of spreading to the whole mood.
4. The contract explicitly decides whether personalization is required, optional, or out of scope.
5. Candidate reasons distinguish catalog facts, listening evidence, and model inference.
6. Evaluation reports retained claims that still depend only on unverified model inference.
7. Evaluation asks whether individually plausible tracks cohere as a set and fulfil the brief's promise.
8. Evaluation keeps explanation auditability separate from selection and listening quality.
9. Evaluation reports coverage and unresolved ambiguity rather than one synthetic score.

The multilingual evaluation suite includes a reference-heavy brief with explicit exclusions. It has
no golden track list. A valid comparison keeps the model, storefront, and brief fixed, then records
catalog failures, contract coverage, the trace for retained and rejected candidates, and blind
listening judgments.

## Claims this project should not make

- “The model understands the user's taste” — current evidence is task-specific and model-dependent.
- “Natural language is always better than retrieval” — production systems combine both.
- “Listening history reveals intent” — examples can help, but the current request may intentionally
  depart from past behavior.
- “Every request improves with personalization” — query-aware personalization beat both extremes in
  one small platform study; that supports an explicit decision, not a universal setting.
- “Constraint coverage proves the playlist is good” — it proves only that stated requirements were
  not silently lost.
- “A convincing curation trace proves the recommendations are better” — explanations make decisions
  inspectable, but their fluency or grounding is not a proxy for recommendation or listening quality.
- “A resolved catalog record proves semantic fit” — it proves identity and availability; atmosphere,
  lyrics, influence, and narrative role may still be model inference.
- “A lower flow cost proves a better story” — acoustic adjacency and semantic narrative remain
  separate judgments.

## Primary sources

- [Delcluze et al. (2025), *Text2Playlist: Generating Personalized Playlists from Text on Deezer*](https://arxiv.org/abs/2501.05894), industry paper accepted at ECIR 2025; [official Deezer research repository](https://github.com/deezer/text2playlist-ecir2025).
- [Palumbo et al. (2025), *Text2Tracks: Prompt-based Music Recommendation via Generative Retrieval*](https://arxiv.org/abs/2503.24193); [Spotify Research overview](https://research.atspotify.com/2025/4/text2tracks-improving-prompt-based-music-recommendations-with-generative-retrieval/).
- [Petrov et al. (2026), *Hypothesis-Driven Shelf Generation for Personalised Recommendation*](https://research.atspotify.com/2026/9/hypothesis-driven-shelf-generation-for-personalised-recommendation), RecSys 2026.
- [Penha et al. (2026), *The Disconnect Between Better Descriptive Reasoning Trace Quality and Recommendation Effectiveness*](https://arxiv.org/abs/2608.23154), RecSys 2026 GenAIECommerce workshop; [Spotify Research publication](https://research.atspotify.com/publications/the-disconnect-between-better-descriptive-reasoning-trace-quality-and-recommendation-effectiveness).
- [Baranes, Hennequin & Epure (2026), *Beyond Musical Descriptors: Extracting Preference-Bearing Intent in Music Queries*](https://aclanthology.org/2026.nlp4musa-1.4/), NLP4MusA; [dataset repository](https://github.com/deezer/MusicRecoIntent-NLP4MusA26).
- [Hausberger, Jósár & Schedl (2026), *Read Between the Tracks: Exploring LLM-driven Intent-based Music Recommendations*](https://aclanthology.org/2026.nlp4musa-1.7/), NLP4MusA.
- [Buzaev et al. (2026), *Learning When to Personalize: LLM Based Playlist Generation via Query Taxonomy and Classification*](https://aclanthology.org/2026.nlp4musa-1.8/), NLP4MusA.
- [Ramos et al. (2024), *Transparent and Scrutable Recommendations Using Natural Language User Profiles*](https://aclanthology.org/2024.acl-long.753/), ACL.
- [Kim et al. (2025), *Beyond Facts: Evaluating Intent Hallucination in Large Language Models*](https://aclanthology.org/2025.acl-long.349/), ACL.
- [Epure et al. (2025; revised 2026), *Music Recommendation with Large Language Models: Challenges, Opportunities, and Evaluation*](https://arxiv.org/abs/2511.16478), accepted at ACM Transactions on Recommender Systems.
- [Schweiger, Parada-Cabaleiro & Schedl (2025), *The impact of playlist characteristics on coherence in user-curated music playlists*](https://doi.org/10.1140/epjds/s13688-025-00531-3), EPJ Data Science.
- [Jeong et al. (2025), *The Comparative Trap: Pairwise Comparisons Amplify Biased Preferences of LLM Evaluators*](https://aclanthology.org/2025.blackboxnlp-1.5/), BlackboxNLP; general NLG evaluator study, not a music-listening study.
- [Hosey et al. (2019), *Just Give Me What I Want: How People Use and Evaluate Music Search*](https://research.atspotify.com/publications/just-give-me-what-i-want-how-people-use-and-evaluate-music-search/), CHI.
- [Li et al. (2019), *Search Mindsets: Understanding Focused and Non-Focused Information Seeking in Music Search*](https://doi.org/10.1145/3308558.3313627), WWW.

The sequencing and practitioner evidence remains in
[`how-to-build-a-good-playlist.md`](how-to-build-a-good-playlist.md) and
[`playlist-curation-survey.md`](playlist-curation-survey.md). The operational boundary between the
host model and deterministic tools remains in [`evaluation-signals.md`](evaluation-signals.md).
