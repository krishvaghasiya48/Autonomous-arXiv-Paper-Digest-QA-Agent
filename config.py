"""Central configuration — all tuneable constants live here.

Import this module everywhere; never hardcode paths or magic numbers in node code.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).resolve().parent
DATA_DIR   = ROOT_DIR / "data"
PDF_DIR    = DATA_DIR / "pdfs"
CHROMA_DIR = DATA_DIR / "chroma"
SESSION_DIR = DATA_DIR / "sessions"

# Ensure runtime dirs exist on import
for _d in (PDF_DIR, CHROMA_DIR, SESSION_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── arXiv retrieval ───────────────────────────────────────────────────────────
ARXIV_MAX_RESULTS   = 10        # max candidates for topic search
ARXIV_RETRY_ATTEMPTS = 3        # tenacity retry count
ARXIV_RETRY_WAIT    = 2.0       # seconds between retries (exponential base)

# ── PDF parsing ───────────────────────────────────────────────────────────────
MIN_PARSE_CHARS   = 500         # below this → retry with pdfplumber
MAX_PDF_PAGES     = 80          # cap to avoid 200-page survey papers
MAX_PDF_CHARS     = 120_000     # hard char cap after page cap

# Section headers we look for when splitting parsed text
SECTION_HEADINGS = [
    "abstract",
    "introduction",
    "background",
    "related work",
    "method",
    "methodology",
    "approach",
    "model",
    "architecture",
    "experiments",
    "experimental",
    "results",
    "evaluation",
    "discussion",
    "limitations",
    "conclusion",
    "conclusions",
    "future work",
    "references",
    "acknowledgements",
    "appendix",
]

# ── Chunking ─────────────────────────────────────────────────────────────────
CHUNK_SIZE    = 900     # target chars per chunk
CHUNK_OVERLAP = 150     # overlap between adjacent chunks
# Justification: academic paragraphs avg 600–1000 chars;
# all-MiniLM-L6-v2 window is 256 tokens ≈ ~1000 chars max.
# 150-char overlap preserves claims that straddle a boundary.

# ── Embeddings ────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # local, CPU-friendly, 384-dim, no API key

# ── Vector store ─────────────────────────────────────────────────────────────
CHROMA_COLLECTION_PREFIX = "paper_"    # collection = paper_<arxiv_id>
TOP_K_DENSE  = 8    # dense candidates before merge
TOP_K_BM25   = 8    # BM25 candidates before merge
TOP_K_FINAL  = 5    # after merge + dedup

# ── LLM ──────────────────────────────────────────────────────────────────────
# Provider priority: groq → gemini → ollama
GROQ_MODEL    = "llama-3.3-70b-versatile"
GEMINI_MODEL  = "gemini-1.5-flash"
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "llama3.2")
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS  = 2048

# Groq free-tier rate limits (as of 2024):
#   6000 tokens/min on llama-3.3-70b-versatile
#   Document these so reviewers know what to expect.
GROQ_RATE_LIMIT_NOTE = (
    "Groq free tier: ~6000 tokens/min on llama-3.3-70b-versatile. "
    "If you hit a 429, the agent will back off and retry automatically. "
    "Alternatively set GEMINI_API_KEY for the fallback path."
)

# ── LLM keys (read from env) ─────────────────────────────────────────────────
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
