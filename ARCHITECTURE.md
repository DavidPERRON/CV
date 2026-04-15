# CV Agent — Architecture

Adaptation de l'architecture [`davidPERRON/AI-Press-REVIEW-5`](https://github.com/davidPERRON/AI-Press-REVIEW-5)
au domaine **recherche d'offres → adaptation CV → dépôt en ligne semi-automatique**.

## 1. Principe directeur

Même shape que AI-Press-Review-5 :

1. **Collect** des sources externes (ici : emails LinkedIn + career pages + job boards).
2. **Extract** du contenu long-form (ici : job description complète, ≥ 300 mots).
3. **Score** / filtre éditorial (ici : matching vs CV maître).
4. **Generate** avec un LLM contraint par un prompt système strict (ici : `prompts/writing_prompt.md`).
5. **Draft persistant sur disque** (`pending_application`) en attente d'un humain.
6. **Release** manuelle via une commande / GitHub Action dédiée (ici : dépôt en ligne Playwright avec stop-before-submit).

Le shape **generate → pending → release/reject** est directement emprunté à
`ai_press_review.pipeline` (`generate_draft` / `release_pending_draft` / `reject_pending_draft`).

## 2. Mapping module par module

| AI-Press-Review-5                       | CV Agent                                 | Rôle |
|----------------------------------------|------------------------------------------|------|
| `settings.py`                          | `cv_agent/settings.py`                   | YAML + env vars, locale EN/FR |
| `models.py` (`SourceItem`, `EpisodeDraft`) | `cv_agent/models.py` (`JobPosting`, `ApplicationDraft`) | dataclasses |
| `state.py`                             | `cv_agent/state.py`                      | `applied_jobs.json`, `pending_applications.json` |
| `collect.py` (RSS + NewsAPI)           | `cv_agent/collect.py`                    | 4-phase : fetch → prefilter → extract → score |
| `collectors/rss.py`, `newsapi.py`      | `collectors/linkedin_email.py`, `collectors/rss_jobs.py`, `collectors/careers.py` | adaptateurs de source |
| `extractors/web_content.py`            | `extractors/job_description.py`          | trafilatura + BeautifulSoup, même stack |
| `editorial/validate.py`                | `editorial/scorer.py`                    | matching score vs master CV |
| `editorial/generator.py`               | `editorial/cv_generator.py`              | applique `writing_prompt.md` |
| `publish/episode_brief.py` + templates | `render/cv_html.py` + `render/templates/` | rendu HTML (même approche placeholder) |
| `storage/r2.py`                        | — (supprimé, pas utile ici)              | |
| `tts/cartesia.py`                      | — (supprimé, pas utile ici)              | |
| —                                      | `submit/playwright_apply.py`             | **nouveau** : dépôt semi-auto |
| `scripts/generate_draft.py`            | `scripts/generate_application.py`        | entrée 1 offre → `pending_application.json` |
| `scripts/release_draft.py`             | `scripts/submit_application.py`          | lance Playwright, stoppe avant Submit |
| `scripts/reject_draft.py`              | `scripts/reject_application.py`          | marque rejetée |
| `.github/workflows/daily-generate.yml` | `.github/workflows/daily-search.yml`     | cron quotidien |
| `.github/workflows/approve-release.yml`| `.github/workflows/approve-submit.yml`   | `workflow_dispatch` manuel |

## 3. Flux de données

```
┌──────────────────────────────────────────────────────────────────────┐
│  search_and_score.py   (cron quotidien GitHub Actions)               │
│  ├── collectors.linkedin_email  (IMAP Gmail)                         │
│  ├── collectors.rss_jobs        (boards RSS)                         │
│  └── collectors.careers         (pages carrière listées)             │
│                                                                      │
│  → dedup vs state/applied_jobs.json (fingerprint title+company+url)  │
│  → extractors.job_description   (full JD, ≥ 300 mots)                │
│  → editorial.scorer             (fit 0-100 vs master_cv.md)          │
│  → écrit runs/<date>/queue.jsonl                                     │
└──────────────────────────────────────────────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  generate_application.py --job <slug>                                │
│  ├── charge runs/<date>/<slug>/job.json                              │
│  ├── charge data/master_cv.md + prompts/writing_prompt.md            │
│  ├── editorial.cv_generator.generate() → LLM                         │
│  │     renvoie 4 blocs : positioning / competencies / gap / cv       │
│  ├── render.cv_html.render(cv_block, template) → cv_adapted.html     │
│  └── écrit runs/<date>/<slug>/                                       │
│      ├── positioning.md                                              │
│      ├── competencies.md                                             │
│      ├── gap_analysis.md                                             │
│      ├── cv_adapted.md + .html                                       │
│      ├── cover.md                                                    │
│      └── status.txt  ("pending_review")                              │
│  → state/pending_applications.json += entry                          │
└──────────────────────────────────────────────────────────────────────┘
                              ▼
                    ┌──────── HUMAN ─────────┐
                    │  relecture des 4 blocs │
                    │  édition éventuelle    │
                    │  décision : OK / KO    │
                    └───────────┬────────────┘
                                │
        ┌───────────────────────┴──────────────────────┐
        ▼                                              ▼
┌──────────────────────┐              ┌─────────────────────────────┐
│ submit_application   │              │ reject_application          │
│ --job <slug>         │              │ --job <slug> --reason ...   │
│                      │              │                             │
│ Playwright headful   │              │ status.txt → "rejected"     │
│ ├── navigate to URL  │              │ pending → applied_jobs.json │
│ ├── fill form        │              │   (avec raison)             │
│ ├── upload cv.pdf    │              │                             │
│ ├── STOP au bouton   │              │                             │
│ │     Submit final   │              │                             │
│ └── attend clic      │              │                             │
│     humain           │              │                             │
│                      │              │                             │
│ puis status.txt →    │              │                             │
│   "submitted"        │              │                             │
│ + archive dans       │              │                             │
│   applied_jobs.json  │              │                             │
└──────────────────────┘              └─────────────────────────────┘
```

## 4. Layout disque

```
CV/
├── ARCHITECTURE.md                    (ce fichier)
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env.example                        (déjà en place)
├── .gitignore                          (déjà en place)
├── config/
│   ├── app_settings.json               (déjà en place, réutilisé)
│   ├── jobs.yaml                       (nouveau : seuils, langues, rôles)
│   └── sources.yaml                    (nouveau : flux RSS + career pages)
├── prompts/
│   ├── search_prompt.md                (déjà)
│   ├── scraping_prompt.md              (déjà)
│   ├── writing_prompt.md               (déjà, prompt système principal)
│   └── scoring_prompt.md               (nouveau : fit scoring contract)
├── data/
│   ├── master_cv.md                    (CV maître — à fournir par l'utilisateur)
│   ├── master_cv.en.md                 (variant EN si fourni)
│   └── state/
│       ├── applied_jobs.json           (dedup + historique)
│       └── pending_applications.json   (drafts en attente)
├── src/cv_agent/
│   ├── __init__.py
│   ├── settings.py
│   ├── models.py
│   ├── state.py
│   ├── utils.py
│   ├── pipeline.py
│   ├── collect.py
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── linkedin_email.py
│   │   ├── rss_jobs.py
│   │   └── careers.py
│   ├── extractors/
│   │   ├── __init__.py
│   │   └── job_description.py
│   ├── editorial/
│   │   ├── __init__.py
│   │   ├── scorer.py
│   │   └── cv_generator.py
│   ├── render/
│   │   ├── __init__.py
│   │   ├── cv_html.py
│   │   └── templates/
│   │       ├── cv-template.html
│   │       └── cover-template.html
│   ├── submit/
│   │   ├── __init__.py
│   │   └── playwright_apply.py
│   └── llm/
│       ├── __init__.py
│       └── client.py
├── scripts/
│   ├── search_and_score.py
│   ├── generate_application.py
│   ├── submit_application.py
│   └── reject_application.py
├── tests/
│   ├── test_state.py
│   ├── test_scorer.py
│   └── test_generator_contract.py
├── .github/workflows/
│   ├── daily-search.yml
│   └── approve-submit.yml
└── runs/                               (gitignored)
    └── <YYYY-MM-DD>/
        ├── queue.jsonl
        └── <job_slug>/
            ├── job.json
            ├── positioning.md
            ├── competencies.md
            ├── gap_analysis.md
            ├── cv_adapted.md
            ├── cv_adapted.html
            ├── cover.md
            └── status.txt
```

## 5. Contrats clés

### 5.1 Prompt système (generator)
Le système prompt envoyé au LLM **est littéralement** le contenu de
`prompts/writing_prompt.md`, sans altération. Le user prompt injecte :

```
### JOB DESCRIPTION
<texte brut de l'offre, scrapée>

### MASTER CV (source de vérité, ne rien inventer au-delà)
<contenu de data/master_cv.md>

### LANGUE DE SORTIE
<EN | FR>

### INSTRUCTIONS COMPLEMENTAIRES
<facultatif>
```

Le LLM doit répondre en JSON strict :
```json
{
  "positioning": "markdown...",
  "competencies": "markdown...",
  "gap_analysis": "markdown...",
  "cv_adapted": "markdown...",
  "cover_letter": "markdown..."
}
```

Chaque bloc est enregistré dans un fichier séparé pour relecture et édition.

### 5.2 Guard "zéro invention"
`editorial.cv_generator.validate_no_invention(draft, master_cv)` :
- Extrait toute entité nommée du `cv_adapted` (entreprises, écoles, diplômes, dates, outils, langues).
- Vérifie qu'elle apparaît dans `master_cv.md` (comparaison insensible à la casse).
- Lève `InventionError` avec la liste des entités suspectes si l'écart dépasse un seuil.

Ce garde-fou est une approximation, pas une preuve. Il attrape les cas grossiers
(noms d'entreprise, diplômes fantômes). La lecture humaine reste obligatoire.

### 5.3 State / dedup
Fingerprint d'une offre = `sha256(company + "|" + title + "|" + canonical_url)`.
`applied_jobs.json` capé à 1000 entrées (rotation FIFO), rétention 180 jours.

### 5.4 Stop-before-submit
`submit/playwright_apply.py` :
- Lance Chromium en `headless=False` avec `user_data_dir` persistant (session LinkedIn conservée).
- Remplit les champs déterministes (upload CV PDF, cover letter, questions Yes/No standards).
- **S'arrête juste avant le bouton "Submit application"** et affiche dans la console :
  ```
  READY TO SUBMIT — review the pre-filled form in the browser.
  Press ENTER to submit, or Ctrl+C to abort.
  ```
- Passe `status.txt` à `submitted` uniquement après retour `ENTER`.
- Si timeout 20 min ou Ctrl+C → `status.txt` = `aborted_by_user`, aucune soumission.

## 6. Sécurité

- Tous les secrets via env vars (`LINKEDIN_EMAIL`, `GMAIL_APP_PASSWORD`, `ANTHROPIC_API_KEY`).
- `.env` + `.playwright-user-data/` + `runs/` → `.gitignore`.
- `config/app_settings.json` ne contient plus de credentials (cf. commit `a5b9550`).
- Le script de submit n'accepte **jamais** `--auto-confirm` : le gate humain est non contournable.

## 7. Ce que l'adaptation retire par rapport à AI-Press-Review-5

- Pas de TTS (Cartesia).
- Pas de Cloudflare R2.
- Pas de feed RSS publié.
- Pas de rendu HTML public sur GitHub Pages (les CV adaptés sont privés).

## 8. Ce que l'adaptation ajoute

- Collecteur IMAP Gmail (alertes LinkedIn).
- Guard "zéro invention" sur le CV généré.
- Étape de soumission semi-auto Playwright avec gate humain explicite.
- Prompt système fidèle au `writing_prompt.md` (méthode exécutive stricte du candidat).
