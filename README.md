# Idea Harbor

A lightweight, distraction-free web app to capture ideas and projects with:

- Name
- Color tag
- Description
- Relationship/connection to another project
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

- Relationship map includes a legend: green left strip + 'Depends on' badge means the idea is linked to another.
- `GET /health` returns `ok` for simple uptime checks.
