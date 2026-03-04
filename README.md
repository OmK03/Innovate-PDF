# PDF Studio (Flask)

A small Flask web application with a modern UI for common PDF tasks:

- Merge multiple PDFs into a single document.
- Split a PDF by page ranges (for example `1-3,5,7-9`).
- Extract all text from a PDF into a `.txt` file.

## Setup

1. **Create and activate a virtual environment** (recommended):

```bash
cd path/to/cur
python -m venv .venv
.venv\Scripts\activate  # on Windows PowerShell / CMD
```

2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

3. **Run the app**:

```bash
python app.py
```

4. Open your browser and visit:

```text
http://127.0.0.1:5000
```

## Notes

- All processing is done in memory; no PDFs are stored permanently on disk.
- For production, change the `SECRET_KEY` in `app.py` and run behind a proper WSGI server.

