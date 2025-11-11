# C3 Inquiry Planner

This Flask application builds C3 Framework-aligned inquiry lessons by combining the Michigan standards catalog with AI-powered lesson planning and personalization.

## Getting Started

1. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run the web app**
   ```bash
   flask --app webapp.app run --reload
   ```

3. **Optional APIs**
   - To enable LangChain lesson refinement, set `OPENAI_API_KEY` (and optionally `OPENAI_API_BASE`).
   - For dynamic resource discovery via Perplexity and Browserless, provide `PERPLEXITY_API_KEY` and `BROWSERLESS_API_KEY`.

## Project Layout

- `webapp/` – Flask routes, lesson builder, templates, and static assets.
- `Curriculum-Ontology/` – Michigan and C3 ontology files used to hydrate the catalog.
- `planner/` – core inquiry planning logic and LLM clients.
- `current-html/` – (ignored) local captures for debugging layout regressions.

## Deployment Checklist

1. Ensure secrets are stored as environment variables (never in git).
2. Run `flask --app webapp.app run` locally to verify lesson generation and resource fetching.
3. Commit changes and push to GitHub:
   ```bash
   git add .
   git commit -m "Describe your change"
   git remote add origin git@github.com:YOUR_NAME/c3-inquiry-planner.git
   git push -u origin main
   ```

Happy planning!
