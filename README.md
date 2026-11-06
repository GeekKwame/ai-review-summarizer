# AI Review Summarizer API

A small Django REST Framework project for learning how to deploy Django with PostgreSQL, Gunicorn, systemd, and Nginx.

The API stores products and customer reviews, then uses the OpenAI API to generate a summary of the ten most recent reviews. A saved summary can be regenerated once every seven days.

## Stack

- Python and Django 5
- Django REST Framework
- PostgreSQL in production, SQLite for local development
- OpenAI Responses API
- Gunicorn and Nginx for production serving

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/products/` | List products and reviews |
| `GET` | `/api/products/{slug}/` | Retrieve one product |
| `POST` | `/api/products/{slug}/generate-summary/` | Generate or reuse an AI review summary |
| `GET` | `/admin/` | Django administration |

### Generate-summary responses

- `201 Created`: a new summary was generated.
- `200 OK`: the existing summary is still inside its seven-day cooldown.
- `400 Bad Request`: the product has no reviews.
- `502 Bad Gateway`: the OpenAI request failed.
- `503 Service Unavailable`: `OPENAI_API_KEY` is not configured.

## Local setup

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/<github-username>/ai-review-summarizer.git
cd ai-review-summarizer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

For local SQLite development, set `PG_DB=False`. Replace the other placeholder values as needed, then initialize the application:

```bash
python manage.py migrate
python manage.py seed_products
python manage.py runserver
```

Open `http://127.0.0.1:8000/api/products/`.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django signing secret; use a unique production value |
| `DEBUG` | Set to `False` in production |
| `ALLOWED_HOSTS` | Comma-separated domain names and server IPs |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins, including `https://` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins |
| `PG_DB` | Use PostgreSQL when `True`; otherwise use SQLite |
| `PG_DB_NAME` | PostgreSQL database name |
| `PG_DB_USER` | PostgreSQL user |
| `PG_DB_PASSWORD` | PostgreSQL password |
| `PG_DB_HOST` | PostgreSQL host, normally `localhost` |
| `PG_DB_PORT` | PostgreSQL port, normally `5432` |
| `OPENAI_API_KEY` | API key used to generate summaries |
| `OPENAI_MODEL` | OpenAI model name used by the summary endpoint |

Never commit `.env`. The repository contains `.env.example` only as a template.

## Checks and tests

```bash
python manage.py check
python manage.py test
```

## Production deployment

The complete server walkthrough is in [deploy_to_linux.md](deploy_to_linux.md). It covers:

1. Cloning the repository on Ubuntu
2. Configuring the production environment
3. Testing Gunicorn manually
4. Running Gunicorn with systemd
5. Proxying requests and serving static files with Nginx
6. Updating and troubleshooting the deployment
