# Read-along player

A mobile web player for the audiobooks that `audiobook` makes. It plays the narration and
highlights the passage on the PDF page while it is read. It works in Safari on iPhone and
Chrome on Android. No install, no build step, no app store.

What it does:

- Shows the PDF pages and highlights the block that is being read (yellow) or explained (blue).
- Shows the current sentence in a caption, so you can follow explanations that are not on the page.
- Follows the narration as it moves down the page. Scroll by hand to stop that; tap
  "Follow narration" to start again.
- Tap a paragraph on the page to jump the narration there.
- Chapter menu, back/forward 15 s, speed 0.75x to 2x, lock-screen controls.
- Remembers where you stopped (per book, on that phone).

## Try it on your phone

On your computer, in this repository:

```sh
python3 player/serve.py --demo          # the demo paper
python3 player/serve.py out/            # a book that `audiobook` wrote to out/
```

The command prints an address such as `http://192.168.1.20:8000/?demo=1`.
Open that address on the phone. The phone must be on the same Wi-Fi as the computer.

If the PDF is not in the book folder and `source_pdf` in `book.json` does not point to it,
add `--pdf path/to/file.pdf`.

`serve.py` uses only the Python standard library. It adds HTTP Range support, because Safari on
iPhone does not play audio from a server without it (Python's built-in `http.server` has none).

### Without a computer

Copy the book folder (`book.json`, the chapter audio files and the PDF) to the phone, open the
player from any web address, tap **Open** and select all of those files together.

## Input

The player reads `book.json` as `audiobook` writes it (see `audiobook/render.py`):
`page_sizes`, `chapters[].file/start/duration`, and `segments[]` with `kind`, `anchors[].page/bbox`
and `sentences[].text/start/end`. It needs no other fields.

URL parameters (paths are relative to `book.json`):

- `?book=path/to/book.json` — the book.
- `&pdf=file.pdf` — the PDF, if its name is not the base name of `source_pdf`.
- `&audio=all.mp3` — one audio file for the whole book instead of the chapter files.
- `?demo=1` — the demo in `demo/`.

## Files

- `index.html`, `style.css`, `app.js` — the player.
- `vendor/pdfjs/` — pdf.js 3.11.174 (Apache 2.0), included so the player works without a CDN.
- `demo/` — the sample paper in Explain mode, with its narration as one MP3.
- `serve.py` — the local server for phones on your Wi-Fi.
