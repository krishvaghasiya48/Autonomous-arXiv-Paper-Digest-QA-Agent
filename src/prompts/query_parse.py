"""Prompt for LLM-based query intent parsing.

Used only when the regex in query_understanding.py cannot determine intent.
The LLM must return strict JSON — no prose, no markdown fences.
"""

SYSTEM = "You are a query classifier. Respond with valid JSON only. No explanation, no markdown."

USER_TEMPLATE = """\
Classify the following user input and return JSON exactly matching this schema:
{{
  "intent": "topic_search" | "paper_lookup",
  "cleaned_query": "<cleaned version of the input>",
  "arxiv_id": "<arXiv ID if intent is paper_lookup, else null>"
}}

Rules:
- intent = "paper_lookup"  if the input is an arXiv ID, versioned ID, or arxiv.org URL
- intent = "topic_search"  for all natural-language research topics
- cleaned_query = strip extra whitespace; for topics, keep the full phrase
- arxiv_id = bare ID without version suffix (e.g. "2401.12345"), null for topics

User input:
{raw_input}

JSON:"""
