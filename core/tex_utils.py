import io
import os
from PIL import Image, ImageOps


def get_image(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Image not found: {path}")
    return Image.open(path)


def resize_image(image, target_size, keep_aspect=True):
    if keep_aspect:
        image.thumbnail(target_size, Image.LANCZOS)
        return image
    return image.resize(target_size, Image.LANCZOS)


def invert_image(image):
    if image.mode == 'RGBA':
        r, g, b, a = image.split()
        inverted = ImageOps.invert(Image.merge("RGB", (r, g, b)))
        r2, g2, b2 = inverted.split()
        return Image.merge("RGBA", (r2, g2, b2, a))
    return ImageOps.invert(image)


def adjust_reflectivity(image, factor=0.5):
    """
    0.5 = identity, 0.0 = fully black, 1.0 = fully white.
    """
    factor = max(0.0, min(1.0, factor))
    if image.mode not in ("L", "RGB", "RGBA"):
        raise ValueError(f"Unsupported mode: {image.mode}")

    has_alpha = image.mode == "RGBA"
    if has_alpha:
        r, g, b, a = image.split()
        base = Image.merge("RGB", (r, g, b))
    else:
        base = image.copy()

    if factor <= 0.5:
        opacity = (0.5 - factor) * 2
        def apply(p):
            burned = 255 if p == 255 else 0
            return max(0, min(255, int(p * (1 - opacity) + burned * opacity)))
    else:
        opacity = (factor - 0.5) * 2
        apply = lambda p: max(0, min(255, int(p * (1 - opacity) + 255 * opacity)))

    if base.mode == "L":
        result = base.point(apply)
    else:
        r, g, b = base.split()
        result = Image.merge("RGB", (r.point(apply), g.point(apply), b.point(apply)))

    if has_alpha:
        r2, g2, b2 = result.split()
        return Image.merge("RGBA", (r2, g2, b2, a))
    return result


def _save_jpeg(image, path, compression, source_info=None):
    buffer = io.BytesIO()
    if compression == "Uncompressed" and source_info and "quantization" in source_info:
        subsampling = source_info.get("subsampling", 2)
        image.save(buffer, format="JPEG", qtables=source_info["quantization"],
                   subsampling=subsampling, optimize=True)
    else:
        quality = {"Uncompressed": 100, "Auto": 80, "Smallest Size": 40,
                   "Balanced": 65, "Higher Quality": 90}[compression]
        subsampling = 0 if compression == "Uncompressed" else -1
        image.save(buffer, format="JPEG", quality=quality, subsampling=subsampling, optimize=True)
    jpeg_bytes = buffer.getvalue()
    try:
        from mozjpeg_lossless_optimization import optimize
        jpeg_bytes = optimize(jpeg_bytes)
    except ImportError:
        pass
    with open(path, "wb") as f:
        f.write(jpeg_bytes)
    image.close()


def _save_png(image, path, compression):
    params = {
        "Uncompressed":  (256, 0,   100),
        "Auto":          (256, 70,  85),
        "Smallest Size": (64,  0,   70),
        "Balanced":      (128, 40,  80),
        "Higher Quality":(256, 80,  100),
    }
    max_colors, min_q, max_q = params[compression]
    if compression != "Uncompressed":
        try:
            import imagequant
            image = imagequant.quantize_pil_image(
                image, dithering_level=1.0,
                max_colors=max_colors, min_quality=min_q, max_quality=max_q,
            )
        except ImportError:
            if image.mode != 'RGBA':
                image = image.quantize(colors=max_colors)
    image.save(path, format="PNG", optimize=True)
    image.close()


def save_image(image, path, format=None, compression="Uncompressed", source_info=None):
    if format == "JPEG":
        _save_jpeg(image, path, compression, source_info=source_info)
    elif format == "PNG":
        _save_png(image, path, compression)
    elif format == "WEBP":
        if compression == "Uncompressed":
            image.save(path, format="WEBP", lossless=True)
        else:
            quality = {"Auto": 80, "Smallest Size": 40, "Balanced": 70, "Higher Quality": 90}[compression]
            image.save(path, format="WEBP", quality=quality)
        image.close()
    else:
        image.save(path, format=format)
        image.close()
