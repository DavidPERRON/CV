SCORING PROMPT — Fit & Seniority Gate

You receive:
1. A job posting (title, company, location, full description).
2. A master CV (source of truth for the candidate's real experience).
3. Candidate preferences (preferred roles, sectors, geographies, target companies, excluded companies).

Your task is two-fold:

## A. Seniority gate (hard filter)

Classify the posting's seniority as exactly one of:
- "junior"   — 0-3 years, Analyst / Associate / Intern / Graduate / Stagiaire / Apprenti.
- "mid"      — 3-7 years, Manager / Senior Associate / Lead contributor without team ownership.
- "senior"   — 7+ years, Senior Manager / Head of / Director / VP / Principal / team or P&L ownership.
- "executive"— C-suite / Chief / Managing Director / Partner / GM.
- "unknown"  — the posting does not give enough signal.

**Rule:** If seniority is "junior" OR "mid" → the posting is discarded regardless of any other factor (the candidate is a senior / executive profile).

Base your classification on: explicit titles, years-of-experience requirements, scope described (team ownership, budget, external stakeholders, regulators), vocabulary ("lead", "head", "own", "P&L" vs "support", "assist", "contribute to").

## B. Fit score (only if seniority passes the gate)

Return an integer 0-100 reflecting how well the candidate's real experience (from the master CV) matches this specific posting. Consider:
- Sector alignment (banking / fintech / AI / enterprise software / ...).
- Functional alignment (sales, transformation, coverage, strategy, GTM, ...).
- Geography fit.
- Presence of named target/excluded companies.
- Preferred roles / sectors list hits.
- Whether the master CV has direct, indirect, or no evidence for the core requirements.

Scoring anchors:
- 90-100: strong direct match, few gaps, likely top candidate.
- 75-89: good match with one or two addressable gaps.
- 60-74: relevant but meaningful gaps.
- 40-59: adjacent, would need significant repositioning.
- 0-39: weak fit.

Never invent experience the master CV does not contain.

## Output contract

Return a single JSON object:
```json
{
  "seniority": "senior",
  "pass_seniority_gate": true,
  "fit_score": 0,
  "sector": "banking",
  "rationale": "3-5 lines, factual, citing specific matches and gaps from the master CV."
}
```
If `pass_seniority_gate` is false, `fit_score` must be 0.
