"""Command line entry point.

    audiobook make paper.pdf -o out/                       # Claude narrator, Explain mode, local Kokoro voice
    audiobook make paper.pdf --narrator rules --mode read  # fully offline
    audiobook script paper.pdf -o script.json              # write the narration script only
    audiobook voice script.json paper.pdf -o out/          # perform an existing (maybe hand-edited) script
    audiobook extract paper.pdf                            # show what the parser found
    audiobook login                                        # sign in to Claude with OAuth (browser)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import auth
from .extract import extract
from .model import Mode, Script
from .narrators import get_narrator
from .render import render
from .voices import get_voice


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="audiobook", description="Turn a PDF into a narrated audiobook.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="sign in to Claude with OAuth (uses the Anthropic CLI)")
    p_login.add_argument("--no-browser", action="store_true", help="print a URL and paste the code back")
    p_login.add_argument("--profile", help="profile name, if you use more than one")
    sub.add_parser("logout", help="sign out of the active OAuth profile")
    sub.add_parser("whoami", help="show how the narrator signs in to Claude")

    p_extract = sub.add_parser("extract", help="print the blocks found in a PDF")
    p_extract.add_argument("pdf", type=Path)
    p_extract.add_argument("--json", action="store_true")

    p_script = sub.add_parser("script", help="write the narration script for a PDF")
    p_script.add_argument("pdf", type=Path)
    p_script.add_argument("-o", "--output", type=Path, required=True)
    _narrator_args(p_script)

    p_voice = sub.add_parser("voice", help="perform an existing script")
    p_voice.add_argument("script", type=Path)
    p_voice.add_argument("pdf", type=Path)
    p_voice.add_argument("-o", "--out-dir", type=Path, required=True)
    _voice_args(p_voice)

    p_make = sub.add_parser("make", help="PDF in, narrated audiobook out")
    p_make.add_argument("pdf", type=Path)
    p_make.add_argument("-o", "--out-dir", type=Path, required=True)
    _narrator_args(p_make)
    _voice_args(p_make)

    args = parser.parse_args(argv)
    if args.command == "login":
        code = auth.login(no_browser=args.no_browser, profile=args.profile)
        print(auth.status_text())
        return code
    if args.command == "logout":
        return auth.logout()
    if args.command == "whoami":
        print(auth.status_text())
        return 0

    doc = extract(args.pdf)

    if args.command == "extract":
        if args.json:
            print(json.dumps([{**b.__dict__, "kind": b.kind.value} for b in doc.blocks], indent=2, ensure_ascii=False))
        else:
            print(f"{doc.title} ({doc.page_count} pages)")
            for b in doc.blocks:
                print(f"{b.id:>8}  {b.kind.value:<10} {b.text[:90]!r}")
        return 0

    if args.command == "voice":
        script = Script.load(args.script)
    else:
        script = _narrate(doc, args)
        if args.command == "script":
            script.save(args.output)
            print(f"wrote {args.output} ({len(script.segments)} segments)")
            return 0
        args.out_dir.mkdir(parents=True, exist_ok=True)
        script.save(args.out_dir / "script.json")  # saved before voicing so a voice failure never loses it

    print(f"voicing with {args.voice}", file=sys.stderr)
    book = render(doc, script, get_voice(args.voice, args.voice_name), args.out_dir, args.format)
    minutes = book["duration"] / 60
    print(f"wrote {len(book['chapters'])} chapters, {minutes:.1f} minutes, to {args.out_dir}/")
    return 0


def _narrate(doc, args) -> Script:
    mode = Mode(args.mode)
    kwargs = {"pages_per_call": args.pages_per_call} if args.narrator == "claude" else {}
    if args.narrator == "claude" and args.model:
        kwargs["model"] = args.model
    print(f"narrating {doc.page_count} pages with {args.narrator} ({mode.value} mode)", file=sys.stderr)
    return get_narrator(args.narrator, **kwargs).narrate(doc, mode)


def _narrator_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--narrator", choices=["claude", "rules"], default="claude")
    p.add_argument("--mode", choices=[m.value for m in Mode], default=Mode.EXPLAIN.value)
    p.add_argument("--model", help="Claude model id for the narrator")
    p.add_argument("--pages-per-call", type=int, default=2)


def _voice_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--voice", choices=["kokoro", "phonon", "openai", "elevenlabs", "silent"], default="kokoro")
    p.add_argument("--voice-name", help="voice within the engine, e.g. af_heart, am_michael, coral")
    p.add_argument("--format", choices=["mp3", "m4a", "wav"], default="mp3")


if __name__ == "__main__":
    sys.exit(main())
