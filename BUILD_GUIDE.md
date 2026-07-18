# AI Study Kit Engine — 4-Week Build Guide

> Companion to `AI_Engine_Manual.md` and the Scaling Roadmap docx. This is a working document — after each day, fill in the **Reflection** block with what actually happened, what surprised you, and what you'd explain differently in an interview. That daily record is the real deliverable of this process, not just the code.

**How to use this doc:** work top to bottom, one day at a time. Each entry has a goal, the reasoning behind it, the user story and acceptance criteria it satisfies, the files you'll touch, and a definition of done. Don't start day N+1 until day N's definition of done is met — if it isn't, that's fine, just note why in the reflection and adjust the next day's scope rather than pushing forward broken.

**Reference — the decisions everything below builds from:**
- Problem: study kits from long-form material (whole textbooks/transcripts), too long for one context window, generated with citations and a verified-correct quiz, in a per-user library that persists across sessions.
- Stack: FastAPI + Postgres (existing) + pgvector (new), Groq for generation, self-hosted sentence-transformers for embeddings, ARQ + Redis for background jobs, Supabase for Auth + Storage, pdfplumber + Tesseract OCR for ingestion, DeepEval for the test/eval harness, React/Vite/Tailwind frontend (existing, extended).
- Demo corpus: OpenStax *Psychology 2e* (CC BY-NC-SA), benchmarked where possible against the OpenStaxQA dataset.
- Non-goals for v1: multi-user sharing, mobile app, non-text sources, fine-tuning, billing, spaced repetition, adaptive difficulty, analytics dashboard, multi-provider LLM fallback — all explicitly deferred to milestone 2/3.

---

## Week 1 — Fix the foundation, stand up the stack, get documents in

### Day 1 — Phase 0: fix what's already broken
**Goal:** clear every item flagged in the original scaling roadmap's Phase 0 before adding anything new on top of a shaky base.
**Why:** building RAG/auth/export on top of an undiagnosed routing bug and a deprecated model just multiplies the surface area you'll have to debug later. Cheapest to fix now.
**User story:** *As the developer, I want the existing engine to be correct and on a supported model, so that new work isn't built on broken foundations.*
**Acceptance criteria:**
- Model migrated off `llama-3.3-70b-versatile` to `openai/gpt-oss-120b`, read from an environment variable, not hardcoded in three files.
- `SPECIALIST_NODES` routing bug fixed (no more substring collisions between "summarize" and "generate").
- `docker-compose.yml` Postgres password consistent between service definition and app connection string.
- `RunResponse` returns `total_tokens`/`total_time_ms` (fixes the "NaN ms" bug).
- `frontend/src/components/SubmitRun.jsx` reads `VITE_API_URL` from env, not hardcoded.
- Stale `.claude/worktrees/` checkout deleted; working tree committed or intentionally stashed.
**Files touched:** `engine/intent_parser.py`, `engine/llm_nodes.py`, `main.py`, `docker-compose.yml`, `api.py`, `frontend/src/components/SubmitRun.jsx`.
**Definition of done:** `docker-compose up` runs clean from a fresh volume, a POST `/run` returns real token/timing numbers, `git status` is clean.
**Reflection:**
> All five code acceptance criteria confirmed met. Model now reads from `LLM_MODEL` env var via `engine/config.py` (default `openai/gpt-oss-120b`) — no hardcoded strings remain in any file. Routing bug fixed: replaced the substring `in` check with an exact-name dict (`SPECIALIST_NODES`) plus a prefix-matching pass (`SPECIALIST_PREFIXES`) — `generate_quiz` and `generate_flashcards` can no longer collide. `docker-compose.yml` removed the hardcoded Postgres password and uses `${POSTGRES_PASSWORD}` throughout. `RunResponse` now carries `total_tokens` and `total_time_ms`; `NodeResult` tracks `input_tokens`, `output_tokens`, and `execution_time_ms`; `ExecutionEngine.run()` returns a `StepTrace` list alongside final state. `SubmitRun.jsx` reads `import.meta.env.VITE_API_URL` with an explicit error thrown when unset. Key interview insight: substring routing is structurally unsafe because any step name that contains a keyword anywhere (prefix, suffix, mid-word) can hit the wrong specialist; the fix is a lookup table with explicit aliases, not a smarter regex.

### Day 2 — Stack setup: pgvector, Redis, embeddings, test scaffolding
**Goal:** get every new infrastructure piece running locally before writing feature code against it.
**Why:** discovering a dependency doesn't install cleanly on day 9 costs more than finding out on day 2 with nothing riding on it yet.
**User story:** *As the developer, I want all new infrastructure dependencies running locally, so that feature work isn't blocked on environment setup later.*
**Acceptance criteria:**
- `pgvector` extension enabled on the existing Postgres service (or a new dedicated service — decide and document which).
- `redis` service added to `docker-compose.yml`, ARQ installed and a trivial worker/task confirmed running end-to-end.
- `sentence-transformers` installed, a small script embeds a test string locally with no external API call.
- `pytest` scaffolding in `tests/` with a mocked Groq client fixture (per the Phase 1 plan) — this is what keeps you inside Groq's daily rate limit for the rest of the build.
**Files touched:** `docker-compose.yml`, `requirements.txt`, `tests/conftest.py`, new `engine/embeddings.py`.
**Definition of done:** `docker-compose up` brings up app + db (with pgvector) + redis; `pytest` runs and passes against mocked Groq calls, zero live API calls made.
**Reflection:**
> Decision: used the existing Postgres service, just swapped `postgres:16` for `pgvector/pgvector:pg16` — no dedicated service. This keeps docker-compose simpler; if pgvector and the app ever need to be on different hardware, splitting is cheap later. Added a `worker` service alongside `app` so ARQ tasks run in their own container without competing with FastAPI for CPU. `engine/embeddings.py` uses `all-MiniLM-L6-v2` via sentence-transformers — 22 MB, runs entirely on-device, no API key. `engine/jobs.py` has a trivial `ping` task to confirm ARQ is wired end-to-end before Day 5 adds real ingestion jobs. `tests/conftest.py` provides `mock_groq` by patching both `engine.intent_parser.get_client` and `engine.llm_nodes.get_client` — the lazy-init pattern (global client initialised on first call) means patching the factory function is the right intercept point, not the class itself. All 8 tests pass, zero live API calls. Key interview point: mocking at the factory function level rather than patching `groq.Groq` directly means the mock works regardless of how many modules import the client.

### Day 3 — Document upload + text extraction + OCR trigger
**Goal:** accept a PDF or text upload and reliably get text out of it, including scanned pages.
**Why:** "whole textbooks" as the document scale means scanned pages are common, not an edge case — this needs to be solved before chunking, not bolted on after.
**User story:** *As a user, I want to upload a PDF or text document, so that the system can turn it into a study kit even if some pages are scanned images.*
**Acceptance criteria:**
- Upload endpoint accepts PDF/text, rejects unsupported types with a clear error (not a silent failure).
- Per-file size cap enforced (25MB) with an explicit error message when exceeded.
- Text extraction via `pdfplumber`; when extracted text for a page falls below a length threshold, automatically fall back to Tesseract OCR for that page.
- Extraction failures (corrupt file, fully unreadable) return a clear error state, not a hang or silent empty result.
**Files touched:** new `engine/ingestion.py`, `api.py` (new `/documents` upload route).
**Definition of done:** uploading a normal OpenStax chapter PDF and a deliberately scanned/image-only page both produce usable extracted text; an oversized or corrupt file produces a clear error, not a crash.
**Reflection:**
> `engine/ingestion.py` is the single entry point: one `ingest(data, filename, content_type)` function that validates type and size first, then delegates to `_extract_pdf` or `_extract_text_file`. Pdfplumber handles text-layer PDFs; any page whose extracted text falls under 100 characters is attempted with Tesseract OCR — and if Tesseract isn't installed (common on Windows), the page goes into `ocr_skipped_pages` rather than crashing. Two exception types keep the mapping clean: `IngestionError` (4xx — bad type, oversized, empty) vs `ExtractionError` (422 — valid file, unreadable). The `/documents` POST endpoint maps these to HTTP 415/413/422 respectively. The tricky path-priority bug: when pytest ran from the main repo root, Python found the main `engine/` package first on `sys.path`, which lacked `ingestion.py` — fixed by inserting the worktree root at `sys.path[0]` in `tests/conftest.py`. All 17 tests pass. Key interview point: separating validation errors (IngestionError) from extraction errors (ExtractionError) makes the API contract explicit — clients know whether to show "wrong file type" vs. "file unreadable" without parsing error strings.

### Day 4 — Chunking + embeddings + pgvector storage
**Goal:** turn extracted text into retrievable, embedded chunks.
**Why:** this is the layer that makes "whole textbook" input actually usable — everything downstream (retrieval, citations) depends on chunk boundaries being sane.
**User story:** *As the system, I want long documents split into embedded, retrievable chunks, so that generation steps can pull only the relevant material instead of requiring the whole document in context.*
**Acceptance criteria:**
- Chunking at ~600 tokens with ~15% overlap (default — tune against Psychology 2e once you see real output).
- Each chunk stores: source document ID, page/section reference (for citations later), embedding vector, owning user ID.
- Duplicate uploads (same content hash) are deduped rather than re-chunked and re-embedded.
**Files touched:** `engine/chunking.py`, `engine/database.py` (new `DocumentChunk` model + pgvector column), `engine/embeddings.py`.
**Definition of done:** ingesting one OpenStax chapter produces a sane number of chunks in Postgres, each with a non-null embedding and a traceable source reference; re-uploading the same file doesn't duplicate them.
**Reflection:**
> `engine/chunking.py` uses a char-based sliding window (~2400 chars = 600 tokens * 4 chars/token) over sentence boundaries, sliding forward by (window - overlap) each step. One tricky bug: when text is shorter than the overlap, `advance` would compute as `max(1, negative)` = 1, causing the loop to crawl through the text character by character producing hundreds of near-identical chunks. Fixed with a single `if end >= len(text): break` guard. Deduplication lives in two places: `Document` dedupes by SHA-256 of the raw bytes (same file uploaded twice returns the existing row immediately, no re-embedding); `DocumentChunk` dedupes by SHA-256 of chunk text (protects against partial re-ingestion of overlapping documents). The pgvector column uses a conditional import so the server still starts cleanly even if the pgvector Python package isn't installed — it falls back to `Text` (stored as JSON string), which is ugly but not crashy. `init_db()` now runs `CREATE EXTENSION IF NOT EXISTS vector` before `create_all` so the vector column type is available. 26 tests pass. Key interview point: char-based chunking with a fixed chars-per-token ratio is fast and dependency-free; token-exact splitting (via tiktoken) adds precision but also a hard dependency and measurably slower throughput — worth profiling before switching.

### Day 5 — Background ingestion pipeline end-to-end
**Goal:** wire upload → extract → chunk → embed → store as a single ARQ background job with visible status.
**Why:** embedding a full chapter isn't instant; this can't block the HTTP request, and the user needs to see "processing" rather than a frozen screen.
**User story:** *As a user, I want to see my document's ingestion status (processing/ready/failed), so that I know when it's usable and don't think the app is broken.*
**Acceptance criteria:**
- Upload endpoint enqueues an ARQ job and returns immediately with a document ID and `processing` status.
- Status field updates to `ready` or `failed` (with an error reason) once the job completes.
- A status-check endpoint (or the existing library list) reflects current state.
**Files touched:** new `engine/jobs.py` (ARQ worker), `api.py`, `engine/database.py`.
**Definition of done:** upload a document, poll its status, watch it move `processing → ready`; deliberately break extraction (corrupt file) and confirm it lands on `failed` with a real error message, not stuck on `processing`.
**Reflection:**
>

---

## Week 2 — The core loop: retrieval-aware planning, generation with citations, verification

### Day 6 — Dynamic node registry
**Goal:** replace the hardcoded `SPECIALIST_NODES` keyword-matching dict with a real registry the planner can query.
**Why:** you can't add retrieval, citation, or verification as first-class step types on top of a substring-matching hack — this was already flagged as a real bug, and it's now a blocker, not a nice-to-have.
**User story:** *As the Intent Parser, I want to know exactly which node types are available and what each one does, so that I plan steps the system can actually execute instead of guessing keywords.*
**Acceptance criteria:**
- Registry is data (a list of available node types + descriptions), not a hardcoded if/substring chain.
- Existing three specialists (summarize/extract/quiz) still work through the new registry — this is a refactor, not a rewrite of behavior yet.
- The old routing bug (from Day 1) is structurally impossible now, not just patched.
**Files touched:** `engine/llm_nodes.py`, `engine/registry.py` (new).
**Definition of done:** the existing test suite (Day 2) still passes, and the routing decision for a given step name is traceable/inspectable, not implicit.
**Reflection:**
>

### Day 7 — Retrieval-aware Intent Parser
**Goal:** the planner needs to know retrieval is a step type, and what scope (one document, several, or full library) a request applies to.
**Why:** this is the actual mechanism that makes multi-document/whole-library requests work instead of assuming everything fits in context.
**User story:** *As a user, I want to ask a question about one document, a few, or my whole library, and have the system plan a sensible sequence of steps for that scope.*
**Acceptance criteria:**
- `parse_intent()` accepts a scope parameter and available-node metadata from the Day 6 registry.
- Plans generated for a single-document request vs. a whole-library request are visibly different (the library case includes a retrieval step scoped appropriately).
- Requests exceeding a reasonable scope (per open question #2) get a clear "too broad, narrow it" response rather than silently truncating.
**Files touched:** `engine/intent_parser.py`, `engine/schemas.py` (extend `WorkflowPlan`/`WorkflowStep` if needed).
**Definition of done:** three test requests — single doc, multi-doc, whole library — produce three distinguishable, sensible plans.
**Reflection:**
>

### Day 8 — Retrieval node
**Goal:** given a plan step needing source content, pull the top-N relevant chunks from pgvector instead of the whole document.
**Why:** this is where "long document" actually stops being a problem — the model only ever sees relevant chunks.
**User story:** *As the execution engine, I want a retrieval step that returns only the relevant chunks for the current request, so that generation stays accurate and within context limits.*
**Acceptance criteria:**
- Retrieval node embeds the query, does a similarity search scoped to the correct document(s)/user, returns top-N chunks with their source references.
- Retrieved chunks are what downstream generation nodes consume — not the raw document.
**Files touched:** `engine/retrieval_node.py` (new), `engine/execution_engine.py` (state now carries retrieved chunks, not raw text).
**Definition of done:** a query against the ingested Psychology 2e chapter returns chunks that are actually relevant to the query, verified by eye against 5–10 manual test queries.
**Reflection:**
>

### Day 9 — Generation with citations
**Goal:** every generated summary/flashcard/quiz item carries a citation back to the chunk/document/section it came from.
**Why:** this is the actual differentiator from a plain summarizer — non-negotiable, not a stretch goal.
**User story:** *As a user, I want every generated study item to show me exactly where it came from, so that I can verify it against the source instead of trusting it blindly.*
**Acceptance criteria:**
- Generation nodes (summary, flashcard, quiz) receive retrieved chunks with metadata and are prompted to cite the source chunk/section for each generated item.
- Output structure includes citation data per item, not just as prose ("according to the text...") — needs to be structured enough for the frontend to link back to source later.
**Files touched:** `engine/llm_nodes.py` (extend specialist nodes), `engine/schemas.py`.
**Definition of done:** a generated quiz question has a citation field pointing at a real chunk ID/section, and spot-checking that chunk against the question confirms it's actually the source.
**Reflection:**
>

### Day 10 — Verification (LLM-as-judge)
**Goal:** every quiz item and its marked-correct answer gets checked by a second pass before being returned.
**Why:** this is what makes "verified accuracy" a real claim instead of a marketing phrase — and it's the load-bearing feature for the DeepEval benchmarking work in week 4.
**User story:** *As a user, I want quiz answers to be checked for correctness before I see them, so that I'm not studying from a wrong "correct" answer.*
**Acceptance criteria:**
- A verification node re-checks each quiz item's marked answer against the cited source chunk.
- Failing items get regenerated once; if still failing, flagged in the output rather than silently shown as correct or silently dropped (per open question #3 default).
**Files touched:** `engine/verification_node.py` (new).
**Definition of done:** deliberately inject a wrong "correct" answer into a test case and confirm the verification step catches it and flags/regenerates rather than passing it through.
**Reflection:**
>

---

## Week 3 — Auth, library, quiz-taking, OCR hardening, search

### Day 11 — Supabase Auth integration
**Goal:** every request is tied to an authenticated user.
**Why:** the per-user library, quotas, and quiz history all depend on knowing who's asking — this has to land before those features, not alongside them.
**User story:** *As a user, I want to sign up and log in, so that my documents and study history are private to me.*
**Acceptance criteria:**
- Supabase Auth wired in; existing endpoints require a valid session and scope all queries to the authenticated user.
- Unauthenticated requests get a clear 401, not a confusing error.
**Files touched:** `api.py` (auth dependency), new `engine/auth.py`, `frontend/src` (login/signup screens).
**Definition of done:** two different test accounts see only their own documents/runs, never each other's.
**Reflection:**
>

### Day 12 — Personal library + quota enforcement
**Goal:** a real library: list, status, scope selection, quota limits.
**Why:** this is the feature that makes "per-user library in v1" true rather than aspirational.
**User story:** *As a user, I want to see all my uploaded documents and choose which ones a new request should use, so that I control the scope of each study kit.*
**Acceptance criteria:**
- Library list endpoint returns documents with status, upload date, size.
- Per-user cap enforced: 25MB/file, 10 documents — clear quota error when exceeded, not a silent failure.
- New request flow lets the user pick scope: one document, a subset, or "my whole library" (default: just the new upload, per open question #8).
**Files touched:** `api.py`, `engine/database.py`, `frontend/src/components` (library view).
**Definition of done:** hitting the document cap produces a clear, user-visible error; scope selection visibly changes which chunks get retrieved (traceable back to Day 8).
**Reflection:**
>

### Day 13 — Interactive quiz-taking + score capture
**Goal:** a user can actually take a generated quiz, not just read it.
**Why:** flagged in the feature-scope discussion as a real gap — quizzes were being generated but never actually taken in-product. This also lays the groundwork for milestone-2 adaptive difficulty/spaced repetition, even though those stay deferred.
**User story:** *As a user, I want to answer quiz questions in the app and see my score, so that the study kit is actually usable for studying, not just readable.*
**Acceptance criteria:**
- Quiz-taking UI presents one question at a time, grades immediately per-question (per open question #13 default).
- Scores persisted per user, per quiz, per question — this is the data model milestone 2 will read from later.
**Files touched:** `engine/database.py` (new `QuizAttempt` model), `api.py`, `frontend/src/components` (quiz-taking view).
**Definition of done:** taking a generated quiz end-to-end produces a stored score record you can query directly from Postgres.
**Reflection:**
>

### Day 14 — OCR hardening
**Goal:** confirm the Day 3 OCR fallback actually holds up against real scanned OpenStax pages, not just a synthetic test case.
**Why:** this was promoted into v1 specifically because "whole textbooks" implies scanned pages are common — worth a dedicated day to stress-test rather than trusting the Day 3 happy-path test.
**User story:** *As a user uploading a scanned textbook page, I want the system to still extract usable text, so that my study kit isn't missing content silently.*
**Acceptance criteria:**
- Test against several real scanned pages (not just one synthetic example) — vary image quality/orientation if possible.
- Confirm OCR'd text still flows correctly through chunking/embedding from Day 4.
**Files touched:** `engine/ingestion.py` (likely fixes, not new features).
**Definition of done:** a genuinely scanned OpenStax page produces chunked, embedded, retrievable text indistinguishable in downstream behavior from a text-layer page.
**Reflection:**
>

### Day 15 — Semantic library search + difficulty parameter
**Goal:** two small, high-value additions that ride on infrastructure already built.
**Why:** both were explicitly promoted into v1 because they're nearly free once retrieval (Day 8) and generation (Day 9) exist.
**User story:** *As a user, I want to search across everything I've uploaded, and choose a difficulty level for a quiz, so that I can find material quickly and control quiz difficulty without needing a history-based system yet.*
**Acceptance criteria:**
- Search endpoint takes a free-text query, embeds it, returns matching chunks across the user's whole library with source references.
- Quiz generation accepts a difficulty parameter (easy/medium/hard), reflected in prompt construction — static, not adaptive (adaptive stays milestone 2).
**Files touched:** `api.py` (new `/search` route), `engine/llm_nodes.py` (difficulty parameter on quiz generation).
**Definition of done:** a search query returns relevant chunks from documents you didn't explicitly select; a "hard" quiz is visibly more difficult than an "easy" one on the same source material.
**Reflection:**
>

---

## Week 4 — Export, frontend, evaluation, polish

### Day 16 — PDF export
**Goal:** export a generated study kit as a PDF.
**Why:** self-contained, low-risk, doesn't touch the core pipeline — good use of a day once the hard engineering is done.
**User story:** *As a user, I want to download my study kit as a PDF, so that I can study offline or print it.*
**Acceptance criteria:** whole-kit export only for v1 (per open question #14) — summary, flashcards, quiz, and citations all included and legible.
**Files touched:** new `engine/export.py`, `api.py`.
**Definition of done:** exported PDF for a real generated kit is readable and complete, citations included.
**Reflection:**
>

### Day 17 — Anki export
**Goal:** export flashcards as a `.apkg` file importable into Anki.
**Why:** the more impressive of the two export formats to show off — plugs into a tool people actually use.
**User story:** *As a user, I want to export my flashcards to Anki, so that I can use spaced repetition in a tool I already use, even before this product builds its own.*
**Acceptance criteria:** valid `.apkg` file, confirmed by actually importing it into Anki (or a compatible reader) and checking the cards render correctly.
**Files touched:** `engine/export.py` (extend), using the `genanki` library.
**Definition of done:** a real Anki install successfully imports the exported deck.
**Reflection:**
>

### Day 18 — Frontend: upload, library, scope selection
**Goal:** bring the backend work from weeks 1–3 into a real, usable frontend flow.
**Why:** frontend was explicitly in scope as equally important, not a demo shell — this is where that commitment gets paid off.
**User story:** *As a user, I want a clear upload flow, a library view, and scope selection, so that the whole system is usable without hitting the API directly.*
**Acceptance criteria:** upload flow shows real-time ingestion status (Day 5); library view lists documents with status and supports scope selection for new requests (Day 12); loading/empty/error states are all handled, not just the happy path.
**Files touched:** `frontend/src/components` (new upload, library components).
**Definition of done:** a first-time user can upload a document, watch it process, and start a scoped request without any manual API calls.
**Reflection:**
>

### Day 19 — Frontend: results, citations, quiz-taking, search
**Goal:** finish the frontend surface for everything built in weeks 2–3.
**Why:** citations are the core differentiator — if they're not visible and clickable in the UI, the feature doesn't actually exist from a user's perspective.
**User story:** *As a user, I want to see citations next to generated content, take quizzes interactively, and search my library, so that the full feature set is actually usable, not just API-accessible.*
**Acceptance criteria:** results view shows citations linked back to source (Day 9); quiz-taking UI from Day 13 is integrated; search UI from Day 15 is integrated; verification-flagged items (Day 10) are visibly marked, not hidden.
**Files touched:** `frontend/src/components/Results.jsx` (extend), new quiz-taking and search components.
**Definition of done:** a full user journey — upload, search, generate, take quiz, see citations, export — works end to end through the UI with no direct API calls needed.
**Reflection:**
>

### Day 20 — Evaluation harness + demo polish
**Goal:** benchmark the pipeline against OpenStaxQA, finish the DeepEval suite, and get the whole thing demo-ready.
**Why:** this is what turns "I built a verification step" into "I benchmarked retrieval and generation accuracy against a published QA dataset" — the stronger interview claim from the tech-stack discussion.
**User story:** *As the developer, I want measurable evidence the system retrieves and generates accurately, so that I can speak to real numbers, not just describe the architecture.*
**Acceptance criteria:** DeepEval suite covers citation accuracy, quiz correctness, and retrieval relevance; a held-out slice of OpenStaxQA is used to measure retrieval/generation accuracy with an actual reported number; README/demo script updated to reflect the finished v1 scope; `Manual.md`/`AI_Engine_Manual.md` changelog and skills-learned sections updated to reflect this whole 4-week build, matching the existing documentation style.
**Files touched:** `tests/eval/` (new), `Manual.md`, `AI_Engine_Manual.md`, `README.md`.
**Definition of done:** you can state a real accuracy number for the pipeline, not just "it seems to work," and the repo's own documentation reflects what actually got built versus this plan.
**Reflection:**
>

---

## End-of-build retrospective (fill in after Day 20)

- What shipped vs. what was cut from this plan, and why:
- Which day's estimate was most wrong, and what that says about future estimates:
- The single hardest bug of the whole build:
- What you'd say in an interview if asked "walk me through a technical decision you're proud of" from this project:
- What's next — milestone 2 priorities based on what you learned building v1:
