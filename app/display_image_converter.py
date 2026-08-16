"""High-quality color image conversion for monochrome SSD1306 displays."""


def convert_image(path, width, height, scaling="fit", dither=True,
                  brightness=128, auto_background=True,
                  orientation="horizontal"):
    """Return a row-major list of booleans and conversion metadata.

    Pipeline: grayscale, background polarity detection, content crop,
    autocontrast, Lanczos resize, unsharp mask, and Floyd-Steinberg dithering.
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required for image conversion. Install requirements.txt."
        ) from exc

    source = Image.open(path).convert("RGBA")
    rgb = Image.new("RGB", source.size, "white")
    rgb.paste(source, mask=source.getchannel("A"))
    gray = ImageOps.grayscale(rgb)

    histogram = gray.histogram()
    total = sum(histogram)
    midpoint = total // 2
    cumulative = 0
    median = 0
    for value, count in enumerate(histogram):
        cumulative += count
        if cumulative >= midpoint:
            median = value
            break
    light_background = auto_background and median >= 160
    if light_background:
        gray = ImageOps.invert(gray)

    # Remove screenshot/window frames before finding the actual artwork. A
    # dark rounded frame around a light picture becomes a bright line after
    # polarity inversion and would otherwise be mistaken for display content.
    edge = max(2, min(gray.size) // 32)
    if gray.width > edge * 2 and gray.height > edge * 2:
        gray = gray.crop((edge, edge, gray.width - edge, gray.height - edge))
    foreground = gray.point(lambda value: 255 if value > 12 else 0)
    bbox = foreground.getbbox()
    if bbox:
        gray = gray.crop(bbox)

    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1, percent=160, threshold=2))

    logical_size = (height, width) if orientation != "horizontal" else (width, height)
    logical_width, logical_height = logical_size
    if scaling == "stretch":
        canvas = gray.resize(logical_size, Image.Resampling.LANCZOS)
    elif scaling == "crop":
        # Slightly favor the upper region, where faces commonly occur in
        # portrait artwork, while still centering horizontally.
        canvas = ImageOps.fit(
            gray, logical_size, Image.Resampling.LANCZOS,
            centering=(0.5, 0.38),
        )
    else:
        resized = ImageOps.contain(gray, logical_size, Image.Resampling.LANCZOS)
        canvas = Image.new("L", logical_size, 0)
        canvas.paste(resized, ((logical_width - resized.width) // 2,
                               (logical_height - resized.height) // 2))

    # Reuse the UI threshold as a brightness bias: 128 is neutral.
    delta = int(brightness) - 128
    if delta:
        canvas = canvas.point(lambda value: max(0, min(255, value + delta)))
    canvas = ImageEnhance.Contrast(canvas).enhance(1.15)
    if dither:
        mono = canvas.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        mono = canvas.point(lambda value: 255 if value >= 128 else 0).convert("1")

    if orientation == "clockwise":
        mono = mono.transpose(Image.Transpose.ROTATE_270)
    elif orientation == "counter_clockwise":
        mono = mono.transpose(Image.Transpose.ROTATE_90)

    pixels = [bool(value) for value in mono.getdata()]
    return pixels, {
        "source_size": source.size,
        "content_size": gray.size,
        "light_background": light_background,
        "median_luminance": median,
        "orientation": orientation,
    }
