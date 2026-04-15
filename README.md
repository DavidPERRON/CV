# cv-agent

Pipeline d'adaptation de CV exécutif et de dépôt semi-automatique, inspiré de
l'architecture [`davidPERRON/AI-Press-REVIEW-5`](https://github.com/davidPERRON/AI-Press-REVIEW-5).

Vue d'ensemble de l'architecture : [ARCHITECTURE.md](./ARCHITECTURE.md).

## Flux

```
collect (RSS + career pages + LinkedIn email IMAP)
  -> extract full JD
  -> score (junior filter + LLM fit vs master CV)
  -> generate (writing_prompt.md, JSON strict, garde zéro-invention)
  -> pending_review (humain relit les 4 blocs + CV adapté)
  -> submit (Playwright, STOP avant le bouton final, ENTER humain requis)
```

## Installation

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
cp .env.example .env
# remplir ANTHROPIC_API_KEY, LINKEDIN_EMAIL, GMAIL_APP_PASSWORD
```

## Fichiers à fournir

- `data/master_cv.md` — ton CV maître (source de vérité). Facultativement
  `data/master_cv.en.md` et `data/master_cv.fr.md` pour deux versions linguistiques.
- `prompts/writing_prompt.md` — déjà présent. C'est le prompt système
  utilisé par le générateur. **Ne rien modifier sauf intention explicite**.
- `config/sources.yaml` — liste des pages carrière et flux RSS. Les entrées
  livrées sont des points de départ (banques FR/UK/DE/NL/CH/NORDIC/IB/IT,
  fintech EU + CA, AI labs, chasseurs de têtes européens). À valider et
  ajuster à mesure des premiers runs.
- `config/jobs.yaml` — seuils, langues, rôles préférés, géographies, blocklist
  junior.

## Usage

### 1) Recherche + scoring (quotidien)

```bash
cv-search -v
# -> écrit runs/<YYYY-MM-DD>/queue.jsonl + un dossier par job au-dessus du seuil mid
```

Affiche les 10 meilleurs matches avec leur `fingerprint`.

### 2) Générer la candidature adaptée

```bash
cv-generate --fingerprint <fp> --language EN
# -> runs/<date>/<slug>/{positioning,competencies,gap_analysis,cv_adapted,cover}.md
#    + cv_adapted.html
#    + status.txt = pending_review
```

Le garde-fou "zéro invention" bloque la génération si le CV adapté contient
des entreprises, écoles ou diplômes absents de ton master CV. Pour désactiver
(non recommandé) : `--allow-invention`.

### 3) Relecture humaine

Ouvre les fichiers, édite si besoin. Tant que le statut est `pending_review`,
rien n'est envoyé.

### 4) Dépôt semi-automatique

```bash
cv-submit --fingerprint <fp> --cv-pdf /chemin/vers/cv.pdf
```

- Chromium s'ouvre en mode visible, se rend sur l'URL de l'offre.
- Un adapter spécifique au site (LinkedIn, Greenhouse, Lever, Workable…) pré-remplit
  ce qu'il peut : upload du CV PDF, lettre de motivation.
- Le script **s'arrête avant le bouton final** et affiche dans le terminal :

```
================================================================
READY TO SUBMIT — review the pre-filled form in the browser now.
Press ENTER in this terminal to confirm submission.
Press Ctrl+C to abort (no submission will be sent).
================================================================
```

Tu relis l'écran, tu presses `ENTER` pour valider ou `Ctrl+C` pour annuler.
Timeout par défaut : 20 minutes (configurable dans `config/jobs.yaml`).

### 5) Rejeter une offre sans postuler

```bash
cv-reject --fingerprint <fp> --reason "scope too junior"
```

Archive la fingerprint dans `data/state/applied_jobs.json` avec la raison,
empêche de la re-découvrir.

## Sécurité

- Aucun secret dans le dépôt. Tout via `.env` (non versionné) ou `GITHUB Secrets`.
- Le mot de passe Gmail qui traînait dans `config/app_settings.json` a été
  retiré au commit `a5b9550`. **Il reste dans l'historique git** : pense à le
  révoquer dans https://myaccount.google.com/apppasswords.
- Pas de flag `--auto-confirm` côté submit. Le gate humain n'est pas contournable.

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

Les tests couvrent :
- `test_utils.py` — slugify, fingerprint, canonical URL.
- `test_state.py` — cap FIFO, TTL, ajout/suppression pending.
- `test_scorer.py` — blocklist junior.
- `test_generator_contract.py` — contrat LLM (blocs requis) + garde zéro-invention.

Aucun test ne fait d'appel réseau ni LLM — le LLM est mocké.

## GitHub Actions

- `.github/workflows/daily-search.yml` — cron quotidien 05:45 UTC. Lance la recherche,
  commit `runs/` + `data/state/`. Requiert les secrets `ANTHROPIC_API_KEY`,
  `LINKEDIN_EMAIL`, `GMAIL_APP_PASSWORD`.
- `.github/workflows/approve-submit.yml` — `workflow_dispatch` manuel.
  Génère le draft côté CI et le commit. La soumission reste locale (Playwright
  interactif).

## Limites connues

- **Les URLs de `config/sources.yaml` sont des points de départ.** Les sites carrière
  changent fréquemment leurs sélecteurs CSS. Le premier run te dira lesquels ne
  ramènent plus rien.
- **Le collecteur LinkedIn via IMAP repose sur les alertes mail** — pas de scraping
  direct de linkedin.com (ToS). Tu dois t'être abonné à des alertes correspondant
  à ton périmètre.
- **L'adapter Workday est intentionnellement passif** : trop de variations. Le
  script ouvre la page et laisse l'humain conduire.
- **Le garde "zéro invention" est heuristique**, pas une preuve. La relecture humaine
  reste obligatoire.
