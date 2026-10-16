#!/usr/bin/env python3
"""Move files dropped into uploads/ to their place on the site.

  uploads/<any image>  (.jpg .jpeg .png .webp .heic)  ->  assets/photo.jpg  (square, 600 px)
  uploads/<any .pdf>                                  ->  assets/cv.pdf
  uploads/<any .docx>                                 ->  assets/cv.pdf  (converted with LibreOffice)

It also bumps the ?v= number on those links in index.html so visitors see
the new file right away instead of an old cached copy, and then empties uploads/.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UP = ROOT / "uploads"
ASSETS = ROOT / "assets"
INDEX = ROOT / "index.html"
IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def newest(exts):
    files = [p for p in UP.iterdir() if p.is_file() and p.suffix.lower() in exts]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def make_photo(src):
    from PIL import Image, ImageOps  # pillow
    try:
        import pillow_heif  # noqa: F401
        pillow_heif.register_heif_opener()
    except Exception:  # noqa: BLE001
        pass
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    side = min(im.size)
    left, top = (im.width - side) // 2, max(0, (im.height - side) // 3)  # keep the face, crop a bit more below
    im = im.crop((left, top, left + side, top + side)).resize((600, 600), Image.LANCZOS)
    im.save(ASSETS / "photo.jpg", quality=86, optimize=True, progressive=True)


def make_cv(src):
    if src.suffix.lower() == ".pdf":
        shutil.copyfile(src, ASSETS / "cv.pdf")
        return
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src)],
                       check=True, capture_output=True, timeout=180)
        pdf = next(Path(tmp).glob("*.pdf"))
        shutil.copyfile(pdf, ASSETS / "cv.pdf")


def bump(asset):
    doc = INDEX.read_text()
    v = str(int(time.time()))
    doc = re.sub(rf"assets/{re.escape(asset)}\?v=\d+", f"assets/{asset}?v={v}", doc)
    INDEX.write_text(doc)


def main():
    done = []
    img = newest(IMAGES)
    if img:
        make_photo(img)
        bump("photo.jpg")
        done.append(f"headshot from {img.name}")
    doc = newest({".pdf", ".docx", ".doc"})
    if doc:
        make_cv(doc)
        bump("cv.pdf")
        done.append(f"CV from {doc.name}")
    for p in UP.iterdir():
        if p.is_file() and p.name != "README.md":
            p.unlink()
    print("Updated: " + ", ".join(done) if done else "Nothing to process.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
