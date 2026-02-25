from pathlib import Path

import pymupdf
from PIL import Image, ImageChops


def _is_blank(img: Image.Image, min_content_px: int = 50) -> bool:
    bg = Image.new("RGB", img.size, (255, 255, 255))
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    bg.close()
    diff.close()
    if bbox is None:
        return True
    content_w = bbox[2] - bbox[0]
    content_h = bbox[3] - bbox[1]
    return content_w < min_content_px or content_h < min_content_px


def trim_whitespace(img: Image.Image) -> Image.Image:
    bg = Image.new("RGB", img.size, (255, 255, 255))
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    bg.close()
    diff.close()
    if bbox:
        cropped = img.crop(bbox)
        img.close()
        return cropped
    return img


def _resize(img: Image.Image, max_width: int | None) -> Image.Image:
    if max_width and img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, max(1, int(img.height * ratio)))
        resized = img.resize(new_size, Image.LANCZOS)
        img.close()
        return resized
    return img


def process_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 150,
    fmt: str = "jpg",
    merge: bool = True,
    prefix: str = "page",
    max_width: int | None = 1600,
) -> tuple[int, list[Path]]:
    """Convert PDF to trimmed images. Returns (page_count, saved_paths)."""
    doc = pymupdf.open(str(pdf_path))
    zoom = dpi / 72
    mat = pymupdf.Matrix(zoom, zoom)
    output_dir.mkdir(parents=True, exist_ok=True)
    save_kwargs = {"quality": 85} if fmt == "jpg" else {"optimize": True}

    saved: list[Path] = []
    page_count = len(doc)

    page_num = 0
    for page in doc:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        if _is_blank(img):
            img.close()
            continue
        img = trim_whitespace(img)
        img = _resize(img, max_width)
        page_num += 1
        path = output_dir / f"{prefix}_{page_num:03d}.{fmt}"
        img.save(str(path), **save_kwargs)
        saved.append(path)
        img.close()

    doc.close()

    if merge and len(saved) > 1:
        merged_path = output_dir / f"{prefix}_merged.{fmt}"
        _merge_from_files(saved, merged_path, save_kwargs, max_width)
        saved.append(merged_path)

    return page_count, saved


def _merge_from_files(
    image_paths: list[Path],
    output_path: Path,
    save_kwargs: dict,
    max_width: int | None = None,
) -> None:
    sizes: list[tuple[int, int]] = []
    for p in image_paths:
        with Image.open(str(p)) as img:
            sizes.append((img.width, img.height))

    width = max(w for w, _ in sizes)
    height = sum(h for _, h in sizes)
    merged = Image.new("RGB", (width, height), (255, 255, 255))

    y = 0
    for p, (_, h) in zip(image_paths, sizes):
        with Image.open(str(p)) as img:
            merged.paste(img.convert("RGB"), (0, y))
        y += h

    merged = _resize(merged, max_width)
    merged.save(str(output_path), **save_kwargs)
    merged.close()
