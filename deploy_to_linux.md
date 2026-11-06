# Deploy Django with Gunicorn and Nginx on Ubuntu

This guide deploys this repository as a production-style Django application. PostgreSQL setup is assumed to be complete.

The request path will be:

```text
Browser -> Nginx -> Unix socket -> Gunicorn -> Django -> PostgreSQL
```

## Before you begin

You need:

- An Ubuntu server with a non-root sudo user
- SSH access to the server
- A PostgreSQL database, user, and password
- Your server IP address or domain name
- An OpenAI API key if you want to use the summary endpoint

This guide uses the following example values. Replace them with your own:

| Item | Example |
| --- | --- |
| Linux user | `deploy` |
| Repository | `ai-review-summarizer` |
| Project directory | `/home/deploy/ai-review-summarizer` |
| Django module | `review_summarizer` |
| systemd service | `review-summarizer` |

## 1. Install server packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev libpq-dev nginx git curl
```

If UFW is enabled, keep SSH available:

```bash
sudo ufw allow OpenSSH
```

## 2. Clone the repository

Run these commands as your regular Linux user:

```bash
cd ~
git clone https://github.com/<github-username>/ai-review-summarizer.git
cd ai-review-summarizer
```

For a private repository, authenticate with a deploy key, GitHub CLI, or a fine-grained token. Do not put a token directly in a command that will remain in shell history.

## 3. Create the virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Confirm that Gunicorn was installed inside the virtual environment:

```bash
which gunicorn
gunicorn --version
```

The path should end with `ai-review-summarizer/.venv/bin/gunicorn`.

## 4. Configure production environment variables

Create the local environment file from the template:

```bash
cp .env.example .env
nano .env
```

Use production values similar to these:

```dotenv
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=False
ALLOWED_HOSTS=your_server_ip,your_domain
CSRF_TRUSTED_ORIGINS=https://your_domain
CORS_ALLOWED_ORIGINS=https://your_frontend_domain

PG_DB=True
PG_DB_NAME=review_summarizer
PG_DB_USER=review_summarizer_user
PG_DB_PASSWORD=replace-with-your-database-password
PG_DB_HOST=localhost
PG_DB_PORT=5432

OPENAI_API_KEY=replace-with-your-openai-api-key
OPENAI_MODEL=gpt-5.1
```

If you are testing with only an IP address and plain HTTP, leave `CSRF_TRUSTED_ORIGINS` empty. Restrict access to the environment file:

```bash
chmod 600 .env
```

Generate a new Django secret key on the server if needed:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 5. Initialize Django

Apply committed migrations. Do not run `makemigrations` during deployment:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
python manage.py check --deploy
```

`check --deploy` may report HTTPS-related warnings until TLS is configured. Fix any other warnings before continuing.

Optionally create an administrator and sample data:

```bash
python manage.py createsuperuser
python manage.py seed_products
```

## 6. Test Django directly

For a server-local test, bind Django to localhost:

```bash
python manage.py runserver 127.0.0.1:8000
```

In a second SSH session:

```bash
curl http://127.0.0.1:8000/api/products/
```

Stop the development server with `Ctrl+C`.

If you choose to test from your browser instead, temporarily open port 8000 and bind to all interfaces. Close the port immediately after the test.

```bash
sudo ufw allow 8000/tcp
python manage.py runserver 0.0.0.0:8000
sudo ufw delete allow 8000/tcp
```

## 7. Test Gunicorn manually

From the project directory with the virtual environment active:

```bash
gunicorn --bind 127.0.0.1:8000 review_summarizer.wsgi:application
```

Test it in another SSH session:

```bash
curl http://127.0.0.1:8000/api/products/
```

Stop Gunicorn with `Ctrl+C`. This proves that Gunicorn can import and serve the Django WSGI application.

## 8. Run Gunicorn with systemd

Create a dedicated service:

```bash
sudo nano /etc/systemd/system/review-summarizer.service
```

Use the following configuration, replacing `deploy` and the paths when necessary:

```ini
[Unit]
Description=Gunicorn for AI Review Summarizer
After=network.target postgresql.service

[Service]
Type=simple
User=deploy
Group=www-data
WorkingDirectory=/home/deploy/ai-review-summarizer
EnvironmentFile=/home/deploy/ai-review-summarizer/.env
RuntimeDirectory=review-summarizer
RuntimeDirectoryMode=0755
UMask=0007
ExecStart=/home/deploy/ai-review-summarizer/.venv/bin/gunicorn \
    --workers 3 \
    --access-logfile - \
    --error-logfile - \
    --bind unix:/run/review-summarizer/gunicorn.sock \
    review_summarizer.wsgi:application
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Why these settings matter:

- `WorkingDirectory` makes Django load the correct project.
- `EnvironmentFile` supplies the production configuration.
- `RuntimeDirectory` creates a clean socket directory at every boot.
- `UMask=0007` lets Nginx, running in the `www-data` group, access the socket.
- `Restart=on-failure` recovers from unexpected Gunicorn exits.

Load, enable, and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now review-summarizer
sudo systemctl status review-summarizer
```

Test the Unix socket directly:

```bash
curl --unix-socket /run/review-summarizer/gunicorn.sock http://localhost/api/products/
```

View recent logs if the service fails:

```bash
sudo journalctl -u review-summarizer -n 100 --no-pager
```

## 9. Configure Nginx

Create a server block:

```bash
sudo nano /etc/nginx/sites-available/review-summarizer
```

Paste this configuration and replace the server name and home-directory path:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name your_server_ip your_domain;

    client_max_body_size 10M;

    location /static/ {
        alias /home/deploy/ai-review-summarizer/staticfiles/;
    }

    location /media/ {
        alias /home/deploy/ai-review-summarizer/media/;
    }

    location / {
        include proxy_params;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://unix:/run/review-summarizer/gunicorn.sock;
    }
}
```

Nginx must be able to traverse the home directory to read static files:

```bash
sudo chmod 711 /home/deploy
```

Enable the site, verify the configuration, and reload Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/review-summarizer /etc/nginx/sites-enabled/review-summarizer
sudo nginx -t
sudo systemctl reload nginx
```

If this server hosts only this application, you can disable the default site:

```bash
sudo unlink /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

## 10. Update firewall rules

Allow web traffic and confirm the rules:

```bash
sudo ufw allow 'Nginx Full'
sudo ufw status
```

Visit `http://your_server_ip/api/products/` or your configured domain.

## 11. Add HTTPS

When your domain points to the server, install Certbot and request a certificate:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your_domain
sudo certbot renew --dry-run
```

After HTTPS works, ensure `.env` contains:

```dotenv
DEBUG=False
ALLOWED_HOSTS=your_domain
CSRF_TRUSTED_ORIGINS=https://your_domain
```

Then restart Gunicorn:

```bash
sudo systemctl restart review-summarizer
```

## 12. Deploy future updates

For each update:

```bash
cd /home/deploy/ai-review-summarizer
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
sudo systemctl restart review-summarizer
sudo systemctl reload nginx
```

## Troubleshooting

### Gunicorn does not start

```bash
sudo systemctl status review-summarizer
sudo journalctl -u review-summarizer -n 100 --no-pager
```

Check the Linux user, project paths, `.env`, and WSGI target in the service file. After editing it, run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart review-summarizer
```

### Nginx returns 502 Bad Gateway

```bash
sudo systemctl status review-summarizer
sudo ls -l /run/review-summarizer/gunicorn.sock
sudo tail -n 100 /var/log/nginx/error.log
```

A 502 normally means Gunicorn is stopped or Nginx cannot access the socket.

### Static files return 404 or 403

```bash
python manage.py collectstatic --noinput
namei -l /home/deploy/ai-review-summarizer/staticfiles
sudo tail -n 100 /var/log/nginx/error.log
```

Confirm that the Nginx `alias` ends with `/` and matches `STATIC_ROOT`.

### Django reports `DisallowedHost`

Add the exact IP address or domain to `ALLOWED_HOSTS` in `.env`, then restart Gunicorn.

### Database connection fails

Verify all `PG_DB_*` values and test the credentials directly:

```bash
psql -h localhost -U review_summarizer_user -d review_summarizer
```

## Final verification

```bash
sudo systemctl is-active review-summarizer
sudo systemctl is-active nginx
curl -I http://your_domain/api/products/
```

Both services should report `active`, and the endpoint should return an HTTP response from Django through Nginx.
