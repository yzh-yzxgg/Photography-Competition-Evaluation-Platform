"""Generate and locate lightweight display versions of competition photos."""

from hashlib import sha1
from pathlib import Path

from PIL import Image, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parent
UPLOADS_DIR = PROJECT_ROOT / "uploads"
VARIANT_CONFIG = {
    "review": {"directory": UPLOADS_DIR / "review", "max_side": 2560, "quality": 90},
    "thumbnail": {"directory": UPLOADS_DIR / "thumbnails", "max_side": 720, "quality": 80},
}


def _safe_filename(filename):
    filename = str(filename)
    if not filename or Path(filename).name != filename:
        raise ValueError("Invalid image filename")
    return filename


def original_path(filename):
    return UPLOADS_DIR / _safe_filename(filename)


def _variant_path(filename, variant):
    if variant not in VARIANT_CONFIG:
        raise ValueError("Invalid image variant")
    safe_name = _safe_filename(filename)
    file_id = sha1(safe_name.encode("utf-8")).hexdigest()[:16]
    return VARIANT_CONFIG[variant]["directory"] / f"{file_id}.webp"


def _save_webp(source, destination, max_side, quality):
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "LA"):
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        temporary = destination.with_suffix(".tmp.webp")
        image.save(temporary, "WEBP", quality=quality, method=6)
        temporary.replace(destination)


def ensure_variant(filename, variant):
    source = original_path(filename)
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = _variant_path(filename, variant)
    if destination.is_file() and destination.stat().st_mtime >= source.stat().st_mtime:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    config = VARIANT_CONFIG[variant]
    _save_webp(source, destination, config["max_side"], config["quality"])
    return destination


def build_variants(filenames):
    """Build both variants without failing the entire setup for one bad image."""
    filenames = list(filenames)
    results = []
    total = len(filenames)
    print(f"\n[图片优化] 开始处理 {total} 张作品…")
    for index, filename in enumerate(filenames, start=1):
        print(f"[图片优化] ({index}/{total}) {filename}", end="", flush=True)
        try:
            source = original_path(filename)
            source_size = source.stat().st_size
            print(f" · 原图 {source_size / 1024 / 1024:.2f} MiB", end="", flush=True)
            review = ensure_variant(filename, "review")
            thumbnail = ensure_variant(filename, "thumbnail")
            results.append((filename, review, thumbnail))
            print(f" → 评审版 {review.stat().st_size / 1024:.0f} KiB，缩略图 {thumbnail.stat().st_size / 1024:.0f} KiB")
        except (FileNotFoundError, OSError, ValueError) as error:
            print(f" → 跳过：{error}")
    print(f"[图片优化] 完成：成功生成 {len(results)}/{total} 张作品的显示版本。\n")
    return results
