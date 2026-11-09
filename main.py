"""Starts the app: `python main.py`. PyInstaller builds from this file too."""
import sys

from ocrmath.app import main

if __name__ == "__main__":
    # Import the normal application first so frozen dependency failures are
    # caught by CI, without opening windows or touching user configuration.
    if sys.argv[1:] == ["--smoke-test"]:
        from io import BytesIO

        from PIL import Image, __version__ as pillow_version
        from pypdf import PdfReader, PdfWriter

        if not pillow_version:
            raise RuntimeError("Pillow version is missing")
        with Image.new("RGB", (1, 1)) as image:
            image.save(BytesIO(), format="PNG")
        pdf = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(pdf)
        pdf.seek(0)
        if len(PdfReader(pdf).pages) != 1:
            raise RuntimeError("PDF round-trip failed")
        sys.exit(0)
    sys.exit(main())
