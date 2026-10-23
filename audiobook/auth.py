"""How the narrator signs in to Claude.

Default: an OAuth profile from `ant auth login` (the Anthropic CLI). You sign in once in the
browser; no API key is stored by you or by this app. The Anthropic SDK reads the profile from
~/.config/anthropic/ and refreshes the short-lived token itself.

Fallback: ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) from the environment.

Note: this is a Claude Platform (Console) sign-in, billed to that account's workspace. Anthropic
does not allow third-party apps to sign in with a claude.ai Pro/Max subscription unless approved.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import anthropic

INSTALL_HINT = (
    "Install the Anthropic CLI first:\n"
    "  macOS:  brew install anthropics/tap/ant\n"
    "  other:  https://github.com/anthropics/anthropic-cli/releases"
)


@dataclass
class Credential:
    kind: str  # "oauth-profile", "api-key", "auth-token" or "none"
    detail: str = ""


def config_dir() -> Path:
    if os.environ.get("ANTHROPIC_CONFIG_DIR"):
        return Path(os.environ["ANTHROPIC_CONFIG_DIR"])
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "Anthropic"
    return Path.home() / ".config" / "anthropic"


def oauth_profile() -> str | None:
    """Name of the OAuth profile the CLI would use, if one has credentials on disk."""
    base = config_dir()
    name = os.environ.get("ANTHROPIC_PROFILE")
    if not name:
        pointer = base / "active_config"
        name = pointer.read_text(encoding="utf-8").strip() if pointer.exists() else "default"
    has_files = (base / "configs" / f"{name}.json").exists() and (base / "credentials" / f"{name}.json").exists()
    return name if has_files else None


def current_credential() -> Credential:
    profile = oauth_profile()
    if profile:
        return Credential("oauth-profile", profile)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return Credential("api-key", "ANTHROPIC_API_KEY")
    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return Credential("auth-token", "ANTHROPIC_AUTH_TOKEN")
    return Credential("none")


def make_client() -> anthropic.Anthropic:
    """An Anthropic client that prefers the OAuth profile over an API key in the environment."""
    cred = current_credential()
    if cred.kind == "oauth-profile":
        # An explicit profile beats ANTHROPIC_API_KEY, which the SDK would otherwise pick first.
        return anthropic.Anthropic(profile=cred.detail)
    if cred.kind == "none":
        raise RuntimeError("Not signed in to Claude. Run `audiobook login` (or set ANTHROPIC_API_KEY).")
    return anthropic.Anthropic()


def login(no_browser: bool = False, profile: str | None = None) -> int:
    ant = shutil.which("ant")
    if not ant:
        print(INSTALL_HINT)
        return 1
    cmd = [ant, "auth", "login"]
    if no_browser:
        cmd.append("--no-browser")
    if profile:
        cmd += ["--profile", profile]
    return subprocess.call(cmd)


def logout() -> int:
    ant = shutil.which("ant")
    if not ant:
        print(INSTALL_HINT)
        return 1
    return subprocess.call([ant, "auth", "logout"])


def status_text() -> str:
    cred = current_credential()
    if cred.kind == "oauth-profile":
        text = f"Signed in with OAuth profile '{cred.detail}' ({config_dir()})."
        if os.environ.get("ANTHROPIC_API_KEY"):
            text += " ANTHROPIC_API_KEY is also set; the OAuth profile is used."
        return text
    if cred.kind == "none":
        return "Not signed in. Run `audiobook login`."
    return f"Using {cred.detail} from the environment (no OAuth profile found)."
