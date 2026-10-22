# Smart Travel Recommendation — Hamza

A Django application for destination recommendations and itinerary planning with weather and Groq integrations.

## Features

- User accounts and travel profiles
- Destination recommendations and distance calculation
- Trip planning with fallback itineraries
- Saved itinerary management and feedback

## Technology

Python, Django and SQLite.

## Local setup

Clone the repository:

```bash
git clone https://github.com/nasirabbas827/Smart-Travel-Recom-Hamza.git
cd Smart-Travel-Recom-Hamza
```

Use a virtual environment:

```bash
python -m venv .venv
# Windows:
# .venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate
python -m pip install django requests groq
```

The install command lists packages used by the inspected source; this repository does not include a pinned dependency file. Saved machine learning models may require the versions used during training.

Review the configuration in `myproject/settings.py`, then initialize the database and start the development server:

```bash
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. The repository includes `db.sqlite3`; back it up before applying migrations to existing data. Use the application's registration or admin workflow to create an account; no login credentials are documented here.

## Project-specific setup

Review `myapp/services.py` and Django settings for Groq, weather and attraction service configuration. Use your own credentials. Fallback itineraries are available in the application code.

## Repository layout

| Path | Purpose |
|---|---|
| `db.sqlite3` | Application database |
| `destinations/` | Project resources |
| `manage.py` | Django command-line entry point |
| `myapp/` | Application code |
| `myproject/` | Django configuration |
| `templates/` | HTML templates |

## Development notes

Setup steps describe local development. Configure your own database, mail and API credentials where applicable. Review debug settings and replace development secrets before deploying. The application was not executed as part of this documentation update.

Maintained by [Nasir Abbas](https://github.com/nasirabbas827).
