# InstructLab QnA YAML Requirements (v3)

This is a concise reference for preparing `qna.yaml` files used as seed examples. It summarizes structure, field semantics, and quality constraints, with special focus on `questions_and_answers`.

## Top-level fields

- **version**: Must be `3`.
- **created_by**: GitHub username (or the contributor’s identifier).
- **domain**:
  - Brief (1–3 words), consistent across a taxonomy (e.g., `Astronomy`, `Healthcare`).
  - Should reflect the subject/folder of the source document(s). Avoid vague or overly broad terms.
- **document_outline**:
  - A concise, descriptive title that provides grounding context (e.g., `IBM Q1 2024 Financial Report`).
  - Expand important acronyms; include year or type when useful.
- **document**:
  - `repo`: URL to the repository containing the source docs.
  - `commit`: SHA for the referenced content.
  - `patterns`: Repo-relative paths/globs for the source files (e.g., `docs/guide.md`).

## Seed examples

- **Count**: Prefer 5–15 sections. If the source is small and yields fewer than 5, it is acceptable; note this in logs.
- Each item contains:
  - **context**: A chunk copied (preferably verbatim) from the source markdown.
  - **questions_and_answers**: Up to 3 Q/A pairs for that context.

### Context

- **Size target**: ~500 tokens (300–500 recommended), but adjust to keep the total budget.
- **Source**: Direct excerpt from the document (do not paraphrase the context itself).
- **Coherence**: Prefer paragraph boundaries; the context should contain everything needed to support its Q/A.
- **Diversity**: Aim to sample different content forms (tables, lists, narrative) when present in the source.

### Questions and Answers

- **Per context**: Maximum 3 Q/A pairs (anything beyond 3 is ignored by downstream teacher models).
- **Budget**: The sum of context + all Q/A pairs must be ≤ 750 tokens.
- **Length targets** (not hard limits):
  - Question: ~30–60 tokens
  - Answer: ~180–220 tokens
  - Per pair total: ~250 tokens
- **Grounding**:
  - Questions must relate directly to the context.
  - Answers must be fully supported (entailed) by the context.
  - Paraphrasing is allowed; do not introduce facts not present in the context.
- **Quality**:
  - Avoid yes/no or single-word answers; use complete sentences.
  - Be specific and complete; avoid partial information when the context provides more.
  - Vary question types (fact, reasoning, comparison, implication) and cover salient points.
  - The question should be self-contained (no external chat history).

## Formatting and schema

- YAML must be valid and lint-clean (final newline, no tabs/mixed indentation, no duplicate keys).
- For knowledge datasets placed under a `knowledge/` path, validate against the InstructLab v3 JSON Schema (`knowledge.json`).

## Practical checklist

1. Set `version: 3`, `created_by`, and a brief `domain`.
2. Write a specific `document_outline` (title-like), expanding acronyms and including key identifiers (e.g., year).
3. For each seed example:
   - Select a coherent context excerpt (~500 tokens) from the source.
   - Provide up to 3 Q/A pairs that are entailed by the context (paraphrases allowed), targeting ~250 tokens per pair.
   - Keep total (context + pairs) ≤ 750 tokens.
4. Ensure 5–15 examples when the source allows; if the document is small and fewer than 5 are possible, proceed and log the exemption.
5. Fill `document.repo`, `document.commit`, and `document.patterns` with repository details.
6. Run an analyzer (e.g., `analyze-qna --ai`) to confirm budgets, counts, and structure; use any warnings as feedback to refine sections and pairs.

---
This guide reflects best practices to help teacher models generate high‑quality, grounded synthetic data with minimal validation friction.


