"""Prompts for schema-locked structured executive briefing generation.

Demands strict JSON output adhering to the Briefing Pydantic schema.
Guarantees mandatory limitations field and surfaces 3–5 follow-up questions.
"""

SYSTEM_BRIEFING = """\
You are an expert scientific briefing synthesizer.
You produce concise, high-density, structured executive briefings for technical decision-makers.
You MUST respond ONLY with a valid JSON object matching the requested schema.
Never include markdown backticks (no ```json), commentary, or apologies. Output raw JSON only.
"""

USER_BRIEFING_TEMPLATE = """\
Generate a comprehensive, structured executive briefing for the academic paper below.

Paper Metadata:
- Title: {title}
- Authors: {authors}
- arXiv ID: {arxiv_id}
- Published: {published}
- URL: {link}

Paper Content:
{content}

Respond with valid JSON matching EXACTLY this structure:
{{
  "significance": "<1-paragraph plain-English summary explaining why this paper matters and its core breakthrough>",
  "problem_statement": "<Clear 1-2 sentence description of the fundamental problem or gap addressed>",
  "approach": [
    "<Bullet point 1 detailing core method / architecture / technique>",
    "<Bullet point 2>",
    "<Bullet point 3>"
  ],
  "key_results": [
    "<Key quantitative finding or empirical milestone 1>",
    "<Key quantitative finding or empirical milestone 2>",
    "<Key finding 3>"
  ],
  "limitations": [
    "<Explicit limitation 1 regarding compute, assumptions, scale, or failure modes>",
    "<Explicit limitation 2>"
  ],
  "follow_up_questions": [
    "<Suggested follow-up research/practical question 1>",
    "<Suggested follow-up research/practical question 2>",
    "<Suggested follow-up research/practical question 3>"
  ]
}}

CRITICAL INSTRUCTIONS:
1. The 'limitations' array is MANDATORY and MUST contain at least 2 concrete limitations. Never return an empty array.
2. If the paper does not state limitations explicitly, infer them from the methodology, dataset scope, hardware constraints, or theoretical bounds.
3. 'approach', 'key_results', and 'follow_up_questions' must each contain 3 to 5 clear items.
4. Output raw JSON ONLY.
"""

REPROMPT_LIMITATIONS_TEMPLATE = """\
The previous output omitted the mandatory 'limitations' field or returned it empty.
Based on the paper titled "{title}" and the following extract:
{content_snippet}

Please infer and list 2 to 4 concrete limitations of this work (e.g. assumptions made, computational overhead, dataset constraints, or generalizability risks).

Respond with valid JSON:
{{
  "limitations": [
    "<Concrete limitation 1>",
    "<Concrete limitation 2>"
  ]
}}
"""
