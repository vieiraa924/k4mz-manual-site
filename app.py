
import os
import secrets
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET", "CHANGE_ME")

API = "https://discord.com/api/v10"

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
VERIFIED_ROLE_ID = os.getenv("VERIFIED_ROLE_ID", "")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "")
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
OWNER_DISCORD_ID = os.getenv("OWNER_DISCORD_ID", "")

import json
from pathlib import Path

SETTINGS_FILE = Path("/home/k4mzrl/k4mz-manual-site/settings.json")

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            return json.loads(
                SETTINGS_FILE.read_text(encoding="utf-8")
            )
        except:
            pass

    return {
        "welcome_enabled": True,
        "welcome_channel_id": "",
        "welcome_message": "Bem-vindo {mention} ao servidor!"
    }

def save_settings(data):
    SETTINGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

import json
from pathlib import Path

SETTINGS_FILE = Path("/home/k4mzrl/k4mz-manual-site/settings.json")

def bot_headers():
    return {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}

@app.get("/")
def home():
    return render_template("index.html", user=session.get("discord_user"))

@app.get("/login")
def login():
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session["return_to"] = request.args.get("return_to", "/verify")
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "identify",
        "state": state,
        "prompt": "consent",
    }
    return redirect("https://discord.com/oauth2/authorize?" + urlencode(params))

@app.get("/callback")
def callback():
    if request.args.get("state") != session.get("oauth_state"):
        return render_template("result.html", ok=False, title="OAuth inválido", message="State inválido."), 400

    code = request.args.get("code")
    if not code:
        return redirect(url_for("home"))

    r = requests.post(
        "https://discord.com/api/oauth2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    if r.status_code != 200:
        return render_template("result.html", ok=False, title="Erro no Discord", message="Não foi possível concluir o login."), 400

    access_token = r.json()["access_token"]
    u = requests.get(f"{API}/users/@me", headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    if u.status_code != 200:
        return render_template("result.html", ok=False, title="Erro no Discord", message="Não foi possível obter a tua conta."), 400

    user = u.json()
    session["discord_user"] = {
        "id": user["id"],
        "username": user["username"],
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
    }
    return redirect(session.pop("return_to", "/verify"))

@app.get("/verify")
def verify_page():
    user = session.get("discord_user")
    if not user:
        return redirect(url_for("login", return_to="/verify"))
    return render_template("verify.html", user=user, turnstile_site_key=TURNSTILE_SITE_KEY)

@app.post("/verify")
def verify_submit():
    user = session.get("discord_user")
    if not user:
        return redirect(url_for("login", return_to="/verify"))

    token = request.form.get("cf-turnstile-response", "")
    vr = requests.post(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data={
            "secret": TURNSTILE_SECRET_KEY,
            "response": token,
            "remoteip": request.headers.get("CF-Connecting-IP") or request.remote_addr,
        },
        timeout=15,
    )
    if not vr.ok or not vr.json().get("success"):
        return render_template("result.html", ok=False, title="CAPTCHA inválido", message="Tenta novamente."), 400

    uid = user["id"]
    member = requests.get(f"{API}/guilds/{GUILD_ID}/members/{uid}", headers=bot_headers(), timeout=15)
    if member.status_code != 200:
        return render_template("result.html", ok=False, title="Ainda não estás no servidor", message="Entra no servidor e tenta novamente."), 400

    role = requests.put(
        f"{API}/guilds/{GUILD_ID}/members/{uid}/roles/{VERIFIED_ROLE_ID}",
        headers=bot_headers(),
        timeout=15,
    )
    if role.status_code != 204:
        return render_template("result.html", ok=False, title="Erro na role", message="O bot não conseguiu atribuir Verified."), 500

    return render_template("result.html", ok=True, title="Verificado", message="A role Verified foi atribuída com sucesso.")

@app.get("/dashboard")
def dashboard():
    user = session.get("discord_user")
    if not user:
        return redirect(url_for("login", return_to="/dashboard"))
    if str(user["id"]) != str(OWNER_DISCORD_ID):
        return render_template("denied.html"), 403

    guild = requests.get(f"{API}/guilds/{GUILD_ID}?with_counts=true", headers=bot_headers(), timeout=15)
    guild_data = guild.json() if guild.status_code == 200 else None
    return render_template("dashboard.html", user=user, guild=guild_data)
@app.route("/dashboard/welcome", methods=["GET", "POST"])
def dashboard_welcome():
    user = session.get("discord_user")

    if not user:
        return redirect(url_for("login", return_to="/dashboard/welcome"))

    if str(user["id"]) != str(OWNER_DISCORD_ID):
        return render_template("denied.html"), 403

    channels_request = requests.get(
        f"{API}/guilds/{GUILD_ID}/channels",
        headers=bot_headers(),
        timeout=15
    )

    channels = []
    if channels_request.status_code == 200:
        channels = [
            c for c in channels_request.json()
            if c.get("type") == 0
        ]

    settings = load_settings()

    if request.method == "POST":
        settings["welcome_enabled"] = request.form.get("welcome_enabled") == "on"
        settings["welcome_channel_id"] = request.form.get(
            "welcome_channel_id", ""
        )
        settings["welcome_message"] = request.form.get(
            "welcome_message", ""
        ).strip()

        save_settings(settings)
        return redirect(url_for("dashboard_welcome"))

    return render_template(
        "welcome.html",
        user=user,
        channels=channels,
        settings=settings
    )
@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.get("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
