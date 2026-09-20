"""PDF download + dual-parser + section splitter + sanity check.

Pipeline
--------
1. download_pdf_full()  — fetch PDF to data/pdfs/<arxiv_id>.pdf with signature,
                          status, completeness, and safe-cache validation.
2. extract_document()   — try PyMuPDF first; fallback to pdfplumber if result
                          is empty, below MIN_PARSE_CHARS, or >90% whitespace.
                          Maintains PageData objects with 1-based page numbers.
3. split_sections_with_pages() — page-aware academic section detector.
4. validate_pdf_completeness() — verifies %PDF- header, openability, and page count.
"""

from __future__ import annotations

import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from config import (
    MAX_PDF_CHARS,
    MAX_PDF_PAGES,
    MIN_PARSE_CHARS,
    PDF_DIR,
    SECTION_HEADINGS,
)

logger = logging.getLogger(__name__)

USER_AGENT = "arxiv-paper-digest-agent/1.0 (academic-research-tool; mailto:research@example.com)"

# ── Optional imports (graceful-failure if library missing) ────────────────────

try:
    import pymupdf          # PyMuPDF ≥ 1.24 (package name changed from fitz)
    HAS_PYMUPDF = True
except ImportError:
    try:
        import fitz as pymupdf  # older PyMuPDF
        HAS_PYMUPDF = True
    except ImportError:
        HAS_PYMUPDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


# ── URL Normalization ─────────────────────────────────────────────────────────

_ARXIV_ID_PATTERN = re.compile(
    r"(?ix)"
    r"(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf|html|e-print)/)?"
    r"(?:arxiv[:\s]*)?"
    r"("
    r"\d{4}\.\d{4,5}(?:v\d+)?"
    r"|"
    r"[a-z\-]+(?:\.[a-z\-]+)?/\d{7}(?:v\d+)?"
    r")"
)


def normalize_pdf_url(url_or_id: str) -> str:
    """Normalize any arXiv URL or raw ID into a valid direct HTTPS PDF download URL.

    Handles:
      - https://arxiv.org/abs/2312.10997 -> https://arxiv.org/pdf/2312.10997.pdf
      - https://arxiv.org/abs/2312.10997v1 -> https://arxiv.org/pdf/2312.10997v1.pdf
      - https://arxiv.org/pdf/2312.10997 -> https://arxiv.org/pdf/2312.10997.pdf
      - https://arxiv.org/pdf/2312.10997.pdf -> https://arxiv.org/pdf/2312.10997.pdf
      - https://arxiv.org/pdf/2312.10997v1.pdf -> https://arxiv.org/pdf/2312.10997v1.pdf
      - http://arxiv.org/... -> https://arxiv.org/...
      - 2312.10997 -> https://arxiv.org/pdf/2312.10997.pdf
      - 2312.10997v2 -> https://arxiv.org/pdf/2312.10997v2.pdf
      - math/0211159v1 -> https://arxiv.org/pdf/math/0211159v1.pdf
    """
    raw = (url_or_id or "").strip()
    if not raw:
        return ""

    # Upgrade insecure HTTP for arxiv
    if raw.startswith("http://arxiv.org") or raw.startswith("http://www.arxiv.org"):
        raw = "https://" + raw[7:]

    # Match arXiv ID
    m = _ARXIV_ID_PATTERN.search(raw)
    if m:
        paper_id = m.group(1)
        return f"https://arxiv.org/pdf/{paper_id}.pdf"

    # If it is already a PDF URL, ensure .pdf extension
    if "arxiv.org/pdf/" in raw:
        if not raw.endswith(".pdf"):
            return f"{raw}.pdf"
        return raw

    # Abstract URL fallback
    if "arxiv.org/abs/" in raw:
        path_part = raw.split("arxiv.org/abs/")[-1].strip("/")
        return f"https://arxiv.org/pdf/{path_part}.pdf"

    if raw.startswith("http://") or raw.startswith("https://"):
        return raw

    # Fallback for bare identifiers
    clean_id = raw.replace("arxiv:", "").strip()
    clean_id = re.sub(r"\.pdf$", "", clean_id, flags=re.IGNORECASE)
    return f"https://arxiv.org/pdf/{clean_id}.pdf"


# ── PDF Validation & Completeness ─────────────────────────────────────────────

def validate_pdf_completeness(pdf_path: Path) -> tuple[bool, str, int]:
    """Verify that a local PDF file exists, is non-trivial, starts with %PDF-,
    can be opened by PyMuPDF or pdfplumber, and contains at least 1 readable page.

    Returns:
      (is_valid: bool, status: str, page_count: int)
    """
    if not pdf_path.exists():
        return False, "PDF_DOWNLOAD_FAILED: file does not exist", 0

    try:
        size = pdf_path.stat().st_size
    except Exception as e:
        return False, f"PDF_DOWNLOAD_FAILED: cannot stat file ({e})", 0

    if size <= 1024:
        return False, f"PDF_INVALID: file size too small ({size} bytes)", 0

    # Header check: must have %PDF signature in first 1024 bytes
    try:
        with open(pdf_path, "rb") as f:
            header = f.read(1024)
            if b"%PDF" not in header:
                return False, "PDF_INVALID: missing %PDF- magic signature", 0
    except Exception as e:
        return False, f"PDF_CORRUPTED: could not read header ({e})", 0

    # Structural check: open document and read page count
    page_count = 0
    if HAS_PYMUPDF:
        try:
            doc = pymupdf.open(str(pdf_path))
            page_count = len(doc)
            if page_count == 0:
                doc.close()
                return False, "PDF_CORRUPTED: document contains 0 pages", 0
            # Test that page 0 is accessible
            _ = doc[0].rect
            doc.close()
        except Exception as e:
            return False, f"PDF_CORRUPTED: PyMuPDF failed to open document ({e})", 0
    elif HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                page_count = len(pdf.pages)
                if page_count == 0:
                    return False, "PDF_CORRUPTED: pdfplumber reports 0 pages", 0
        except Exception as e:
            return False, f"PDF_CORRUPTED: pdfplumber failed to open document ({e})", 0
    else:
        page_count = 1

    return True, "OK", page_count


def _is_valid_pdf_file(path: Path) -> bool:
    """Backward-compatible boolean check for valid PDF file."""
    ok, _, _ = validate_pdf_completeness(path)
    return ok


# ── PDF Download with Retry & Safe Caching ────────────────────────────────────

def download_pdf_full(
    arxiv_id: str,
    pdf_url: str = "",
    max_attempts: int = 3,
    timeout: int = 30,
) -> tuple[Path | None, str, str | None, dict[str, Any]]:
    """Download PDF to data/pdfs/<arxiv_id>.pdf with full response validation.

    Checks:
      1. Safe Caching: Reuses existing local file if and only if validate_pdf_completeness passes.
         Evicts and redownloads if corrupt/invalid.
      2. Protocol: HTTPS with explicit polite User-Agent.
      3. Response validation: Status 200, Content-Type != text/html, size > 1024, magic bytes %PDF-.
      4. Retry logic: Handles HTTP 429 (Retry-After), HTTP 5xx, and network timeouts.

    Returns:
      (pdf_path, status, error_reason, metadata_dict)
    """
    safe_id = arxiv_id.replace("/", "_").replace(":", "_").strip()
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = PDF_DIR / f"{safe_id}.pdf"
    target_url = normalize_pdf_url(pdf_url or arxiv_id)

    # 1. Safe Cache Check
    if pdf_path.exists():
        is_valid, cache_status, page_count = validate_pdf_completeness(pdf_path)
        if is_valid:
            size = pdf_path.stat().st_size
            meta = {
                "url": target_url,
                "http_status": 200,
                "content_type": "application/pdf (cached)",
                "file_size": size,
                "magic_bytes": "%PDF-",
                "page_count": page_count,
                "cached": True,
            }
            return pdf_path, "OK", None, meta
        else:
            # Corrupted / invalid cached file — evict
            try:
                pdf_path.unlink()
            except Exception:
                pass

    # 2. Download Execution with Retry Policy
    last_status = "PDF_DOWNLOAD_FAILED"
    last_error: str | None = None
    last_meta: dict[str, Any] = {
        "url": target_url,
        "http_status": 0,
        "content_type": "unknown",
        "file_size": 0,
        "magic_bytes": "none",
        "page_count": 0,
        "cached": False,
    }

    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(
                target_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/pdf, */*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                http_status = resp.status
                content_type = resp.headers.get("Content-Type", "").lower()
                last_meta["http_status"] = http_status
                last_meta["content_type"] = content_type

                if http_status != 200:
                    last_status = "PDF_DOWNLOAD_FAILED"
                    last_error = f"HTTP {http_status}"
                    continue

                if "text/html" in content_type or "application/xhtml+xml" in content_type:
                    last_status = "PDF_INVALID"
                    last_error = f"Server returned HTML ({content_type}) instead of PDF"
                    continue

                data = resp.read()
                size = len(data)
                last_meta["file_size"] = size

                if size <= 1024:
                    last_status = "PDF_INVALID"
                    last_error = f"Response payload too small ({size} bytes)"
                    continue

                # Magic byte check
                if b"%PDF" not in data[:1024]:
                    last_status = "PDF_INVALID"
                    last_error = "Missing %PDF magic signature in first 1024 bytes"
                    continue

                # Write to disk and verify structural completeness
                pdf_path.write_bytes(data)
                is_valid, val_status, page_count = validate_pdf_completeness(pdf_path)
                if is_valid:
                    last_meta["magic_bytes"] = "%PDF-"
                    last_meta["page_count"] = page_count
                    return pdf_path, "OK", None, last_meta
                else:
                    try:
                        pdf_path.unlink()
                    except Exception:
                        pass
                    last_status = "PDF_CORRUPTED"
                    last_error = val_status

        except urllib.error.HTTPError as e:
            last_meta["http_status"] = e.code
            if e.code == 429:
                retry_after = e.headers.get("Retry-After")
                wait_sec = int(retry_after) if (retry_after and retry_after.isdigit()) else (2.0 * attempt)
                time.sleep(wait_sec)
                last_status = "PDF_DOWNLOAD_FAILED"
                last_error = f"HTTP 429 Too Many Requests (backoff {wait_sec}s)"
            elif e.code in (500, 502, 503, 504):
                time.sleep(1.5 * attempt)
                last_status = "PDF_DOWNLOAD_FAILED"
                last_error = f"HTTP {e.code} Server Error"
            else:
                last_status = "PDF_DOWNLOAD_FAILED"
                last_error = f"HTTP {e.code}: {e.reason}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_status = "PDF_DOWNLOAD_FAILED"
            last_error = f"Network failure: {exc}"
            if attempt < max_attempts:
                time.sleep(1.0 * attempt)
        except Exception as exc:
            last_status = "PDF_DOWNLOAD_FAILED"
            last_error = f"Unexpected download failure: {exc}"

    return None, last_status, last_error, last_meta


def download_pdf(arxiv_id: str, pdf_url: str) -> Path | None:
    """Backward-compatible helper returning Path | None."""
    path, _, _, _ = download_pdf_full(arxiv_id, pdf_url)
    return path


# ── Dual-Parser & Page Representation ─────────────────────────────────────────

@dataclass
class PageData:
    """Normalized page representation preserving page boundaries and char stats."""
    page_number: int     # 1-indexed
    text: str
    char_count: int


@dataclass
class ExtractionResult:
    """Container for dual-parser execution outcome."""
    pages: list[PageData]
    method: Literal["pymupdf", "pdfplumber", "abstract_only"]
    status: str          # "OK", "PDF_SCANNED", "PDF_TEXT_EMPTY", "PDF_PARSE_FAILED", "PDF_PARSE_DEGRADED"
    total_chars: int
    page_count: int
    sections_dict: dict[str, str]
    sections_detected: list[str]
    page_section_map: dict[str, list[tuple[int, str]]]  # section -> list of (page_num, text)
    pymupdf_info: str
    pdfplumber_info: str
    error: str | None = None


def evaluate_pages_quality(pages: list[PageData]) -> tuple[bool, str]:
    """Detect empty, low density, whitespace-dominated, or scanned PDF extraction."""
    if not pages:
        return False, "PDF_TEXT_EMPTY: zero pages extracted"

    total_chars = sum(p.char_count for p in pages)
    if total_chars == 0:
        return False, "PDF_TEXT_EMPTY: zero text characters found across all pages"

    if total_chars < MIN_PARSE_CHARS and len(pages) > 1:
        return False, f"PDF_SCANNED: low character total ({total_chars} chars across {len(pages)} pages)"

    avg_per_page = total_chars / max(len(pages), 1)
    if len(pages) >= 3 and avg_per_page < 100:
        return False, f"PDF_SCANNED: low average density ({avg_per_page:.1f} chars/page)"

    # Whitespace ratio
    combined = " ".join(p.text for p in pages)
    non_ws = sum(1 for c in combined if not c.isspace())
    if non_ws / max(len(combined), 1) < 0.10:
        return False, "PDF_SCANNED: text is >90% whitespace"

    # Replacement/garbage characters
    replacement_count = combined.count("\ufffd")
    if replacement_count > 50 and (replacement_count / max(len(combined), 1)) > 0.30:
        return False, "PDF_PARSE_DEGRADED: unreadable/corrupted character encoding"

    return True, "OK"


def _extract_pages_pymupdf(pdf_path: Path, max_pages: int = MAX_PDF_PAGES) -> list[PageData]:
    """Extract pages incrementally using PyMuPDF."""
    if not HAS_PYMUPDF:
        return []
    doc = pymupdf.open(str(pdf_path))
    num_pages = min(len(doc), max_pages)
    pages: list[PageData] = []
    for i in range(num_pages):
        text = doc[i].get_text() or ""
        pages.append(PageData(page_number=i + 1, text=text, char_count=len(text.strip())))
    doc.close()
    return pages


def _extract_pages_pdfplumber(pdf_path: Path, max_pages: int = MAX_PDF_PAGES) -> list[PageData]:
    """Extract pages incrementally using pdfplumber."""
    if not HAS_PDFPLUMBER:
        return []
    pages: list[PageData] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        num_pages = min(len(pdf.pages), max_pages)
        for i in range(num_pages):
            text = pdf.pages[i].extract_text() or ""
            pages.append(PageData(page_number=i + 1, text=text, char_count=len(text.strip())))
    return pages


# ── Page-Aware Section Detection ──────────────────────────────────────────────

_HEADING_PATTERN = re.compile(
    r"(?m)^"
    r"(?:\d+\.?\s+)?"
    r"("
    + "|".join(re.escape(h) for h in SECTION_HEADINGS)
    + r")"
    r"(?:\s*[:.\-]?)?"
    r"\s*$",
    re.IGNORECASE,
)


def split_sections_with_pages(
    pages: list[PageData],
) -> tuple[dict[str, str], dict[str, list[tuple[int, str]]], list[str]]:
    """Scan across pages, detect academic sections, and record exact page numbers.

    Returns:
      (sections_dict, page_section_map, detected_headings)
    """
    if not pages:
        return {}, {}, []

    sections_dict: dict[str, list[str]] = {}
    page_section_map: dict[str, list[tuple[int, str]]] = {}
    detected_headings: list[str] = []

    current_section = "abstract" if "abstract" in pages[0].text.lower() else "body"

    for page in pages:
        p_num = page.page_number
        lines = page.text.splitlines()

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            m = _HEADING_PATTERN.match(line_str)
            if m:
                heading = m.group(1).strip().lower()
                current_section = heading
                if heading not in detected_headings:
                    detected_headings.append(heading)
                continue

            # Accumulate paragraph text under current_section
            sections_dict.setdefault(current_section, []).append(line_str)
            page_section_map.setdefault(current_section, []).append((p_num, line_str))

    # Format sections_dict
    final_dict: dict[str, str] = {}
    for sec_name, items in sections_dict.items():
        text_content = "\n".join(items).strip()
        if text_content:
            final_dict[sec_name] = text_content

    if not final_dict:
        full_text = "\n".join(p.text for p in pages).strip()
        if full_text:
            final_dict["body"] = full_text

    return final_dict, page_section_map, detected_headings


def extract_document(pdf_path: Path) -> ExtractionResult:
    """Execute dual-parser extraction with automatic fallback and quality validation."""
    pymupdf_info = "unattempted"
    pdfplumber_info = "unattempted"

    # 1. Primary: PyMuPDF
    pages: list[PageData] = []
    try:
        pages = _extract_pages_pymupdf(pdf_path)
        is_usable, quality_reason = evaluate_pages_quality(pages)
        if is_usable:
            total_chars = sum(p.char_count for p in pages)
            sec_dict, page_sec_map, headings = split_sections_with_pages(pages)
            pymupdf_info = f"success ({total_chars} chars, {len(pages)} pages)"
            return ExtractionResult(
                pages=pages,
                method="pymupdf",
                status="OK",
                total_chars=total_chars,
                page_count=len(pages),
                sections_dict=sec_dict,
                sections_detected=headings,
                page_section_map=page_sec_map,
                pymupdf_info=pymupdf_info,
                pdfplumber_info="skipped (PyMuPDF succeeded)",
            )
        else:
            pymupdf_info = f"unusable: {quality_reason}"
    except Exception as exc:
        pymupdf_info = f"exception: {exc}"

    # 2. Fallback: pdfplumber
    try:
        pages_plumber = _extract_pages_pdfplumber(pdf_path)
        is_usable, quality_reason = evaluate_pages_quality(pages_plumber)
        if is_usable:
            total_chars = sum(p.char_count for p in pages_plumber)
            sec_dict, page_sec_map, headings = split_sections_with_pages(pages_plumber)
            pdfplumber_info = f"success ({total_chars} chars, {len(pages_plumber)} pages)"
            return ExtractionResult(
                pages=pages_plumber,
                method="pdfplumber",
                status="OK",
                total_chars=total_chars,
                page_count=len(pages_plumber),
                sections_dict=sec_dict,
                sections_detected=headings,
                page_section_map=page_sec_map,
                pymupdf_info=pymupdf_info,
                pdfplumber_info=pdfplumber_info,
            )
        else:
            pdfplumber_info = f"unusable: {quality_reason}"
    except Exception as exc:
        pdfplumber_info = f"exception: {exc}"

    # 3. Both Parsers Failed
    # Determine exact failure classification
    combined_pages = pages or pages_plumber if 'pages_plumber' in locals() else []
    total_chars = sum(p.char_count for p in combined_pages)

    if combined_pages and total_chars == 0:
        fail_status = "PDF_TEXT_EMPTY"
        err_msg = "PDF contains pages but zero extractable text (blank or image-only)"
    elif combined_pages and total_chars < MIN_PARSE_CHARS:
        fail_status = "PDF_SCANNED"
        err_msg = f"PDF appears to be scanned or image-only ({total_chars} characters extracted)"
    else:
        fail_status = "PDF_PARSE_FAILED"
        err_msg = f"Both parsers failed. PyMuPDF: {pymupdf_info}; pdfplumber: {pdfplumber_info}"

    return ExtractionResult(
        pages=[],
        method="abstract_only",
        status=fail_status,
        total_chars=total_chars,
        page_count=len(combined_pages),
        sections_dict={},
        sections_detected=[],
        page_section_map={},
        pymupdf_info=pymupdf_info,
        pdfplumber_info=pdfplumber_info,
        error=err_msg,
    )


# ── Backward Compatible API ───────────────────────────────────────────────────

def extract_text(
    pdf_path: Path,
) -> tuple[str, Literal["pymupdf", "pdfplumber", "abstract_only"]]:
    """Backward-compatible function returning (text, method)."""
    res = extract_document(pdf_path)
    if res.status == "OK" and res.pages:
        full_text = "\n\n".join(p.text for p in res.pages)
        return full_text[:MAX_PDF_CHARS], res.method
    return "", "abstract_only"


def split_sections(full_text: str) -> dict[str, str]:
    """Split raw text into sections dict."""
    if not full_text.strip():
        return {}

    matches = list(_HEADING_PATTERN.finditer(full_text))
    if len(matches) < 2:
        return {"body": full_text.strip()}

    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        heading = match.group(1).strip().lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()
        if content:
            sections[heading] = content

    if not sections:
        sections["body"] = full_text.strip()
    return sections


def _is_usable(text: str) -> bool:
    """Sanity check text length and whitespace."""
    if len(text) < MIN_PARSE_CHARS:
        return False
    non_ws = sum(1 for c in text if not c.isspace())
    if non_ws / max(len(text), 1) < 0.10:
        return False
    return True


def sanity_check(text: str) -> tuple[bool, str]:
    """Check parsed text quality."""
    if not text:
        return False, "empty text"
    if len(text) < MIN_PARSE_CHARS:
        return False, f"too short ({len(text)} chars < {MIN_PARSE_CHARS})"
    non_ws = sum(1 for c in text if not c.isspace())
    ratio = non_ws / len(text)
    if ratio < 0.10:
        return False, f"mostly whitespace ({ratio:.1%} non-whitespace)"
    return True, "ok"
