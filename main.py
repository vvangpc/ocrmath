"""Starts the app: `python main.py`. PyInstaller builds from this file too."""
import sys

from ocrmath.app import main

if __name__ == "__main__":
    sys.exit(main())
