"""Render sidebar SVG assets, then refresh the distributable logo kit."""
from pathlib import Path
import shutil
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
renderer = shutil.which("rsvg-convert")
if not renderer:
    raise SystemExit("rsvg-convert is required; add its directory to PATH")
for source in sorted((ROOT / "sidebar").glob("wordmark*.svg")):
    for scale in (1, 2, 3):
        target = source.with_name(source.stem + (f"@{scale}x" if scale > 1 else "") + ".png")
        subprocess.run([renderer, "-z", str(scale), "-o", str(target), str(source)], check=True)
subprocess.run([renderer, "-o", str(ROOT / "sidebar/preview.png"), str(ROOT / "sidebar/preview.svg")], check=True)
target = ROOT.parent / "g-hess-logo-kit.zip"
with ZipFile(target, "w", ZIP_DEFLATED) as archive:
    for source in sorted(ROOT.rglob("*")):
        if source.is_file() and "__pycache__" not in source.parts:
            archive.write(source, source.relative_to(ROOT.parent))
print(f"Rendered sidebar PNGs and saved {target.name}")
