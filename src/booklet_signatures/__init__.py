"""
booklet_signatures

Split a large, normally-sorted PDF (page 1, 2, 3, ...) into multiple
saddle-stitch "signatures" (mini zines, e.g. 16 pages each), and reorder
the pages of each signature into correct fold/imposition order.

By default this does NOT place two pages side-by-side on one sheet for
the interior signatures. It only reorders single, full-size pages so
that when you print each signature's output PDF using your print
dialog's "2 pages per sheet" + duplex option, the physical sheets come
out in the right sequence to fold, nest, and sew into a book with
signatures stacked on top of each other (the classic multi-signature
bookbinding trick that keeps the middle from bulging the way one giant
60+ page saddle-stitch does).

Pass --imposed to instead have the script itself combine two source
pages directly onto each output page (e.g. two A5 pages onto one
A4-sized output page), so you don't need to configure "pages per sheet"
in your print dialog at all -- just print each signature file
double-sided at actual size.

Optionally (--cover-sleeve), the first two and last two pages of the
source document are pulled out of the interior signatures entirely and
used to build a single wraparound cover sheet: back cover, blank spine,
front cover on the outside; front-inner and back-inner pages on the
reverse. That sheet is sized to wrap around the outside of all the
sewn-together interior signatures, like a slipcover/dust-jacket, rather
than being sewn through the middle with any one signature. The cover
sleeve is always built as a directly-imposed sheet, regardless of
--imposed, since it needs the blank spine placed between the two panels
either way.

HOW THE INTERIOR SIGNATURE MATH WORKS
--------------------------------------
For a signature of n pages (n divisible by 4), sheet i (0-indexed,
i = 0 is the outermost sheet of that signature):
    front side pages (left, right) = (n - 2i,     2i + 1)
    back  side pages (left, right) = (2i + 2, n - 2i - 1)
(For --duplex short, the back side pair is swapped left/right to
compensate for the different flip axis.)

Concatenating all sheets' front/back pairs in order (sheet 0 front,
sheet 0 back, sheet 1 front, sheet 1 back, ...) and printing that
sequence 2-up double-sided (or, with --imposed, directly rendering each
pair onto one output page) produces a correctly folding booklet.

HOW THE COVER SLEEVE WORKS
---------------------------
The cover sleeve is a single sheet, printed on both sides, with a blank
spine strip in the middle whose width you choose to match the thickness
of the finished, sewn stack of interior signatures.

Outside (what you see with the book closed), left to right:
    [ back cover page ] [ blank spine ] [ front cover page ]

Inside (what you see when you open the front or back cover), the two
content panels swap sides relative to the outside layout because
flipping the physical sheet over (to print or view the reverse) mirrors
left and right -- this is the same "long edge" vs "short edge" duplex
distinction used for the interior signatures:
    --duplex long  (default): [ front-inner page ] [ blank spine ] [ back-inner page ]
    --duplex short:           [ back-inner page ]  [ blank spine ] [ front-inner page ]

A3 is a common sheet size for printing this kind of wraparound cover
and trimming to size, so the tool checks the resulting sheet dimensions
against A3 and warns if it won't fit.
"""

import argparse
import math
import os
import sys

from pypdf import PdfReader, PdfWriter, Transformation

MM_TO_PT = 2.834645669291339
A3_LANDSCAPE_WIDTH_PT = 420 * MM_TO_PT
A3_LANDSCAPE_HEIGHT_PT = 297 * MM_TO_PT


def booklet_page_pairs(n: int, duplex: str = "long") -> list[tuple[int, int]]:
    """Return the list of (left, right) 1-indexed local page number pairs,
    one pair per sheet side, in print order (sheet 0 front, sheet 0 back,
    sheet 1 front, sheet 1 back, ...). n must be a multiple of 4."""
    assert n % 4 == 0, "signature size must be a multiple of 4"
    pairs = []
    sheets = n // 4
    for i in range(sheets):
        front = (n - 2 * i, 2 * i + 1)
        back = (2 * i + 2, n - 2 * i - 1)
        if duplex == "short":
            back = (back[1], back[0])
        pairs.append(front)
        pairs.append(back)
    return pairs


def booklet_page_sequence(n: int, duplex: str = "long") -> list[int]:
    """Return the linear sequence of 1-indexed local page numbers
    (within a single signature of length n) in imposition/print order,
    for use when NOT combining two pages onto one output sheet (i.e. you
    rely on your print dialog's own "2 pages per sheet" option). n must
    be a multiple of 4."""
    sequence = []
    for left, right in booklet_page_pairs(n, duplex=duplex):
        sequence.extend((left, right))
    return sequence


def chunk_pages(total_pages: int, signature_size: int) -> list[tuple[int, int]]:
    """Split total_pages into chunks of signature_size (last chunk may
    be smaller). Returns list of (start, end) 1-indexed inclusive."""
    chunks = []
    start = 1
    while start <= total_pages:
        end = min(start + signature_size - 1, total_pages)
        chunks.append((start, end))
        start = end + 1
    return chunks


def pad_to_multiple_of_4(n: int) -> int:
    return math.ceil(n / 4) * 4


def build_signature_pdf(reader, start, end, duplex, out_path, imposed=False):
    """Build one reordered, padded-if-needed signature PDF.

    If imposed is False (default): one full-size source page per output
    page, in fold order, for use with your print dialog's own "2 pages
    per sheet" option.

    If imposed is True: two source pages are combined directly onto
    each output page, side by side at native size (e.g. two A5 pages
    onto one A4-sized output page), so no "pages per sheet" print
    setting is needed -- just duplex printing at actual size.
    """
    real_pages = list(range(start, end + 1))  # 1-indexed source page numbers
    n_real = len(real_pages)
    n_padded = pad_to_multiple_of_4(n_real)
    n_blank = n_padded - n_real

    # local_page_map: local page number (1..n_padded) -> source page index
    # (0-indexed) or None for blank
    local_map = {}
    for local_i, src_page in enumerate(real_pages, start=1):
        local_map[local_i] = src_page - 1  # 0-indexed
    for local_i in range(n_real + 1, n_padded + 1):
        local_map[local_i] = (
            None  # blank filler, goes at the very end (last local pages)
        )

    # Determine page size from the first real page in this signature
    sample_idx = next(v for v in local_map.values() if v is not None)
    page_w = float(reader.pages[sample_idx].mediabox.width)
    page_h = float(reader.pages[sample_idx].mediabox.height)

    writer = PdfWriter()

    if imposed:
        pairs = booklet_page_pairs(n_padded, duplex=duplex)
        for left_num, right_num in pairs:
            out_page = writer.add_blank_page(width=page_w * 2, height=page_h)
            for local_num, x_offset in ((left_num, 0.0), (right_num, page_w)):
                src_idx = local_map[local_num]
                if src_idx is not None:
                    out_page.merge_transformed_page(
                        reader.pages[src_idx], Transformation().translate(x_offset, 0)
                    )
                # if src_idx is None (blank filler), leave that half blank
    else:
        sequence = booklet_page_sequence(n_padded, duplex=duplex)
        for local_num in sequence:
            src_idx = local_map[local_num]
            if src_idx is None:
                writer.add_blank_page(width=page_w, height=page_h)
            else:
                writer.add_page(reader.pages[src_idx])

    with open(out_path, "wb") as f:
        writer.write(f)

    return n_real, n_blank, n_padded


def build_cover_sleeve_pdf(
    reader,
    cover_front_idx,
    inner_front_idx,
    inner_back_idx,
    cover_back_idx,
    spine_width_pt,
    duplex,
    out_path,
):
    """Build a 2-page wraparound cover sleeve PDF.

    Page 1 (outside): back cover | blank spine | front cover
    Page 2 (inside):  mirrored panel order per --duplex, same blank spine

    Indices are 0-indexed source page indices. Returns (sheet_width_pt,
    sheet_height_pt) for the A3-fit check.
    """
    page_w = float(reader.pages[cover_front_idx].mediabox.width)
    page_h = float(reader.pages[cover_front_idx].mediabox.height)
    sheet_w = page_w * 2 + spine_width_pt
    sheet_h = page_h

    writer = PdfWriter()

    # Outside: back cover at left, front cover at right
    outside = writer.add_blank_page(width=sheet_w, height=sheet_h)
    outside.merge_transformed_page(
        reader.pages[cover_back_idx], Transformation().translate(0, 0)
    )
    outside.merge_transformed_page(
        reader.pages[cover_front_idx],
        Transformation().translate(page_w + spine_width_pt, 0),
    )

    # Inside: panel order depends on which edge the printer flips on
    inside = writer.add_blank_page(width=sheet_w, height=sheet_h)
    if duplex == "long":
        left_page_idx, right_page_idx = inner_front_idx, inner_back_idx
    else:
        left_page_idx, right_page_idx = inner_back_idx, inner_front_idx
    inside.merge_transformed_page(
        reader.pages[left_page_idx], Transformation().translate(0, 0)
    )
    inside.merge_transformed_page(
        reader.pages[right_page_idx],
        Transformation().translate(page_w + spine_width_pt, 0),
    )

    with open(out_path, "wb") as f:
        writer.write(f)

    return sheet_w, sheet_h


def check_fits_a3(sheet_w_pt, sheet_h_pt):
    """Return (fits: bool, message: str) comparing sheet dims to A3 landscape."""
    fits = sheet_w_pt <= A3_LANDSCAPE_WIDTH_PT and sheet_h_pt <= A3_LANDSCAPE_HEIGHT_PT
    sheet_w_mm = sheet_w_pt / MM_TO_PT
    sheet_h_mm = sheet_h_pt / MM_TO_PT
    if fits:
        msg = (
            f"Cover sheet is {sheet_w_mm:.1f}mm x {sheet_h_mm:.1f}mm, "
            f"fits within A3 (420mm x 297mm)."
        )
    else:
        msg = (
            f"WARNING: cover sheet is {sheet_w_mm:.1f}mm x {sheet_h_mm:.1f}mm, "
            f"which does NOT fit within A3 (420mm x 297mm). "
            f"Reduce --spine-width-mm, or scale the print job down, or use a larger sheet."
        )
    return fits, msg


def main():
    parser = argparse.ArgumentParser(
        prog="booklet-signatures",
        description="Split a thesis PDF into saddle-stitch signatures "
        "(mini zines) with pages reordered for correct fold order, "
        "with an optional wraparound cover sleeve.",
    )
    parser.add_argument("input_pdf", help="Path to source PDF")
    parser.add_argument(
        "--signature-size",
        "-s",
        type=int,
        default=16,
        help="Pages per signature/zine (multiple of 4). Default: 16",
    )
    parser.add_argument(
        "--duplex",
        "-d",
        choices=["long", "short"],
        default="long",
        help="Which edge your printer flips on for double-sided printing. Default: long",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="./booklet_output",
        help="Directory to write output files. Default: ./booklet_output",
    )
    parser.add_argument(
        "--cover-sleeve",
        "-c",
        action="store_true",
        help="Pull the first two and last two pages out of the interior "
        "signatures and build a separate wraparound cover sheet "
        "(back cover / spine / front cover, plus inner pages).",
    )
    parser.add_argument(
        "--spine-width-mm",
        type=float,
        default=10.0,
        help="Width of the blank spine strip on the cover sleeve, in mm. "
        "Match this to the thickness of your sewn stack of signatures. "
        "Default: 10.0",
    )
    parser.add_argument(
        "--imposed",
        "-i",
        action="store_true",
        help="Combine two source pages directly onto each output page "
        "(e.g. two A5 pages onto one A4-sized output page), instead of "
        "relying on your print dialog's own 'pages per sheet' option. "
        "Off by default.",
    )
    args = parser.parse_args()

    if args.signature_size % 4 != 0:
        print(
            f"ERROR: --signature-size must be a multiple of 4 "
            f"(got {args.signature_size}).",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.cover_sleeve and args.spine_width_mm <= 0:
        print(
            f"ERROR: --spine-width-mm must be greater than 0 "
            f"(got {args.spine_width_mm}).",
            file=sys.stderr,
        )
        sys.exit(1)

    reader = PdfReader(args.input_pdf)
    total_pages = len(reader.pages)
    os.makedirs(args.output_dir, exist_ok=True)

    instructions = []
    instructions.append(f"Source PDF: {args.input_pdf}")
    instructions.append(f"Total pages: {total_pages}")
    instructions.append(f"Signature size: {args.signature_size}")
    instructions.append(f"Duplex mode: {args.duplex}-edge flip")
    instructions.append(f"Imposed (2-up) output: {'yes' if args.imposed else 'no'}")

    body_start = 1
    body_end = total_pages

    if args.cover_sleeve:
        # Need at minimum: page 1 (front cover), page 2 (front inner),
        # second-to-last (back inner), last (back cover), i.e. 4 pages
        # just for the cover, plus at least 1 page of interior content.
        if total_pages < 5:
            print(
                f"ERROR: --cover-sleeve needs at least 5 pages total "
                f"(4 for the cover, 1+ for the interior); got {total_pages}.",
                file=sys.stderr,
            )
            sys.exit(1)

        cover_front_idx = 0  # page 1
        inner_front_idx = 1  # page 2
        inner_back_idx = total_pages - 2  # second-to-last page
        cover_back_idx = total_pages - 1  # last page

        body_start = 3
        body_end = total_pages - 2
        body_page_count = body_end - body_start + 1

        if body_page_count <= 0:
            print(
                f"ERROR: after removing the 4 cover pages, there are no "
                f"pages left for the interior signatures ({total_pages} "
                f"total pages is too few).",
                file=sys.stderr,
            )
            sys.exit(1)

        spine_width_pt = args.spine_width_mm * MM_TO_PT
        cover_out_path = os.path.join(args.output_dir, "cover_sleeve.pdf")
        sheet_w, sheet_h = build_cover_sleeve_pdf(
            reader,
            cover_front_idx,
            inner_front_idx,
            inner_back_idx,
            cover_back_idx,
            spine_width_pt,
            args.duplex,
            cover_out_path,
        )
        fits, fit_msg = check_fits_a3(sheet_w, sheet_h)

        instructions.append("")
        instructions.append("COVER SLEEVE")
        instructions.append(
            f"  Source pages used: front cover = page 1, front inner = page 2, "
            f"back inner = page {total_pages - 1}, back cover = page {total_pages}"
        )
        instructions.append(
            f"  Interior signatures now cover pages {body_start}-{body_end} "
            f"({body_page_count} pages), i.e. total pages minus the 4 cover pages."
        )
        instructions.append(f"  Spine width: {args.spine_width_mm:.1f}mm")
        instructions.append(f"  {fit_msg}")
        instructions.append(
            "  Print cover_sleeve.pdf double-sided (page 1 = outside: back "
            "cover / spine / front cover -- page 2 = inside: inner pages "
            "either side of the same spine), on A3, then trim to size and "
            "score/fold at the spine edges. Wrap it around the outside of "
            "the sewn stack of interior signatures; it is not sewn through "
            "any signature's own fold."
        )
        instructions.append(
            "  If your duplex printer misaligns page 2, print the two "
            "pages as separate single-sided jobs instead and align/glue "
            "by hand -- this avoids relying on the printer's duplex "
            "geometry for the cover."
        )
        instructions.append("")

        print("Cover sleeve: cover_sleeve.pdf")
        print(f"  {fit_msg}")

    chunks = chunk_pages(body_end - body_start + 1, args.signature_size)
    # shift chunk numbering to reflect true source page numbers
    chunks = [(body_start + s - 1, body_start + e - 1) for (s, e) in chunks]

    instructions.append(f"Number of interior signatures: {len(chunks)}")
    instructions.append("")
    instructions.append("PRINT SETTINGS TO USE FOR EACH SIGNATURE FILE:")
    flip_label = "long edge (standard)" if args.duplex == "long" else "short edge"
    if args.imposed:
        instructions.append(
            "  - Pages are already imposed: each output page contains two "
            "source pages side by side (e.g. two A5 pages on one A4-sized "
            "output page). Do NOT set 'pages per sheet' in the print dialog."
        )
        instructions.append(
            "  - Print at actual size / 100% (no 'fit to page' scaling)."
        )
        instructions.append("  - Two-sided printing: ON")
        instructions.append(f"  - Flip on: {flip_label}")
    else:
        instructions.append("  - Pages per sheet: 2")
        instructions.append("  - Page order: horizontal / left-to-right")
        instructions.append("  - Two-sided printing: ON")
        instructions.append(f"  - Flip on: {flip_label}")
    instructions.append("")
    instructions.append(
        "ASSEMBLY ORDER: after printing and cutting each signature's stack of "
        "sheets in half (or folding, depending on your paper size setup), fold "
        "each signature's sheets together as one nested unit, in the sheet order "
        "they were printed. Then nest/stack the signatures themselves in numeric "
        "order and sew through the shared fold line of each signature separately, "
        "then join signatures together (e.g. with a sewn or glued spine)."
        + (
            " Finally, wrap the cover sleeve around the outside of the whole "
            "sewn stack."
            if args.cover_sleeve
            else ""
        )
    )
    instructions.append("")

    for idx, (start, end) in enumerate(chunks, start=1):
        out_name = f"signature_{idx:02d}_pages_{start:03d}-{end:03d}.pdf"
        out_path = os.path.join(args.output_dir, out_name)
        n_real, n_blank, n_padded = build_signature_pdf(
            reader, start, end, args.duplex, out_path, imposed=args.imposed
        )
        line = f"Signature {idx:02d}: source pages {start}-{end} ({n_real} pages)"
        if n_blank:
            line += (
                f" + {n_blank} blank filler page(s) padded to {n_padded} -> {out_name}"
            )
        else:
            line += f" -> {out_name}"
        instructions.append(line)
        print(line)

    instr_path = os.path.join(args.output_dir, "print_instructions.txt")
    with open(instr_path, "w") as f:
        f.write("\n".join(instructions))

    print(f"\nWrote {len(chunks)} signature file(s) to {args.output_dir}")
    if args.cover_sleeve:
        print("Wrote cover_sleeve.pdf")
    print(f"Instructions: {instr_path}")


if __name__ == "__main__":
    main()
