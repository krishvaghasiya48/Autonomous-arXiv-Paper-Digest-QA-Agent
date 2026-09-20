# Autonomous arXiv Paper Digest & QA Agent — Technical Architecture

This document describes the design, routing mechanisms, storage models, and failure recovery strategies of the Autonomous arXiv Paper Digest & QA Agent.

---

## 1. High-Level Two-Graph Architecture

Rather than bolting Question-Answering onto a single long prompt chain, the system is explicitly divided into two decoupled lifecycle graphs compiled via **LangGraph**:

```
                              ┌───────────────────────────────────┐
                              │     AgentState (Pydantic Model)   │
                              │  Shared across all nodes & saved  │
                              │  to data/sessions/<arxiv_id>.json │
                              └───────────────────────────────────┘
                                                │
════════════════════════════════════════════════╪════════════════════════════════════════════════
 GRAPH A: Digest Pipeline (Nodes 1–6)           │
════════════════════════════════════════════════╪════════════════════════════════════════════════
                                                ▼
                                    ┌───────────────────────┐
                                    │ 1. Query Understanding│
                                    └───────────────────────┘
                                                │
                        ┌───────────────────────┴───────────────────────┐
      intent == "paper_lookup"                                intent == "topic_search"
                        ▼                                               ▼
            ┌──────────────────────┐                        ┌──────────────────────┐
            │ 2b. arXiv ID Lookup  │                        │ 2a. arXiv Topic Search│
            └──────────────────────┘                        └──────────────────────┘
                        │                                               │
                        │                               ┌───────────────┴───────────────┐
                        │                       candidates == []                candidates > 0
                        │                               ▼                               ▼
                        │                   ┌───────────────────────┐       ┌──────────────────────┐
                        │                   │ Clarify Node (Suggestions)│    │ 3. Selection Node    │
                        │                   └───────────────────────┘       └──────────────────────┘
                        │                               │ (Terminal)                    │
                        └───────────────────────┬───────┴───────────────────────────────┘
                                                ▼
                                    ┌───────────────────────┐
                                    │ 4. Fetch & Parse PDF  │
                                    └───────────────────────┘
                                                │
                        ┌───────────────────────┴───────────────────────┐
             hard fail (no text/abstract only)                  normal parse / partial
                        ▼                                               ▼
                        │                                   ┌───────────────────────┐
                        │                                   │ 5. Chunk & Embed      │
                        │                                   └───────────────────────┘
                        │                                               │
                        └───────────────────────┬───────────────────────┘
                                                ▼
                                    ┌───────────────────────┐
                                    │ 6. Structured Briefing│
                                    └───────────────────────┘
                                                │
                                                ▼
                                              (END)
════════════════════════════════════════════════════════════════════════════════════════════════
 GRAPH B: Grounded QA Loop (Node 7) — Hydrates state from disk without re-parsing/re-embedding
════════════════════════════════════════════════════════════════════════════════════════════════
                                                ▼
                                    ┌───────────────────────┐
                                    │ 7. Grounded QA Node   │◀─────┐
                                    │ - Hybrid dense + BM25 │      │
                                    │ - [C1] citations      │      │ Interactive Loop
                                    │ - "Not stated..."     │──────┘
                                    └───────────────────────┘
                                                │
                                                ▼
                                              (END)
```

---

## 2. The Three Critical Conditional Edges

1. **Edge 1: Intent Routing (Node 1 → Node 2a vs. Node 2b)**
   - Regex matches new-style arXiv IDs (`2401.12345`), old-style IDs (`hep-th/9901001`), and `arxiv.org` URLs.
   - If regex detects an ID or URL, intent is classified as `paper_lookup` and immediately branches to `arxiv_retrieval_id`, skipping candidate ranking entirely.
   - Natural language queries branch to `arxiv_retrieval_topic`.

2. **Edge 2: Zero-Results Resilience (Node 2a → Clarify vs. Selection)**
   - If the topic search returns 0 candidates from arXiv, the pipeline does **not** crash or raise an unhandled exception.
   - Instead, it transitions to the terminal `clarify` node, which returns broadened query suggestions and alternative keyword recommendations.

3. **Edge 3: Parse Failure Routing (Node 4 → Summarize vs. Chunk & Embed)**
   - When PDF download or extraction fails completely, the agent sets `parse_degraded = True` and populates `sections["abstract"]` from the API metadata.
   - If text extraction is completely unusable, it routes directly to `summarize` (abstract-only briefing with an explicit warning banner) or embeds the available abstract without crashing.

---

## 3. Grounding, Chunking & Hybrid Retrieval

### Chunking Rationale (900 Chars / 150 Overlap)
- **Target Size (900 chars)**: Academic paragraphs average 600–1000 characters. `all-MiniLM-L6-v2` has a 256-token context window (~1000 chars max). 900 chars leaves headroom for prompt labels and metadata without truncating context.
- **Overlap (150 chars)**: Corresponds to ~1–2 sentences. Claims or equations spanning paragraph boundaries remain intact in at least one chunk.
- **Section Isolation**: Chunks never merge across section boundaries. References sections are excluded from embeddings to prevent noise.

### Hybrid Retrieval (Dense + BM25)
- Dense retrieval (ChromaDB cosine similarity with `all-MiniLM-L6-v2`) captures conceptual semantics.
- Sparse retrieval (BM25Okapi) captures exact entities (e.g. `llama-3`, `BLEU`, mathematical constants).
- **Reciprocal Rank Fusion (RRF)**: Merges dense top-8 and BM25 top-8, deduplicating chunks and ranking the top-5 candidates for QA context injection.

### Grounding Rules & Refusal
- Chunks are labeled as `[C1 | section=... | page=...]`.
- If a question cannot be answered from the provided chunks, the LLM is instructed to return:
  `"Not stated in this paper."` followed by what related topics the context discusses.
- Factual answers must cite their sources using `[C1]`, `[C2]`.

---

## 4. Multi-Provider Zero-Paid LLM Fallback

To satisfy the strict constraint of requiring zero paid API keys:
1. **Primary**: **Groq** (`llama-3.3-70b-versatile`) — Fast inference on free-tier.
2. **Secondary**: **Google Gemini** (`gemini-1.5-flash`) — Free-tier fallback.
3. **Tertiary / Offline**: **Ollama CLI** (`llama3.2`) — Fully local execution requiring zero network credentials.
