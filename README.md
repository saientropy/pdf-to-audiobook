# pdf-to-audiobook

Turn any PDF into an audiobook you can listen to while you read along. It isn't plain
text-to-speech. An AI narrator looks at every page and reads it the way a good tutor would: it
skips the clutter, reads formulas as natural speech, and explains formulas, figures, tables and
code in plain words.

See [docs/spec.md](docs/spec.md) for the product plan.

```
PDF ──► extract ──► narrator (Claude + page images) ──► voice ──► chapter audio + book.json
        blocks,      what to say, what to explain       Kokoro,     sync map: every sentence's
        reading      and how to say it                  Phonon,     time and its spot on the page
        order                                           OpenAI,
                                                        ElevenLabs
```

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

export ANTHROPIC_API_KEY=...          # the narrator brain
audiobook make paper.pdf -o out/      # Explain mode, local Kokoro voice
```

The first run downloads the Kokoro voice model (about 120 MB) to `~/.cache/pdf-to-audiobook`.
`out/` then contains one MP3 per chapter, `script.json` (what the narrator says) and `book.json`
(the read-along sync map).

### Modes

| `--mode` | What you hear |
|---|---|
| `read` | A clean reading. Formulas are spoken naturally; figures and tables get a one-line mention. |
| `explain` (default) | Adds short asides that explain equations, describe figures, give a table's takeaway and say what code does. |
| `tutor` | Also defines jargon the first time it appears and recaps each section. |

### Fully offline

```bash
audiobook make paper.pdf --narrator rules --mode read -o out/
```

The rule-based narrator only does Read mode. Explanations need the LLM.

### Voices

| `--voice` | Where | Notes |
|---|---|---|
| `kokoro` (default) | Local, CPU | Kokoro-82M, Apache 2.0. `--voice-name af_heart`, `am_michael`, `bf_emma`, ... |
| `phonon` | Local server | Gradium Phonon 31m (Apache 2.0) through its OpenAI-compatible server. Set `PHONON_URL`. |
| `openai` | Cloud | gpt-4o-mini-tts. It follows the narrator's delivery notes. Needs `OPENAI_API_KEY`. |
| `elevenlabs` | Cloud | eleven_v3. Needs `ELEVENLABS_API_KEY` and a voice id. |

### Step by step

```bash
audiobook extract paper.pdf                    # what the parser found
audiobook script paper.pdf -o script.json      # narrate only (you can edit the script)
audiobook voice script.json paper.pdf -o out/  # perform a script with any voice
```

## Try it on the sample

`samples/sample-paper.pdf` is a two-page toy paper with a header, page numbers, citations, an
equation, a figure, a table, code, a footnote and references. You can regenerate it with
`python scripts/make_sample_pdf.py`.
`samples/sample-paper.explain.script.json` is an Explain-mode script for it.

```bash
audiobook voice samples/sample-paper.explain.script.json samples/sample-paper.pdf -o out/
```

## Tests

```bash
pytest
```
