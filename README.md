# Idea Harbor

A lightweight, distraction-free web app to capture ideas and projects with:

- Name
- Color tag
- Description
- Parent idea (to create child-idea trees)
- Edit existing ideas quickly
- Feasibility score
- Self-rating of difficulty
- Priority

## Why this approach

- **No extra setup**: runs with Python standard library and SQLite.
- **Simple login**: one personal account can be created on first run.
- **Cross-device ready**: once hosted on any server/VPS, it's reachable from desktop and mobile browsers.

## Run locally

```bash
python3 app.py
```

Then open `http://localhost:8000`.

## Notes

- First-time startup shows account creation.
- Data persists in `ideas.db`.
- Session cookies are HTTP-only.
- Unknown preview paths now gracefully render the main app screen (helps hosted preview environments that proxy under custom URLs).

- Idea hierarchy panel shows Parent ideas and nested Child ideas; green strip + 'Parent idea' badge marks child cards.
- `GET /health` returns `ok` for simple uptime checks.

## Updating / merge conflicts

If you see merge conflicts while integrating this branch, prefer **Current Change** for `app.py` and `README.md` to keep the latest idea hierarchy + `Parent idea` wording and edit flow.

## Codex PR note

If you see: `Codex does not currently support updating PRs that are updated outside of Codex`, create a **new PR** from the current branch tip instead of trying to update the old PR.
