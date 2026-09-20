"""Typed exceptions for the Autonomous arXiv Paper Digest & QA Agent.

Having explicit exception classes prevents bare except clauses and ensures
graceful degradation across all pipeline stages.
"""

from __future__ import annotations


class AgentBaseError(Exception):
    """Base exception for all agent domain errors."""
    pass


class QueryParsingError(AgentBaseError):
    """Raised when query intent parsing fails unexpectedly."""
    pass


class NoResultsError(AgentBaseError):
    """Raised when arXiv returns zero papers for a query."""
    def __init__(self, query: str, suggestions: list[str] | None = None):
        super().__init__(f"No arXiv papers found for query: '{query}'")
        self.query = query
        self.suggestions = suggestions or []


class ArxivRetrievalError(AgentBaseError):
    """Raised when the arXiv API call encounters an unrecoverable failure."""
    pass


class ParseFailedError(AgentBaseError):
    """Raised when PDF extraction fails completely across all parsers."""
    def __init__(self, arxiv_id: str, reason: str):
        super().__init__(f"Failed to extract text from PDF for {arxiv_id}: {reason}")
        self.arxiv_id = arxiv_id
        self.reason = reason


class LLMProviderError(AgentBaseError):
    """Raised when an LLM provider fails, times out, or hits rate limits."""
    def __init__(self, provider: str, message: str):
        super().__init__(f"LLM provider '{provider}' failed: {message}")
        self.provider = provider


class SessionNotFoundError(AgentBaseError):
    """Raised when a requested session state file does not exist on disk."""
    def __init__(self, arxiv_id: str):
        super().__init__(f"No saved session found for arXiv ID: '{arxiv_id}'")
        self.arxiv_id = arxiv_id


class PDFDownloadError(AgentBaseError):
    """Raised when PDF download fails due to network, HTTP 429, or server errors."""
    pass


class PDFInvalidError(AgentBaseError):
    """Raised when downloaded content is not a valid PDF (e.g. HTML error page or missing %PDF header)."""
    pass


class PDFCorruptedError(AgentBaseError):
    """Raised when a PDF file is truncated or structurally corrupted and cannot be opened."""
    pass


class PDFScannedError(AgentBaseError):
    """Raised when a PDF is image-only/scanned with unextractable text."""
    pass


class PDFTextEmptyError(AgentBaseError):
    """Raised when a PDF has pages but yields zero extracted text."""
    pass
