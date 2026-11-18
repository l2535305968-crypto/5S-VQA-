#!/usr/bin/env python3
"""VQA 2.0 technical image audit: real pixel counts, formats, lossless 1:1 crops.

This tool does NOT automatically determine aesthetic quality, texture correctness,
AI-native generation resolution, or whether super-resolution invented details.
Requires Pillow. Legacy usage remains valid:
    python image_qc.py picture.png --target 3840x2160
New usage:
    python image_qc.py picture.png --target 2160x3840 --crop 384 --focus 120,500,240,300
    python image_qc.py images/ --recursive --target 2160x3840 --out qa_batch
    python image_qc.py picture.png --baseline original.png
Without --target, pixel verdict is NOT_EVALUATED rather than assuming a ratio.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp", ".avif"}
SAMPLE_POINTS = [
    ("center", 0.50, 0.50),
    ("upper_left", 0.15, 0.15),
    ("upper_right", 0.85, 0.15),
    ("lower_left", 0.15, 0.85),
    ("lower_right", 0.85, 0.85),
]


def parse_size(value: str) -> tuple[int, int]:
    try:
        parts = value.lower().replace(" ", "").split("x")
        if len(parts) != 2:
            raise ValueError
        w, h = map(int, parts)
        if w < 1 or h < 1:
            raise ValueError
        return w, h
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use WxH, for example 2160x3840") from exc


def parse_focus(value: str) -> tuple[int, int, int, int]:
    try:
        v = tuple(map(int, value.replace(" ", "").split(",")))
        if len(v) != 4 or v[0] < 0 or v[1] < 0 or v[2] < 1 or v[3] < 1:
            raise ValueError
        return v  # type: ignore[return-value]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use x,y,width,height in source pixels, e.g. 100,200,384,384") from exc


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover(paths: list[Path], recursive: bool) -> list[Path]:
    all_files: list[Path] = []
    for p in paths:
        if p.is_file():
            all_files.append(p)
        elif p.is_dir():
            itr = p.rglob("*") if recursive else p.iterdir()
            all_files.extend(f for f in itr if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS)
        else:
            raise FileNotFoundError(f"File or directory not found: {p}")
    unique: dict[str, Path] = {}
    for p in all_files:
        unique[str(p.resolve())] = p
    return sorted(unique.values(), key=lambda p: str(p).casefold())


def open_normalized(path: Path) -> tuple[Image.Image, dict[str, Any]]:
    with Image.open(path) as source:
        has_alpha = ("A" in source.getbands()) or ("transparency" in source.info)
        img = ImageOps.exif_transpose(source)
        img.load()
        alpha_extrema = None
        if has_alpha:
            alpha_extrema = list(img.convert("RGBA").getchannel("A").getextrema())
        meta = {
            "source_format": source.format,
            "source_mode": source.mode,
            "stored_size_px": list(source.size),
            "source_exif_orientation": source.getexif().get(274),
            "has_icc_profile": bool(source.info.get("icc_profile")),
            "has_alpha_channel_or_transparency": has_alpha,
            "alpha_extrema_0_255": alpha_extrema,
        }
    return img, meta


def make_contact_sheet(img: Image.Image, output: Path, requested_crop: int) -> list[dict[str, Any]]:
    """Extract source-pixel 1:1 samples with no interpolation (labels only on sheet)."""
    w, h = img.size
    size = min(w, h, requested_crop)
    cols, rows, gap, title_h = 3, 2, 16, 29
    sheet = Image.new("RGB", (cols * (size + gap) + gap, rows * (size + gap + title_h) + gap), "#e9e9e9")
    draw = ImageDraw.Draw(sheet)
    details = []
    has_alpha = ("A" in img.getbands()) or ("transparency" in img.info)
    rgba = img.convert("RGBA") if has_alpha else None
    rgb = img.convert("RGB") if not has_alpha else None
    for index, (name, xfrac, yfrac) in enumerate(SAMPLE_POINTS):
        xc, yc = round(w * xfrac), round(h * yfrac)
        x0 = max(0, min(w - size, xc - size // 2))
        y0 = max(0, min(h - size, yc - size // 2))
        if has_alpha:
            crop_rgba = rgba.crop((x0, y0, x0 + size, y0 + size))
            # Checkerboard compositing makes transparent pixels/edge halos visible
            # without silently discarding alpha against an arbitrary background.
            tile = 24
            checker = Image.new("RGB", crop_rgba.size, "#d8d8d8")
            checker_draw = ImageDraw.Draw(checker)
            for cy in range(0, size, tile):
                for cx in range(0, size, tile):
                    if ((cx // tile) + (cy // tile)) % 2:
                        checker_draw.rectangle((cx, cy, min(cx + tile - 1, size - 1), min(cy + tile - 1, size - 1)), fill="#aaaaaa")
            crop = Image.alpha_composite(checker.convert("RGBA"), crop_rgba).convert("RGB")
        else:
            crop = rgb.crop((x0, y0, x0 + size, y0 + size))
        col, row = index % cols, index // cols
        x = gap + col * (size + gap)
        y = gap + row * (size + gap + title_h)
        draw.text((x, y + 7), f"{name}: ({x0},{y0}) | 1:1 px", fill="#181818")
        sheet.paste(crop, (x, y + title_h))
        details.append({"name": name, "pixel_origin": [x0, y0], "crop_size_px": [size, size]})
    sheet.save(output, format="PNG")
    return details


def make_focus_crops(img: Image.Image, out: Path, regions: list[tuple[int, int, int, int]]) -> list[dict[str, Any]]:
    w, h = img.size
    details = []
    for i, (x, y, rw, rh) in enumerate(regions, start=1):
        if x + rw > w or y + rh > h:
            raise ValueError(f"Focus #{i} ({x},{y},{rw},{rh}) exceeds image size {w}x{h}")
        fname = f"focus_{i:02d}_100pct.png"
        img.crop((x, y, x + rw, y + rh)).save(out / fname, format="PNG")
        details.append({"image": fname, "origin_px": [x, y], "size_px": [rw, rh], "resampled": False})
    return details


def inspect(path: Path, out: Path, args: argparse.Namespace) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    img, meta = open_normalized(path)
    w, h = img.size
    target = list(args.target) if args.target else None
    required_format = args.format.upper() if args.format else None
    actual_fmt = (meta["source_format"] or "UNKNOWN").upper()
    pixel_status = "NOT_EVALUATED" if target is None else ("PASS" if [w, h] == target else "FAIL")
    format_status = "NOT_EVALUATED" if required_format is None else ("PASS" if actual_fmt == required_format else "FAIL")
    failed = "FAIL" in (pixel_status, format_status)
    technical_status = "FAIL" if failed else ("TECHNICAL_PASS_VISUAL_PENDING" if target or required_format else "INSPECTION_ONLY")
    crops = make_contact_sheet(img, out / "review_100pct_crops.png", args.crop)
    focus = make_focus_crops(img, out, args.focus)
    warnings = [
        "This script cannot determine aesthetics, AI artifacts, true source detail, or model-native resolution.",
        "Inspect 100%-scale crops AND the whole image; 1:1 crops are not a substitute for visual judgment.",
    ]
    if actual_fmt in {"JPEG", "WEBP"}:
        warnings.append("Potentially lossy input: use original lossless master when available.")
    if pixel_status == "FAIL":
        warnings.append(f"Exact size mismatch: got {w}x{h}; required {target[0]}x{target[1]}.")
    if pixel_status == "NOT_EVALUATED":
        warnings.append("No --target supplied; no pixel pass claim is possible.")
    if format_status == "FAIL":
        warnings.append(f"Format mismatch: got {actual_fmt}; required {required_format}.")
    baseline_info: dict[str, Any] | None = None
    if args.baseline:
        original_img, original_meta = open_normalized(args.baseline)
        baseline_info = {
            "baseline_file": str(args.baseline.resolve()),
            "baseline_size_px": list(original_img.size),
            "baseline_format": original_meta["source_format"],
            "size_changed": list(original_img.size) != [w, h],
            "detail_restoration_verified": False,
            "warning": "Pixel counts and file formats cannot establish detail recovery or native generation origin.",
        }
    report = {
        "schema_version": "2.0", "checked_utc": utc_now(),
        "source_file": str(path.resolve()), "source_sha256": sha256(path),
        "file_bytes": path.stat().st_size, **meta,
        "actual_size_px": [w, h], "required_size_px": target,
        "required_format": required_format,
        "pixel_requirement": pixel_status,
        "format_requirement": format_status,
        "technical_status": technical_status,
        "visual_quality_status": "NOT_EVALUATED",
        "source_native_resolution": "UNKNOWN",
        "processing_history": "NOT_PROVIDED",
        "inspection_crops": crops, "focus_crops": focus,
        "100pct_preview": str((out / "review_100pct_crops.png").resolve()),
        "baseline_comparison": baseline_info, "warnings": warnings,
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "VQA TECHNICAL IMAGE AUDIT", "",
        f"File: {path}", f"Actual: {w} x {h} px",
        f"Required: {target[0]} x {target[1]} px" if target else "Required: NOT SPECIFIED",
        f"Format: {actual_fmt} | Required: {required_format or 'NOT SPECIFIED'}",
        f"Pixel check: {pixel_status}", f"Format check: {format_status}",
        f"Technical result: {technical_status}", "Visual quality: NOT_EVALUATED (human/vision-model inspection required)",
        "", "Inspect review_100pct_crops.png. Source pixels were not resampled.",
        "Inspect the primary subject separately if the five samples missed it.",
        "N1-N5 noise/artifact types MUST be judged in visual and task context.",
        "True native model resolution and AI-upscale provenance CANNOT be inferred from dimensions.",
        f"Alpha/transparency: {meta['has_alpha_channel_or_transparency']} | alpha extrema: {meta['alpha_extrema_0_255']}",
        "Transparent samples are composited over a checkerboard in the contact sheet; focus crops retain source alpha.", "",
        *[f"WARNING: {item}" for item in warnings],
    ]
    (out / "REVIEW.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VQA image technical audit and lossless 100% inspection crops")
    parser.add_argument("image", nargs="+", type=Path, help="One or more image paths or directories")
    parser.add_argument("--target", type=parse_size, default=None, help="Exact width x height; optional, no implied default")
    parser.add_argument("--format", type=str, default=None, help="Expected source format such as PNG")
    parser.add_argument("--out", type=Path, help="Output directory (single default qc_<stem>; batch default qc_batch)")
    parser.add_argument("--crop", type=int, default=384, help="1:1 sample crop side (at least 16 px)")
    parser.add_argument("--focus", type=parse_focus, action="append", default=[], help="Repeat x,y,width,height for 100% specific-region crops")
    parser.add_argument("--recursive", action="store_true", help="Search directories recursively")
    parser.add_argument("--baseline", type=Path, help="Reference original for a SINGLE-image technical comparison")
    args = parser.parse_args(argv)
    if args.crop < 16:
        parser.error("--crop must be at least 16")
    try:
        files = discover(args.image, args.recursive)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    if not files:
        parser.error("No supported images found")
    if args.baseline and (len(files) != 1 or not args.baseline.is_file()):
        parser.error("--baseline requires one image and an existing baseline image")
    single = len(files) == 1
    out_root = args.out or (files[0].parent / f"qc_{files[0].stem}" if single else Path.cwd() / "qc_batch")
    reports = []
    errors = []
    for i, p in enumerate(files, start=1):
        name = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", p.stem).strip("._") or "image"
        folder = out_root if single else out_root / f"{i:03d}_{name}"
        try:
            report = inspect(p, folder, args)
            reports.append(report)
            print(f"[{i}/{len(files)}] {p.name}: {report['actual_size_px']} | {report['technical_status']}")
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            errors.append({"file": str(p), "error": str(exc)})
            print(f"[ERROR] {p}: {exc}", file=sys.stderr)
    if not single:
        out_root.mkdir(parents=True, exist_ok=True)
        summary = {"checked_utc": utc_now(), "count": len(files), "succeeded": len(reports), "errors": errors,
                   "results": [{"source_file": r["source_file"], "actual_size_px": r["actual_size_px"],
                                "pixel_requirement": r["pixel_requirement"], "format_requirement": r["format_requirement"],
                                "technical_status": r["technical_status"]} for r in reports]}
        (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with (out_root / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["source_file", "width", "height", "pixel_check", "format_check", "technical_status"])
            for r in reports:
                writer.writerow([r["source_file"], *r["actual_size_px"], r["pixel_requirement"],
                                 r["format_requirement"], r["technical_status"]])
    if errors or not reports:
        return 1
    if any(r["technical_status"] == "FAIL" for r in reports):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
