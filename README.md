# booklet-signatures

Split a large, normally-sorted PDF (page 1, 2, 3, ...) into multiple saddle-stitch "signatures" (mini zines, e.g. 16 pages each), and reorder the pages of each signature into correct fold/imposition order.

By default this does not place two pages side by side on one sheet for the interior signatures. It only reorders single, full-size pages so that feeding each signature's output PDF into your print dialog's "2 pages per sheet" plus duplex option produces sheets that fold, nest, and sew into a book with signatures stacked on top of each other. This is the standard multi-signature bookbinding technique that keeps the middle of a thick book from bulging the way one giant saddle-stitch zine does.

Optionally, it can combine two pages directly onto one output page itself (e.g. two A5 pages onto one A4-sized page), so you don't need to configure anything in your print dialog. It can also build a wraparound cover sleeve that covers all the signatures from the outside, like a slipcover.

## Install and run

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv run booklet-signatures thesis.pdf --signature-size 16 --duplex long --output-dir ./out
```

With direct 2-up imposition (two A5 pages combined onto one A4-sized output page):

```bash
uv run booklet-signatures thesis.pdf -s 16 -d long -i -o ./out
```

With a cover sleeve:

```bash
uv run booklet-signatures thesis.pdf -s 16 -d long -c --spine-width-mm 12 -o ./out
```

Both together:

```bash
uv run booklet-signatures thesis.pdf -s 16 -d long -i -c --spine-width-mm 12 -o ./out
```

Or, without installing it as a tool:

```bash
uv sync
uv run booklet-signatures thesis.pdf -s 16 -d long -o ./out
```

## Arguments

| Flag               | Short | Description                                                                                                                 | Default            |
| ------------------ | ----- | --------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| `input_pdf`        |       | Path to source PDF, pages already in normal reading order                                                                   | required           |
| `--signature-size` | `-s`  | Pages per signature/zine, must be a multiple of 4                                                                           | 16                 |
| `--duplex`         | `-d`  | Which edge your printer flips on for double-sided printing: `long` or `short`                                               | long               |
| `--output-dir`     | `-o`  | Where to write output files                                                                                                 | `./booklet_output` |
| `--imposed`        | `-i`  | Combine two source pages directly onto each output page, instead of relying on your print dialog's "pages per sheet" option | off                |
| `--cover-sleeve`   | `-c`  | Build a wraparound cover sleeve from the first two and last two pages instead of including them in the interior signatures  | off                |
| `--spine-width-mm` |       | Width of the blank spine strip on the cover sleeve, in mm                                                                   | 10.0               |

## Output

One PDF per interior signature, named like `signature_01_pages_003-018.pdf`, containing the pages of that chunk of the source document reordered for correct fold order. If a signature's page count isn't a multiple of 4, blank filler pages are added at the end of that signature automatically.

If `--cover-sleeve` is used, a `cover_sleeve.pdf` is also written (see below). The cover sleeve is always built as a directly-imposed sheet, regardless of `--imposed`, since it needs a blank spine placed between its two panels either way.

A `print_instructions.txt` is written alongside the output files summarizing the print settings and assembly order.

## Direct 2-up imposition (`--imposed`)

By default, each signature PDF contains one full-size source page per output page, in fold order, and you tell your print dialog to place 2 pages per sheet. That works fine, but relies on your print dialog's own imposition logic, which varies between apps and OSes.

With `--imposed`, the script does that combining itself: each output page directly contains two source pages placed side by side at their native size, with no scaling. For example, if your source PDF is A5, each output page ends up roughly A4-landscape sized, containing two A5 pages, in the correct fold order for that sheet side. Print each signature file double-sided at actual size (100%, no "fit to page"), with no "pages per sheet" setting needed.

Note this preserves each page at its original size, without scaling. If your source pages are already full A4 (or similar), combining two of them side by side will produce a page roughly twice as wide, which you would then need a large-format printer to output at true size — most people will only want `--imposed` when the source document's page size is already half of their target sheet size (e.g. A5 source pages for an A4 sheet output).

## Cover sleeve

`--cover-sleeve` pulls four pages out of the document entirely — page 1, page 2, the second-to-last page, and the last page — and uses them to build a single wraparound cover sheet instead of folding them into an interior signature. That sheet wraps around the outside of the whole sewn stack of interior signatures, like a slipcover, rather than being sewn through the middle of any one signature.

**What this means for your page count:** the interior signatures now cover pages 3 through (total − 2), i.e. total pages minus 4. For a 64-page thesis, that's 60 pages split into signatures as before, plus a separate 2-page `cover_sleeve.pdf`.

**Checks the tool runs for you:**

- Requires at least 5 total pages (4 for the cover, 1+ left over for the interior). Errors out otherwise.
- Requires `--spine-width-mm` to be greater than 0.
- Warns if, after adding your chosen spine width, the resulting cover sheet is larger than A3 (420mm x 297mm) — a common sheet size for printing this kind of wraparound cover and trimming to size. Note that two Letter or A4 pages side by side already use almost the entire width of an A3 sheet, so there's little room left for a wide spine; the warning tells you the exact sheet dimensions so you can adjust. Two A5 pages side by side leave plenty of room.

**Layout of `cover_sleeve.pdf`** (2 pages):

- Page 1 (outside, what you see with the book closed), left to right: back cover page, blank spine, front cover page.
- Page 2 (inside, what you see when you open the covers). The panel order swaps sides relative to the outside layout, because flipping the physical sheet over mirrors left and right — the same long-edge/short-edge distinction used for the interior signatures:
  - `--duplex long` (default): front-inner page, blank spine, back-inner page.
  - `--duplex short`: back-inner page, blank spine, front-inner page.

Print `cover_sleeve.pdf` on A3, double-sided, then trim to size and score/fold at the spine edges. If your printer's duplex alignment doesn't line up the two sides correctly, print the two pages as separate single-sided jobs instead and align/glue by hand.

## Printing the interior signatures

For each signature file, set your print dialog to:

- If not using `--imposed`: pages per sheet 2, two-sided printing on, flip on long or short edge matching `--duplex`.
- If using `--imposed`: no "pages per sheet" setting needed. Two-sided printing on, flip on long or short edge matching `--duplex`, and print at actual size (no scale-to-fit).

Print, fold each signature's stack of sheets in half as one unit, nest the signatures in numeric order, and sew each one through its own fold before joining the spines. If you used `--cover-sleeve`, wrap the finished cover sheet around the outside of the whole sewn stack last.

## How the interior signature imposition math works

For a signature of `n` pages (`n` divisible by 4), sheet `i` (0-indexed, `i = 0` is the outermost sheet of that signature):

```
front side pages (left, right) = (n - 2i,     2i + 1)
back  side pages (left, right) = (2i + 2, n - 2i - 1)
```

For `--duplex short`, the back side pair is swapped left/right to compensate for the different flip axis.

Concatenating all sheets' front/back pairs in order (sheet 0 front, sheet 0 back, sheet 1 front, sheet 1 back, ...) and printing that sequence 2-up double-sided (or, with `--imposed`, directly rendering each pair onto one output page) produces a correctly folding booklet.

## Note on creep

This tool does not compensate for creep or shingling (the small margin shift on inner pages caused by paper thickness accumulating through the fold). For 16-page signatures on standard paper this is usually negligible.
