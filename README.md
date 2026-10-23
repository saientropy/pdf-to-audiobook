# pdf-to-audiobook

Turn any PDF into an audiobook so you can listen along while you read.

## Goal

- Take a PDF as input.
- Extract its text in reading order (skipping headers, footers and page numbers where possible).
- Convert the text to natural-sounding speech.
- Output audio files (for example one MP3 per chapter) that you can play alongside the PDF.

## Status

Early days. Nothing is built yet; this repo is the starting point.

## Read-along player (phones)

`player/` holds a web player for iPhone and Android: it plays the audiobook and highlights the
passage on the PDF page. Run `python3 player/serve.py --demo` and open the printed address on
your phone. See [player/README.md](player/README.md).
