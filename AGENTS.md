# Alexa Morning News

- Repository: `1p-MAKER/my-first-app`. Work only inside this project. Keep the unrelated root `index.html` intact.
- Python 3.12, standard library only. Tests: `python3 -m unittest discover -s tests -v`. Workflow lint: `actionlint` when available. Check `git diff --check` before committing.
- Preserve Gemini-only generation, Google Search grounding, Japanese news categories, 5–7 minute target, weekday 05:45 JST Cloud Scheduler dispatch with GitHub Actions recovery runs, and 07:15 Alexa playback.
- Never store API keys in files, fixtures, logs or Git. Use `GEMINI_API_KEY` from the environment / Actions Secrets.
- `docs/` is the Pages build directory. A successful test, branch push or artifact upload is not a published feed or proven Echo playback.
- Commit and push scoped changes to the existing task branch. PR creation, main merge, Pages configuration, deployment and Alexa account changes require explicit authorization. Do not bypass branch protections.
- Keep `README.md` setup steps and `SPEC.md` operational behavior consistent with implementation. Do not turn mocked API tests into claims of live API success.
