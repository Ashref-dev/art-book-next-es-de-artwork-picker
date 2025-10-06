# art-book-next-es-de-artwork-picker

This file documents how to run and configure `artwork_picker.py` (the Art Book Next interactive artwork picker) and includes tips for common scenarios.

## Purpose

`artwork_picker.py` is a small Flask-based web tool that:

- Scans your ES-DE `downloaded_media` for game images (fanart / screenshots / titlescreens / miximages).
- Generates slanted previews using the theme's artwork mask.
- Lets you pick an image and save a per-system PNG into the theme artwork folders.

## Important behaviour

- The script determines the theme root using the script file location (Path(__file__).resolve().parent). This means:
  - You do NOT need to `cd` into the theme folder before running the script.
  - You can run the script from any directory as long as you call the script by path, e.g. `python3 /path/to/artwork_picker.py`.
- The script still requires that it resides in the correct theme root directory (it checks that `_inc/systems/artwork` exists relative to the script). If you move the script out of the theme folder it will exit with an error.

## Requirements

- Python 3.8+
- Pillow (PIL)
- Flask

Install requirements (recommended inside a virtual environment):

```bash
pip3 install pillow flask
```

## Run examples

- From the theme directory (recommended):

```bash
cd /Users/you/ES-DE/themes/art-book-next-es-de
python3 artwork_picker.py
```

- From any other directory (script still resolves theme root from its file location):

```bash
cd ~/Downloads
python3 /Users/you/ES-DE/themes/art-book-next-es-de/artwork_picker.py
```

Open http://localhost:5000 in your browser after the server starts.

## ES-DE auto-detection

The script tries to find your ES-DE installation by checking these default locations (edit `ESDE_PATHS` in the script if needed):

- `~/ES-DE`
- `~/Library/Application Support/ES-DE`
- `/Users/<your-username>/ES-DE`

It looks for a `downloaded_media` folder inside the ES-DE root. If you installed ES-DE elsewhere, add that path to `ESDE_PATHS` at the top of `artwork_picker.py`.

## Output (where selected images are saved)

The script writes the composite PNG for each system into the theme artwork directories it finds. By default these are (relative to the theme root):

- `_inc/systems/artwork`
- `_inc/systems/artwork-noir`
- `_inc/systems/artwork-circuit`
- `_inc/systems/artwork-outline`
- `_inc/systems/artwork-screenshots`

It only writes into directories present in your theme; missing directories are skipped.

## Quick troubleshooting

- "❌ ERROR: Not in Art Book Next theme directory" — make sure `artwork_picker.py` is inside the theme directory and `_inc/systems/artwork` exists.
- "❌ ERROR: ES-DE installation not found" — either install ES-DE in a default location or add your ES-DE root to `ESDE_PATHS` in the script.
- Missing Python packages — run `pip3 install pillow flask`.
- Mask load failures — ensure `_inc/systems/artwork` contains at least one non-`_default.png` PNG file used to extract the alpha mask.

## Optional improvements

If you'd like I can modify the script to accept command-line arguments, for example:

- `--theme-root /path/to/theme` to explicitly override the detected theme root
- `--esde-root /path/to/ES-DE` to override ES-DE detection

This makes running from other scripts or CI easier.
