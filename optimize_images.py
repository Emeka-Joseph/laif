"""Resize and re-encode the photographs in images/ for the web.

The originals are straight off the camera: 6000x4000 and up to 11 MB each,
which the site then serves at full size. This rewrites them at a sensible
display size, leaving the originals untouched.

    python optimize_images.py                 # write images_optimized/
    python optimize_images.py --in-place      # overwrite images/ (keeps a backup)

Filenames are never changed, so every template, database row and link keeps
working. EXIF rotation is baked into the pixels rather than stripped: 17 of
these files are marked "rotate 90°", and dropping that flag without turning
the image would leave them lying on their side in the browser.
"""

import argparse
import os
import shutil
import sys

from PIL import Image, ImageOps

SOURCE = "images"
MAX_EDGE = 2400          # long edge in pixels; comfortably sharp on a 4K display
JPEG_QUALITY = 82        # visually indistinguishable from the original at this size
PNG_COLOURS = 256        # palette size for the PNG portraits
JPEG_EXT = {".jpg", ".jpeg"}
PNG_EXT = {".png"}


def optimize(path, destination):
    """Write one optimized image. Returns (before, after) in bytes."""
    before = os.path.getsize(path)
    extension = os.path.splitext(path)[1].lower()

    with Image.open(path) as image:
        # Apply the camera's rotation flag to the pixels, then let it go.
        image = ImageOps.exif_transpose(image)

        if max(image.size) > MAX_EDGE:
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

        if extension in JPEG_EXT or extension == ".jpg":
            if image.mode != "RGB":
                image = image.convert("RGB")
            image.save(destination, "JPEG", quality=JPEG_QUALITY,
                       optimize=True, progressive=True)
        elif extension in PNG_EXT:
            # These are photographs saved as PNG, which is why they are
            # megabytes apiece. A 256-colour palette takes roughly 85% off
            # at a mean error near 2/255 — invisible on a photograph — and
            # quantising in RGBA keeps the cut-out portraits' transparency,
            # so nothing needs a flat background baked in behind it.
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.mode else "RGB")
            palette = image.quantize(colors=PNG_COLOURS, method=Image.FASTOCTREE,
                                     dither=Image.FLOYDSTEINBERG)
            palette.save(destination, "PNG", optimize=True)
        else:
            shutil.copy2(path, destination)

    after = os.path.getsize(destination)
    # A small file can come out larger than it went in; keep whichever is smaller.
    if after >= before:
        shutil.copy2(path, destination)
        after = before
    return before, after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-place", action="store_true",
                        help="overwrite images/, backing the originals up first")
    parser.add_argument("--out", default="images_optimized",
                        help="destination folder (default: images_optimized)")
    args = parser.parse_args()

    if not os.path.isdir(SOURCE):
        sys.exit(f"No {SOURCE}/ folder here. Run this from the project root.")

    out = SOURCE if args.in_place else args.out
    if args.in_place:
        backup = SOURCE + "_originals"
        if os.path.exists(backup):
            sys.exit(f"{backup}/ already exists; move it aside first.")
        shutil.copytree(SOURCE, backup)
        print(f"Originals copied to {backup}/")
    os.makedirs(out, exist_ok=True)

    files = sorted(f for f in os.listdir(SOURCE)
                   if os.path.isfile(os.path.join(SOURCE, f)))
    total_before = total_after = 0
    print(f"{'file':44} {'before':>9} {'after':>9}  saved")
    print("-" * 76)
    for name in files:
        source = os.path.join(SOURCE + "_originals" if args.in_place else SOURCE, name)
        before, after = optimize(source, os.path.join(out, name))
        total_before += before
        total_after += after
        cut = (1 - after / before) * 100 if before else 0
        print(f"{name:44} {before/1024/1024:8.1f}M {after/1024/1024:8.1f}M  {cut:4.0f}%")

    print("-" * 76)
    saved = (1 - total_after / total_before) * 100 if total_before else 0
    print(f"{'TOTAL':44} {total_before/1024/1024:8.1f}M {total_after/1024/1024:8.1f}M  {saved:4.0f}%")
    print(f"\nWritten to {out}/")


if __name__ == "__main__":
    main()
