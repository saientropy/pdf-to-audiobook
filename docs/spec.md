# PDF to audiobook: product spec

Status: draft, 2026-10-23. Platform (macOS / iOS / Android / web) is still open; everything below is a
platform-agnostic core that a future app wraps.

## What we are building

An **AI narrator** for documents, not a text-to-speech reader. You open a PDF, press play, and hear
it read the way a good human narrator or tutor would: it skips the clutter, reads prose naturally,
and when it reaches a formula, a figure, a table or a chunk of code it tells you what that thing
*means*, not the symbols on the page. You can follow along in the PDF while it talks, and the text
being spoken is highlighted.

"Anything can read text blindly." The value is in the understanding layer, so the product is built
around it:

```
PDF ──► 1. Understand ──► 2. Write the script ──► 3. Perform ──► 4. Sync
        layout + vision      LLM narrator            expressive      audio + map
        (what is on the      (what to say, and       speech model    back to page
         page, in order)      how to say it)                         positions
```

The voice model is the last and most swappable step. The narrator (step 2) is the product.

## Narration modes

The same PDF can be narrated in different ways. The script is regenerated per mode; audio is cached
per mode.

| Mode | What you hear | For |
|---|---|---|
| **Read** | Clean, faithful reading of the prose. Formulas read in natural speech ("E equals m c squared"), figures and tables get a one-line mention. No commentary. | Novels, articles, when you just want the words |
| **Explain** (default) | Everything in Read, plus short asides that explain formulas, figures, tables and code in plain language, and say why they matter in context. | Papers, textbooks, technical docs |
| **Tutor** | Explain, plus a short "what this section was about" recap at the end of each section, and definitions the first time a jargon term appears. | Studying something hard |

Later (not in v1): **Skim** (section-by-section summary only) and **Ask** (pause and ask the narrator
a question about what you just heard).

## How each kind of content is handled

| Content | Read mode | Explain / Tutor mode |
|---|---|---|
| Body prose | Read verbatim, with hyphenation fixed and lines joined | Same |
| Headings | Read with a pause before and after; becomes a chapter marker | Same |
| Inline math (`$x_i$`) | Spoken naturally ("x sub i") | Same, plus a gloss on first use ("x sub i, the i-th input") |
| Display equations | Spoken naturally | Spoken, then explained: what each part is, what the equation says in words, why it matters here |
| Figures / charts | "Figure 3 shows the loss curve." (from caption) | Described from the image itself (via vision): what is plotted, the trend, the takeaway |
| Tables | "Table 2 compares four models." | The key takeaway, not cell by cell ("model C is best on every benchmark, by about 4 points") |
| Code blocks | "A code listing follows." | What the code does, in a sentence or two |
| Footnotes | Skipped | Read as a quiet aside where they are referenced, if they add something |
| Citation markers `[12]`, `(Smith et al., 2020)` | Dropped (or "Smith and colleagues" when the name is part of the sentence) | Same |
| Running headers, footers, page numbers | Dropped | Dropped |
| References / bibliography, index | Skipped, announced once | Same |
| Abbreviations, numbers, units, dates | Expanded for speech ("Fig." → "figure", "1990s" → "nineteen nineties", "5 km" → "five kilometres") | Same |
| Dialogue (fiction) | Narrator voice | Optional: distinct voices per speaker (later) |

Every explanation is clearly marked as an **aside** in the script, so the listener (and the reader UI)
can tell what the document says from what the narrator adds. The narrator must never present its own
commentary as the author's words.

## Step by step

### 1. Understand (extract)

- Use PyMuPDF to pull text blocks with font size, position and page, and to render each page to an image.
- Rule-based cleanup that is cheap and reliable: repeating headers/footers (same text in the same
  band on many pages), page numbers, hyphenation, multi-column reading order.
- Detect candidate headings (font size / weight), display equations (symbol density, centred
  blocks), figures (image regions + "Figure N" captions), tables, code (monospace fonts).
- Output: an ordered list of **blocks** `{id, page, bbox, kind, text}` per page.

### 2. Write the script (the narrator)

- An LLM with vision gets, for a window of a few pages at a time: the page images, the extracted
  blocks, the running outline of the document so far, and the mode.
- It returns a **narration script**: an ordered list of segments
  `{kind: read|aside|heading|pause, text, source_block_ids, style}`.
  - `text` is exactly what will be spoken.
  - `source_block_ids` ties the segment to positions on the page for highlighting.
  - `style` is a short delivery hint ("neutral", "slower, emphasise the result", "quiet aside").
- The document-level outline and a glossary of defined terms are carried between windows so the
  narrator stays consistent across a long book.
- Offline fallback: a rule-based narrator that produces a Read-mode script from the cleaned blocks
  with no LLM. Useful for testing and for plain prose.
- Scripts are cached as JSON. Regenerating audio with another voice never re-runs the LLM.

### 3. Perform (speech)

One small interface, `SpeechEngine.synthesize(text, style) -> audio`, with engines behind it:

| Engine | Where | Licence | Notes |
|---|---|---|---|
| Kokoro-82M (ONNX) | Local, all platforms | Apache 2.0 | v1 default. Fast, good quality, ignores style hints. |
| Gradium Phonon 31m | Local, all platforms (GGUF, Swift, WASM) | Apache 2.0 | Next to add. 64 MB, better with numbers/emails. 40m models are CC BY-NC. |
| Expressive local (Chatterbox, Orpheus, Dia) | Local, desktop GPU | MIT / Apache | Take emotion/style control; too heavy for phones today. |
| OpenAI gpt-4o-mini-tts | Cloud | Paid | Accepts free-text delivery instructions, so `style` maps straight across. |
| ElevenLabs v3 | Cloud | Paid | Best quality, audio tags for emotion. |

Because the script already carries delivery hints, a steerable voice (cloud today, local later) gets
the full "human narrator" performance, and a plain voice still reads a well-written script.

### 4. Sync (output)

- One audio file per chapter (heading), plus `book.json`:
  `{chapters: [{title, file, start}], segments: [{id, kind, text, start, end, page, bboxes}]}`.
- A reader UI plays the audio and highlights `bboxes` on `page` for the segment under the playhead.
  During an `aside`, the source (the formula, the figure) stays highlighted and the UI shows that the
  narrator is commenting.
- Tapping a paragraph in the PDF seeks to its segment.

## Local vs cloud

| Part | v1 | Fully local option |
|---|---|---|
| Extraction, cleanup, rule narrator | Local | Local |
| Narrator brain (LLM + vision) | Cloud (Claude) | Small local vision model on desktop. Noticeably weaker at explaining maths and figures today; not viable on phones yet. |
| Voice | Local (Kokoro), cloud optional | Local |

The narrator script is generated once per document and mode, so cloud cost is a one-off per book,
not per listen.

## v1 scope (this PR)

- Python package + CLI: `audiobook make paper.pdf --mode explain --voice kokoro -o out/`
- Extraction with header/footer/page-number/citation cleanup, headings, equation/figure/table/code detection.
- Rule-based narrator (Read mode, offline) and Claude narrator (Read / Explain / Tutor) with vision.
- Kokoro local engine; OpenAI and ElevenLabs engines behind the same interface.
- Chapter audio files + `book.json` sync map.
- Tests for extraction, cleanup and script/timing logic.

Out of scope for v1: the reader UI, Ask mode, per-character voices, Phonon engine (blocked on
downloading weights from this build environment), local LLM narrator.

## Open decisions

1. **May the narrator brain run in the cloud?** Recommended yes for v1 (quality of explanations);
   fully local is possible later on desktop with weaker results.
2. **Which voice tier should be the default** once there is an app: free local voice, or a paid
   cloud voice for the most human performance?
