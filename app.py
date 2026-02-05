#!/usr/bin/env python3
import html
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from http import cookies
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import make_server

DB_PATH = os.path.join(os.path.dirname(__file__), "ideas.db")
SESSION_DAYS = 14


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            color TEXT NOT NULL,
            description TEXT NOT NULL,
            related_idea_id INTEGER,
            feasibility INTEGER NOT NULL,
            difficulty INTEGER NOT NULL,
            priority INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(related_idea_id) REFERENCES ideas(id)
        );
        """
    )
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    import hashlib

    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    import hashlib

    salt, digest = stored.split("$", 1)
    trial = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return secrets.compare_digest(digest, trial)


def parse_cookies(environ):
    cookie_jar = cookies.SimpleCookie()
    cookie_jar.load(environ.get("HTTP_COOKIE", ""))
    return cookie_jar


def get_session_user(environ):
    cookie_jar = parse_cookies(environ)
    token = cookie_jar.get("session")
    if not token:
        return None

    conn = db()
    conn.execute("PRAGMA foreign_keys = ON")
    session = conn.execute(
        "SELECT user_id, expires_at FROM sessions WHERE token = ?", (token.value,)
    ).fetchone()
    if not session:
        conn.close()
        return None

    if datetime.fromisoformat(session["expires_at"]) < datetime.utcnow():
        conn.execute("DELETE FROM sessions WHERE token = ?", (token.value,))
        conn.commit()
        conn.close()
        return None

    user = conn.execute(
        "SELECT id, username FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    conn.close()
    return user


def set_session_headers(user_id):
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(days=SESSION_DAYS)
    conn = db()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO sessions(token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires.isoformat()),
    )
    conn.commit()
    conn.close()
    return [
        (
            "Set-Cookie",
            f"session={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={SESSION_DAYS*24*60*60}",
        )
    ]


def clear_session_headers(environ):
    cookie_jar = parse_cookies(environ)
    token = cookie_jar.get("session")
    if token:
        conn = db()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM sessions WHERE token = ?", (token.value,))
        conn.commit()
        conn.close()
    return [("Set-Cookie", "session=; HttpOnly; Path=/; Max-Age=0")]


def redirect(start_response, location, headers=None):
    headers = headers or []
    start_response("303 See Other", [("Location", location), *headers])
    return [b""]


def form_data(environ):
    try:
        size = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError:
        size = 0
    body = environ["wsgi.input"].read(size).decode("utf-8")
    parsed = parse_qs(body)
    return {k: v[0] if v else "" for k, v in parsed.items()}


def num_value(raw, default=5):
    try:
        return max(1, min(10, int(raw)))
    except (TypeError, ValueError):
        return default


def relationship_summary(ideas):
    by_id = {idea["id"]: idea for idea in ideas}
    rows = []
    linked = 0
    for idea in ideas:
        if idea["related_idea_id"] and idea["related_idea_id"] in by_id:
            linked += 1
            parent = by_id[idea["related_idea_id"]]
            rows.append(
                f"<li><span class='swatch' style='background:{html.escape(idea['color'])}'></span><strong>{html.escape(idea['name'])}</strong> \u2192 <span>{html.escape(parent['name'])}</span></li>"
            )

    if not rows:
        relation_text = "No links yet. Connect ideas to reveal project lanes."
        detail = "Start by relating one idea to another so priorities become clearer."
    else:
        relation_text = f"{linked} linked idea{'s' if linked != 1 else ''} out of {len(ideas)}"
        detail = "Linked items are highlighted in the board with a relationship strip."

    return relation_text, detail, "".join(rows) or "<li>No relationships created yet.</li>"


def layout(title, body, username=None, flash=None):
    nav = ""
    if username:
        nav = f"""
        <div class='nav-right'>
            <span class='hello'>Hi, {html.escape(username)}</span>
            <form method='POST' action='/logout'><button class='ghost'>Log out</button></form>
        </div>
        """

    flash_html = f"<div class='flash'>{html.escape(flash)}</div>" if flash else ""

    return f"""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>{html.escape(title)}</title>
<style>
:root {{
  --bg:#f6f3ee;
  --panel:#fffdfa;
  --ink:#202020;
  --muted:#6e665f;
  --accent:#4c6a63;
  --accent-soft:#dce9e6;
  --line:#e3dbd3;
  --radius:16px;
}}
*{{box-sizing:border-box;}}
body{{font-family: Inter, system-ui, -apple-system, sans-serif;background:var(--bg);color:var(--ink);margin:0;}}
main{{max-width:1100px;margin:0 auto;padding:24px;}}
header{{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:24px;}}
.brand h1{{margin:0;font-size:1.4rem;}}
.brand p{{margin:4px 0 0;color:var(--muted);font-size:.95rem;}}
.nav-right{{display:flex;align-items:center;gap:10px;}}
.hello{{color:var(--muted);font-size:.95rem;}}
button,.btn{{border:none;background:var(--accent);color:white;padding:10px 14px;border-radius:12px;cursor:pointer;font-weight:600;text-decoration:none;display:inline-block;}}
button:hover,.btn:hover{{opacity:.93;}}
.ghost{{background:transparent;border:1px solid var(--line);color:var(--ink);}}
.alert{{background:#fff7e6;border:1px solid #e6d3a4;color:#5e4a1a;}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:18px;box-shadow:0 4px 14px rgba(0,0,0,.04);}}
.grid{{display:grid;grid-template-columns:1.1fr 1.4fr;gap:18px;align-items:start;}}
label{{font-size:.9rem;font-weight:600;display:block;margin-bottom:6px;}}
input,textarea,select{{width:100%;padding:10px 11px;border:1px solid #d7d0c8;border-radius:12px;background:white;font:inherit;}}
textarea{{min-height:110px;resize:vertical;}}
.row{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;}}
.projects{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;}}
.project{{border:1px solid var(--line);border-radius:14px;padding:14px;background:white;position:relative;}}
.project.linked{{border-left:6px solid var(--accent);padding-left:12px;}}
.swatch{{width:14px;height:14px;border-radius:50%;display:inline-block;vertical-align:middle;margin-right:8px;border:1px solid #0002;}}
.meta{{font-size:.85rem;color:var(--muted);display:flex;flex-wrap:wrap;gap:9px;margin-top:10px;}}
.rel-badge{{display:inline-block;background:#edf4f2;color:#325149;border:1px solid #c8dbd7;padding:5px 8px;border-radius:999px;font-size:.78rem;font-weight:600;margin-top:8px;}}
.rel-panel{{margin-bottom:14px;padding:14px;border:1px solid #d6e3df;background:#f2f8f6;border-radius:14px;}}
.rel-panel h3{{margin:0 0 8px;font-size:1rem;}}
.rel-list{{margin:8px 0 0 0;padding-left:18px;display:grid;gap:6px;}}
.rel-list li{{color:#314740;}}
.actions{{display:flex;gap:8px;margin-top:12px;}}
.flash{{background:var(--accent-soft);border:1px solid #bdd5d0;padding:11px 12px;border-radius:12px;margin-bottom:14px;}}
footer{{text-align:center;color:var(--muted);padding:18px;}}
@media (max-width:860px){{.grid{{grid-template-columns:1fr;}} .row{{grid-template-columns:1fr;}} header{{flex-direction:column;align-items:flex-start;}}}}
</style>
</head>
<body>
<main>
<header>
  <div class='brand'>
    <h1>Idea Harbor</h1>
    <p>Capture your thoughts without losing focus.</p>
  </div>
  {nav}
</header>
{flash_html}
{body}
</main>
<footer>Built for calm, focused planning across desktop and mobile.</footer>
</body>
</html>"""


def auth_page(message="", signup=False):
    extra = "<p>Create your personal account to start.</p>" if signup else "<p>Log in and unload your ideas quickly.</p>"
    action = "/signup" if signup else "/login"
    cta = "Create account" if signup else "Log in"
    toggle = (
        "<a href='/login' class='btn ghost'>I already have an account</a>"
        if signup
        else "<a href='/signup' class='btn ghost'>Create first account</a>"
    )
    body = f"""
    <section class='card' style='max-width:460px;margin:30px auto;'>
      <h2>{'Create your account' if signup else 'Welcome back'}</h2>
      {extra}
      {f"<div class='flash'>{html.escape(message)}</div>" if message else ''}
      <form method='POST' action='{action}'>
        <p><label>Username</label><input name='username' required minlength='3'></p>
        <p><label>Password</label><input name='password' type='password' required minlength='8'></p>
        <button>{cta}</button>
      </form>
      <div style='margin-top:12px;'>{toggle}</div>
    </section>
    """
    return layout("Account", body)


def dashboard_page(user, flash="", edit_idea=None):
    conn = db()
    conn.execute("PRAGMA foreign_keys = ON")
    ideas = conn.execute(
        """
        SELECT i.*, rel.name AS related_name
        FROM ideas i
        LEFT JOIN ideas rel ON rel.id = i.related_idea_id
        WHERE i.user_id = ?
        ORDER BY i.priority DESC, i.created_at DESC
        """,
        (user["id"],),
    ).fetchall()
    conn.close()

    relation_text, detail, relation_items = relationship_summary(ideas)

    form_action = "/ideas/update" if edit_idea else "/ideas"
    form_title = "Edit idea" if edit_idea else "Quick capture"
    submit_text = "Save changes" if edit_idea else "Save idea"

    option_rows = ["<option value=''>No relation</option>"]
    editing_id = edit_idea["id"] if edit_idea else None
    for idea in ideas:
        if editing_id and idea["id"] == editing_id:
            continue
        selected = ""
        if edit_idea and edit_idea["related_idea_id"] == idea["id"]:
            selected = " selected"
        option_rows.append(
            f"<option value='{idea['id']}'{selected}>{html.escape(idea['name'])}</option>"
        )

    items = ""
    for idea in ideas:
        linked_class = " linked" if idea["related_idea_id"] else ""
        relation_badge = (
            f"<div class='rel-badge'>Connected to: {html.escape(idea['related_name'])}</div>"
            if idea["related_name"]
            else ""
        )
        items += f"""
        <article class='project{linked_class}'>
            <h3><span class='swatch' style='background:{html.escape(idea['color'])}'></span>{html.escape(idea['name'])}</h3>
            <p>{html.escape(idea['description'])}</p>
            {relation_badge}
            <div class='meta'>
               <span>Feasibility: {idea['feasibility']}/10</span>
               <span>Difficulty: {idea['difficulty']}/10</span>
               <span>Priority: {idea['priority']}/10</span>
            </div>
            <div class='actions'>
              <a class='btn ghost' href='/?edit={idea['id']}'>Edit</a>
              <form method='POST' action='/delete'>
                 <input type='hidden' name='id' value='{idea['id']}'>
                 <button class='ghost'>Remove</button>
              </form>
            </div>
        </article>
        """

    if not items:
        items = "<p>No ideas yet. Add your first one and keep your flow uninterrupted.</p>"

    body = f"""
    <div class='grid'>
      <section class='card'>
        <h2>{form_title}</h2>
        {"<div class='flash alert'>You are editing an existing idea.</div>" if edit_idea else ""}
        <form method='POST' action='{form_action}'>
          {f"<input type='hidden' name='id' value='{edit_idea['id']}'>" if edit_idea else ''}
          <p><label>Name</label><input name='name' required maxlength='120' value='{html.escape((edit_idea['name'] if edit_idea else ''))}'></p>
          <p><label>Color</label><input type='color' name='color' value='{html.escape((edit_idea['color'] if edit_idea else '#4c6a63'))}'></p>
          <p><label>Description</label><textarea name='description' required maxlength='1000'>{html.escape((edit_idea['description'] if edit_idea else ''))}</textarea></p>
          <p><label>Relationship / connection</label>
            <select name='related_idea_id'>
              {''.join(option_rows)}
            </select>
          </p>
          <div class='row'>
            <p><label>Feasibility</label><input type='number' min='1' max='10' name='feasibility' value='{edit_idea['feasibility'] if edit_idea else 5}' required></p>
            <p><label>Difficulty</label><input type='number' min='1' max='10' name='difficulty' value='{edit_idea['difficulty'] if edit_idea else 5}' required></p>
            <p><label>Priority</label><input type='number' min='1' max='10' name='priority' value='{edit_idea['priority'] if edit_idea else 5}' required></p>
          </div>
          <button>{submit_text}</button>
          {"<a class='btn ghost' style='margin-left:8px;' href='/'>Cancel</a>" if edit_idea else ""}
        </form>
      </section>
      <section class='card'>
        <h2>Ideas & projects</h2>
        <div class='rel-panel'>
          <h3>Relationship map</h3>
          <div><strong>{html.escape(relation_text)}</strong></div>
          <div style='color:#4e5d58;margin-top:3px;'>{html.escape(detail)}</div>
          <ul class='rel-list'>{relation_items}</ul>
        </div>
        <div class='projects'>{items}</div>
      </section>
    </div>
    """
    return layout("Idea Harbor", body, username=user["username"], flash=flash)


def app(environ, start_response):
    url = urlparse(environ.get("PATH_INFO", "/") + ("?" + environ.get("QUERY_STRING", "") if environ.get("QUERY_STRING") else ""))
    path = url.path
    query = parse_qs(url.query)
    method = environ.get("REQUEST_METHOD", "GET").upper()
    user = get_session_user(environ)

    conn = db()
    conn.execute("PRAGMA foreign_keys = ON")
    user_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    conn.close()

    if path == "/" and method == "GET":
        if user:
            edit_idea = None
            edit_id = (query.get("edit") or [""])[0]
            if edit_id.isdigit():
                conn = db()
                conn.execute("PRAGMA foreign_keys = ON")
                edit_idea = conn.execute(
                    "SELECT * FROM ideas WHERE id = ? AND user_id = ?",
                    (int(edit_id), user["id"]),
                ).fetchone()
                conn.close()
            html_doc = dashboard_page(user, edit_idea=edit_idea)
        else:
            html_doc = auth_page(signup=user_count == 0)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [html_doc.encode("utf-8")]

    if path == "/login" and method == "GET":
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [auth_page().encode("utf-8")]

    if path == "/signup" and method == "GET":
        if user_count > 0:
            return redirect(start_response, "/login")
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [auth_page(signup=True).encode("utf-8")]

    if path == "/signup" and method == "POST":
        if user_count > 0:
            return redirect(start_response, "/login")
        data = form_data(environ)
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if len(username) < 3 or len(password) < 8:
            start_response("400 Bad Request", [("Content-Type", "text/html; charset=utf-8")])
            return [auth_page("Username or password is too short.", signup=True).encode("utf-8")]

        conn = db()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO users(username, password, created_at) VALUES (?, ?, ?)",
            (username, hash_password(password), datetime.utcnow().isoformat()),
        )
        uid = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()["id"]
        conn.commit()
        conn.close()
        headers = set_session_headers(uid)
        return redirect(start_response, "/", headers)

    if path == "/login" and method == "POST":
        data = form_data(environ)
        conn = db()
        conn.execute("PRAGMA foreign_keys = ON")
        row = conn.execute(
            "SELECT id, username, password FROM users WHERE username = ?",
            (data.get("username", "").strip(),),
        ).fetchone()
        conn.close()
        if not row or not verify_password(data.get("password", ""), row["password"]):
            start_response("401 Unauthorized", [("Content-Type", "text/html; charset=utf-8")])
            return [auth_page("Invalid credentials.").encode("utf-8")]
        headers = set_session_headers(row["id"])
        return redirect(start_response, "/", headers)

    if path == "/logout" and method == "POST":
        headers = clear_session_headers(environ)
        return redirect(start_response, "/login", headers)

    if path == "/ideas" and method == "POST":
        if not user:
            return redirect(start_response, "/login")
        data = form_data(environ)
        related = data.get("related_idea_id", "").strip()
        related_id = int(related) if related.isdigit() else None
        conn = db()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO ideas(user_id, name, color, description, related_idea_id, feasibility, difficulty, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                data.get("name", "Untitled")[:120],
                data.get("color", "#4c6a63"),
                data.get("description", "")[:1000],
                related_id,
                num_value(data.get("feasibility", "5")),
                num_value(data.get("difficulty", "5")),
                num_value(data.get("priority", "5")),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        return redirect(start_response, "/")

    if path == "/ideas/update" and method == "POST":
        if not user:
            return redirect(start_response, "/login")
        data = form_data(environ)
        if not data.get("id", "").isdigit():
            return redirect(start_response, "/")

        idea_id = int(data["id"])
        related = data.get("related_idea_id", "").strip()
        related_id = int(related) if related.isdigit() else None
        if related_id == idea_id:
            related_id = None

        conn = db()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            UPDATE ideas
            SET name = ?, color = ?, description = ?, related_idea_id = ?, feasibility = ?, difficulty = ?, priority = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                data.get("name", "Untitled")[:120],
                data.get("color", "#4c6a63"),
                data.get("description", "")[:1000],
                related_id,
                num_value(data.get("feasibility", "5")),
                num_value(data.get("difficulty", "5")),
                num_value(data.get("priority", "5")),
                idea_id,
                user["id"],
            ),
        )
        conn.commit()
        conn.close()
        return redirect(start_response, "/")

    if path == "/delete" and method == "POST":
        if not user:
            return redirect(start_response, "/login")
        data = form_data(environ)
        if data.get("id", "").isdigit():
            conn = db()
            conn.execute("PRAGMA foreign_keys = ON")
            delete_id = int(data["id"])
            conn.execute(
                "UPDATE ideas SET related_idea_id = NULL WHERE user_id = ? AND related_idea_id = ?",
                (user["id"], delete_id),
            )
            conn.execute(
                "DELETE FROM ideas WHERE id = ? AND user_id = ?",
                (delete_id, user["id"]),
            )
            conn.commit()
            conn.close()
        return redirect(start_response, "/")

    # Preview-friendly fallback for unknown GET routes.
    if method == "GET":
        html_doc = dashboard_page(user) if user else auth_page(signup=user_count == 0)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [html_doc.encode("utf-8")]

    start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
    return [b"Not Found"]


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    print(f"Idea Harbor running on http://0.0.0.0:{port}")
    with make_server("0.0.0.0", port, app) as server:
        server.serve_forever()
