"""
setup/oauth_setup.py — Interactive OAuth Setup CLI
Gold Tier — Panaversity AI Employee Hackathon 2026

Run: python setup/oauth_setup.py

Guides through LinkedIn, Twitter, Facebook/Instagram OAuth setup.
Saves credentials to .env automatically.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional

# Rich for pretty output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    console = Console()
except ImportError:
    class Console:
        def print(self, *a, **k): print(*a)
        def rule(self, *a, **k): print("─" * 60)
    class Panel:
        def __init__(self, t, **k): self.t = t
        def __str__(self): return str(self.t)
    class Prompt:
        @staticmethod
        def ask(prompt, default=""): return input(f"{prompt} [{default}]: ") or default
    class Confirm:
        @staticmethod
        def ask(prompt): return input(f"{prompt} [y/N]: ").lower() == "y"
    console = Console()

ENV_FILE = Path(os.environ.get("ENV_FILE", ".env"))

# ─────────────────────────────────────────────────────────────
# .env helpers
# ─────────────────────────────────────────────────────────────

def read_env() -> dict:
    """Read all key=value pairs from .env file."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def save_env(updates: dict) -> None:
    """Update or add keys in .env file."""
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Add new keys
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    console.print(f"[green]✓ Saved to {ENV_FILE}[/green]")


# ─────────────────────────────────────────────────────────────
# Local OAuth callback server
# ─────────────────────────────────────────────────────────────

_oauth_code: Optional[str] = None
_oauth_state: Optional[str] = None


class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _oauth_code, _oauth_state
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _oauth_code = params.get("code", [None])[0]
        _oauth_state = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"""
        <html><body style='font-family:sans-serif;text-align:center;padding:40px'>
        <h2 style='color:#7c3aed'>Authorization Successful!</h2>
        <p>You can close this tab and return to the terminal.</p>
        </body></html>""")

    def log_message(self, *_):
        pass  # suppress request logging


def wait_for_oauth_code(port: int = 8080, timeout: int = 120) -> Optional[str]:
    """Start local server, wait for OAuth redirect, return authorization code."""
    global _oauth_code
    _oauth_code = None
    server = http.server.HTTPServer(("localhost", port), _OAuthCallbackHandler)
    server.timeout = timeout
    server.handle_request()
    return _oauth_code


# ─────────────────────────────────────────────────────────────
# LINKEDIN SETUP
# ─────────────────────────────────────────────────────────────

def setup_linkedin() -> None:
    console.rule("[bold blue]LinkedIn OAuth Setup[/bold blue]")
    console.print(Panel(
        "1. Open [link=https://www.linkedin.com/developers/apps]https://www.linkedin.com/developers/apps[/link]\n"
        "2. Create/select your App\n"
        "3. Add products: Share on LinkedIn, Sign In with LinkedIn\n"
        "4. Auth tab → Redirect URL: [bold]http://localhost:8080/callback[/bold]\n"
        "5. Copy Client ID & Client Secret below",
        title="LinkedIn Setup Instructions",
        border_style="blue",
    ))

    client_id = Prompt.ask("Enter LinkedIn Client ID")
    client_secret = Prompt.ask("Enter LinkedIn Client Secret")

    scopes = "r_liteprofile,r_emailaddress,w_member_social"
    state = "ai_employee_li_setup"
    redirect_uri = "http://localhost:8080/callback"

    auth_url = (
        f"https://www.linkedin.com/oauth/v2/authorization"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&state={state}"
        f"&scope={urllib.parse.quote(scopes)}"
    )

    console.print(f"\n[yellow]Opening browser for LinkedIn authorization…[/yellow]")
    webbrowser.open(auth_url)
    console.print("[dim]Waiting for authorization (120s timeout)…[/dim]")

    code = wait_for_oauth_code()
    if not code:
        console.print("[red]✗ Authorization timed out or failed[/red]")
        return

    # Exchange code for tokens
    try:
        import requests
        resp = requests.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
            timeout=20,
        )
        resp.raise_for_status()
        tokens = resp.json()
        access_token = tokens.get("access_token", "")
        refresh_token = tokens.get("refresh_token", "")

        # Get profile
        profile_resp = requests.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        profile_resp.raise_for_status()
        profile = profile_resp.json()
        name = f"{profile.get('localizedFirstName', '')} {profile.get('localizedLastName', '')}".strip()
        person_id = profile.get("id", "")
        person_urn = f"urn:li:person:{person_id}"

        save_env({
            "LINKEDIN_CLIENT_ID": client_id,
            "LINKEDIN_CLIENT_SECRET": client_secret,
            "LINKEDIN_ACCESS_TOKEN": access_token,
            "LINKEDIN_REFRESH_TOKEN": refresh_token,
            "LINKEDIN_PERSON_URN": person_urn,
        })
        console.print(f"[bold green]✅ LinkedIn connected as \"{name}\" ({person_urn})[/bold green]")

    except Exception as exc:
        console.print(f"[red]✗ Token exchange failed: {exc}[/red]")


# ─────────────────────────────────────────────────────────────
# TWITTER SETUP
# ─────────────────────────────────────────────────────────────

def setup_twitter() -> None:
    console.rule("[bold cyan]Twitter/X OAuth Setup[/bold cyan]")
    console.print(Panel(
        "1. Open [link=https://developer.twitter.com/en/portal/dashboard]developer.twitter.com[/link]\n"
        "2. Create Project → Create App\n"
        "3. Set User Authentication: Read + Write + Direct Message\n"
        "4. Callback URL: [bold]http://localhost:8080/callback[/bold]\n"
        "5. Copy all 5 credentials below",
        title="Twitter/X Setup Instructions",
        border_style="cyan",
    ))

    api_key = Prompt.ask("Twitter API Key (Consumer Key)")
    api_secret = Prompt.ask("Twitter API Secret (Consumer Secret)")
    bearer_token = Prompt.ask("Twitter Bearer Token")
    access_token = Prompt.ask("Twitter Access Token")
    access_token_secret = Prompt.ask("Twitter Access Token Secret")

    # Verify
    try:
        import tweepy
        client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        me = client.get_me()
        username = me.data.username if me and me.data else "unknown"
        user_id = str(me.data.id) if me and me.data else ""

        save_env({
            "TWITTER_API_KEY": api_key,
            "TWITTER_API_SECRET": api_secret,
            "TWITTER_BEARER_TOKEN": bearer_token,
            "TWITTER_ACCESS_TOKEN": access_token,
            "TWITTER_ACCESS_TOKEN_SECRET": access_token_secret,
            "TWITTER_MY_USER_ID": user_id,
        })
        console.print(f"[bold green]✅ Twitter connected as @{username} (id={user_id})[/bold green]")

    except ImportError:
        console.print("[yellow]tweepy not installed — saving credentials without verification[/yellow]")
        save_env({
            "TWITTER_API_KEY": api_key,
            "TWITTER_API_SECRET": api_secret,
            "TWITTER_BEARER_TOKEN": bearer_token,
            "TWITTER_ACCESS_TOKEN": access_token,
            "TWITTER_ACCESS_TOKEN_SECRET": access_token_secret,
        })
    except Exception as exc:
        console.print(f"[red]✗ Twitter verification failed: {exc}[/red]")


# ─────────────────────────────────────────────────────────────
# FACEBOOK + INSTAGRAM SETUP
# ─────────────────────────────────────────────────────────────

def setup_facebook_instagram() -> None:
    console.rule("[bold blue]Facebook + Instagram Setup[/bold blue]")
    console.print(Panel(
        "1. Open [link=https://developers.facebook.com/apps]developers.facebook.com/apps[/link]\n"
        "2. Create App → Business type\n"
        "3. Add: Facebook Login + Instagram Graph API products\n"
        "4. Go to Graph API Explorer\n"
        "5. Generate User Token with these permissions:\n"
        "   pages_show_list, pages_read_engagement, pages_manage_posts,\n"
        "   pages_messaging, instagram_basic, instagram_content_publish,\n"
        "   instagram_manage_comments, instagram_manage_messages\n"
        "6. Enter App ID, App Secret, and the short-lived token below",
        title="Facebook + Instagram Setup Instructions",
        border_style="blue",
    ))

    app_id = Prompt.ask("Facebook App ID")
    app_secret = Prompt.ask("Facebook App Secret")
    short_token = Prompt.ask("Short-lived User Access Token (from Graph API Explorer)")

    import requests

    # Exchange for long-lived token
    try:
        resp = requests.get(
            "https://graph.facebook.com/v19.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        long_token = resp.json().get("access_token", short_token)
        console.print("[green]✓ Long-lived token obtained (60 days)[/green]")
    except Exception as exc:
        console.print(f"[yellow]Token exchange failed: {exc} — using short-lived token[/yellow]")
        long_token = short_token

    # Get Page list
    try:
        pages_resp = requests.get(
            "https://graph.facebook.com/v19.0/me/accounts",
            params={"access_token": long_token},
            timeout=10,
        )
        pages_resp.raise_for_status()
        pages = pages_resp.json().get("data", [])
        if not pages:
            console.print("[yellow]No pages found — enter Page ID manually[/yellow]")
            page_id = Prompt.ask("Facebook Page ID")
            page_token = long_token
        else:
            console.print("\nYour Facebook Pages:")
            for i, page in enumerate(pages):
                console.print(f"  [{i+1}] {page.get('name')} (id={page.get('id')})")
            choice = int(Prompt.ask("Select page number", default="1")) - 1
            page = pages[choice]
            page_id = page.get("id", "")
            page_token = page.get("access_token", long_token)
            console.print(f"[green]✓ Page selected: {page.get('name')} ({page_id})[/green]")
    except Exception as exc:
        console.print(f"[yellow]Could not list pages: {exc}[/yellow]")
        page_id = Prompt.ask("Facebook Page ID")
        page_token = long_token

    # Get Instagram Business Account
    ig_account_id = ""
    try:
        ig_resp = requests.get(
            f"https://graph.facebook.com/v19.0/{page_id}",
            params={"fields": "instagram_business_account", "access_token": page_token},
            timeout=10,
        )
        ig_resp.raise_for_status()
        ig_data = ig_resp.json().get("instagram_business_account", {})
        ig_account_id = ig_data.get("id", "")
        if ig_account_id:
            console.print(f"[green]✓ Instagram Business Account: {ig_account_id}[/green]")
        else:
            console.print("[yellow]No Instagram Business Account linked to this page[/yellow]")
            ig_account_id = Prompt.ask("Instagram Business Account ID (optional)", default="")
    except Exception:
        ig_account_id = Prompt.ask("Instagram Business Account ID (optional)", default="")

    save_env({
        "FACEBOOK_APP_ID": app_id,
        "FACEBOOK_APP_SECRET": app_secret,
        "FACEBOOK_PAGE_ID": page_id,
        "FACEBOOK_PAGE_ACCESS_TOKEN": page_token,
        "FACEBOOK_LONG_LIVED_TOKEN": long_token,
        "INSTAGRAM_BUSINESS_ACCOUNT_ID": ig_account_id,
        "INSTAGRAM_ACCESS_TOKEN": page_token,
    })

    # Final verification
    try:
        me = requests.get(
            f"https://graph.facebook.com/v19.0/{page_id}",
            params={"fields": "name", "access_token": page_token},
            timeout=10,
        ).json()
        console.print(f"[bold green]✅ Facebook Page: \"{me.get('name')}\"[/bold green]")
        if ig_account_id:
            ig_me = requests.get(
                f"https://graph.facebook.com/v19.0/{ig_account_id}",
                params={"fields": "username", "access_token": page_token},
                timeout=10,
            ).json()
            console.print(f"[bold green]✅ Instagram: @{ig_me.get('username', ig_account_id)}[/bold green]")
    except Exception as exc:
        console.print(f"[yellow]Verification check: {exc}[/yellow]")


# ─────────────────────────────────────────────────────────────
# TEST ALL CONNECTIONS
# ─────────────────────────────────────────────────────────────

def test_all_connections() -> None:
    console.rule("[bold green]Testing All Connections[/bold green]")
    env = read_env()
    import requests as req

    # LinkedIn
    li_token = env.get("LINKEDIN_ACCESS_TOKEN", "")
    if li_token and not li_token.endswith("..."):
        try:
            resp = req.get(
                "https://api.linkedin.com/v2/me",
                headers={"Authorization": f"Bearer {li_token}"},
                timeout=10,
            )
            resp.raise_for_status()
            p = resp.json()
            name = f"{p.get('localizedFirstName', '')} {p.get('localizedLastName', '')}".strip()
            console.print(f"[bold green]✅ LinkedIn connected as \"{name}\"[/bold green]")
        except Exception as exc:
            console.print(f"[red]✗ LinkedIn: {exc}[/red]")
    else:
        console.print("[yellow]⚠ LinkedIn: not configured[/yellow]")

    # Twitter
    bearer = env.get("TWITTER_BEARER_TOKEN", "")
    if bearer and not bearer.endswith("..."):
        try:
            import tweepy
            client = tweepy.Client(bearer_token=bearer)
            me = client.get_me()
            if me and me.data:
                console.print(f"[bold green]✅ Twitter connected as @{me.data.username}[/bold green]")
        except Exception as exc:
            console.print(f"[red]✗ Twitter: {exc}[/red]")
    else:
        console.print("[yellow]⚠ Twitter: not configured[/yellow]")

    # Facebook
    fb_token = env.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    fb_page_id = env.get("FACEBOOK_PAGE_ID", "")
    if fb_token and fb_page_id and not fb_token.endswith("..."):
        try:
            resp = req.get(
                f"https://graph.facebook.com/v19.0/{fb_page_id}",
                params={"fields": "name", "access_token": fb_token},
                timeout=10,
            )
            resp.raise_for_status()
            page_name = resp.json().get("name", "")
            console.print(f"[bold green]✅ Facebook Page: \"{page_name}\"[/bold green]")
        except Exception as exc:
            console.print(f"[red]✗ Facebook: {exc}[/red]")
    else:
        console.print("[yellow]⚠ Facebook: not configured[/yellow]")

    # Instagram
    ig_id = env.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    ig_token = env.get("INSTAGRAM_ACCESS_TOKEN", "")
    if ig_id and ig_token and not ig_token.endswith("..."):
        try:
            resp = req.get(
                f"https://graph.facebook.com/v19.0/{ig_id}",
                params={"fields": "username,followers_count", "access_token": ig_token},
                timeout=10,
            )
            resp.raise_for_status()
            d = resp.json()
            console.print(
                f"[bold green]✅ Instagram: @{d.get('username')} "
                f"({d.get('followers_count', 0)} followers)[/bold green]"
            )
        except Exception as exc:
            console.print(f"[red]✗ Instagram: {exc}[/red]")
    else:
        console.print("[yellow]⚠ Instagram: not configured[/yellow]")


# ─────────────────────────────────────────────────────────────
# REFRESH ALL TOKENS
# ─────────────────────────────────────────────────────────────

def refresh_all_tokens() -> None:
    console.rule("[bold yellow]Refreshing Tokens[/bold yellow]")
    env = read_env()

    # LinkedIn refresh
    refresh_token = env.get("LINKEDIN_REFRESH_TOKEN", "")
    client_id = env.get("LINKEDIN_CLIENT_ID", "")
    client_secret = env.get("LINKEDIN_CLIENT_SECRET", "")
    if refresh_token and client_id:
        try:
            import requests
            resp = requests.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=15,
            )
            resp.raise_for_status()
            new_token = resp.json().get("access_token", "")
            if new_token:
                save_env({"LINKEDIN_ACCESS_TOKEN": new_token})
                console.print("[green]✓ LinkedIn token refreshed[/green]")
        except Exception as exc:
            console.print(f"[red]✗ LinkedIn refresh failed: {exc}[/red]")

    console.print("[dim]Note: Twitter tokens don't expire. Facebook tokens last 60 days.[/dim]")


# ─────────────────────────────────────────────────────────────
# MAIN MENU
# ─────────────────────────────────────────────────────────────

def main() -> None:
    console.print(Panel.fit(
        "[bold purple]AI Employee — OAuth Setup Wizard[/bold purple]\n"
        "Connect your social media accounts",
        border_style="purple",
    ))

    while True:
        console.print("\n[bold]Select an option:[/bold]")
        console.print("  [cyan]1[/cyan] Setup LinkedIn OAuth")
        console.print("  [cyan]2[/cyan] Setup Twitter/X OAuth")
        console.print("  [cyan]3[/cyan] Setup Facebook + Instagram")
        console.print("  [cyan]4[/cyan] Test All Connections")
        console.print("  [cyan]5[/cyan] Refresh All Tokens")
        console.print("  [cyan]q[/cyan] Quit\n")

        choice = Prompt.ask("Choice", default="4")

        if choice == "1":
            setup_linkedin()
        elif choice == "2":
            setup_twitter()
        elif choice == "3":
            setup_facebook_instagram()
        elif choice == "4":
            test_all_connections()
        elif choice == "5":
            refresh_all_tokens()
        elif choice.lower() == "q":
            console.print("[bold green]Setup complete! Run: python orchestrator.py[/bold green]")
            break
        else:
            console.print("[yellow]Invalid choice[/yellow]")


if __name__ == "__main__":
    main()
