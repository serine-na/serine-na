# Setup

1. Create a public repo named exactly like your username and upload everything in this folder
   (`README.md`, `generate.py`, `assets/`, `.github/workflows/update-cards.yml`, `SETUP.md`).
2. Nothing to edit: username (`serine-na`) and name (`Serine`) are already set.
3. Repo → Settings → Actions → General → Workflow permissions → "Read and write permissions".
4. Repo → Actions → "Update profile cards" → Run workflow. Cards now fill with your real data
   and refresh daily.
5. Optional: edit CONFIG at the top of `generate.py` (name, tagline, extra social pills, colours).

Local run: `GITHUB_TOKEN=<token> PROFILE_USER=<you> python generate.py`
