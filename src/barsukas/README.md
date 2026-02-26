# Barsukas

Barsukas is Greenland's Flask-based editor for managing multilingual linguistic
data used by Trakaido.

## Core capabilities

- Browse/search lemmas and edit core lexical data.
- Manage translations across supported languages.
- Review and edit sentence content.
- Trigger selected agent workflows from the UI.
- Track changes through operation logging/audit views.
- Export selected data views for downstream use.

## Run locally

From the repository root:

```bash
PYTHONPATH=src python src/barsukas/app.py
```

Default URL: `http://127.0.0.1:5555`

Optional flags:

```bash
PYTHONPATH=src python src/barsukas/app.py --port 8080
PYTHONPATH=src python src/barsukas/app.py --readonly
```

## Background worker (for queued LLM-heavy tasks)

Some actions enqueue asynchronous tasks. Run the worker in a second shell:

```bash
PYTHONPATH=src python -m workqueue.worker --poll-interval 2
```

## High-level structure

```text
barsukas/
├── app.py            # Flask app entry point
├── routes/           # Feature blueprints (lemmas, translations, sentences, etc.)
├── templates/        # Jinja templates
├── static/           # Front-end assets
└── config.py         # Runtime configuration
```

Barsukas is intended for local/internal use and binds to localhost by default.
