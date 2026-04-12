# Find me in the terminal

> Daily Linux commands, Vim tricks, and terminal productivity drops —
> newsletter backend built with FastAPI + Neon PostgreSQL + async email.

---

## Project Structure

```
fmitt/
├── app/
│   ├── main.py                  # FastAPI app entry point + page routes
│   ├── config.py                # All settings (reads from .env)
│   ├── database.py              # Async SQLAlchemy engine + Neon setup
│   ├── models.py                # DB tables: subscribers, emails, email_logs
│   ├── schemas.py               # Pydantic request/response models
│   ├── routers/
│   │   ├── subscribers.py       # POST /subscribe, GET /unsubscribe
│   │   └── emails.py            # POST /admin/send-daily, /admin/broadcast
│   ├── services/
│   │   └── email_service.py     # Email builder + async SMTP sender
│   ├── templates/
│   │   ├── index.html           # Landing page (served at /)
│   │   ├── unsubscribe.html     # Unsubscribe confirmation page
│   │   └── privacy.html         # Privacy policy page
│   └── static/                  # Static assets (CSS/images if needed)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml           # For local testing
├── railway.toml                 # Railway deployment config
├── render.yaml                  # Render deployment config
├── .env.example                 # Copy this to .env and fill in values
├── .dockerignore
└── .gitignore
```

---

## Quick Start — Local Development

### 1. Clone and set up Python environment

```bash
git clone https://github.com/yourname/find-me-in-the-terminal.git
cd find-me-in-the-terminal

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Set up Neon PostgreSQL (free)

1. Go to [console.neon.tech](https://console.neon.tech) and create a free account
2. Create a new project — name it `fmitt`
3. On the dashboard, click **Connection string**
4. Copy the connection string — it looks like:
   ```
   postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
5. **Important:** Change `postgresql://` to `postgresql+asyncpg://` in your `.env`

### 3. Set up Gmail App Password (for sending emails)

1. Enable 2-Factor Authentication on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Select **Mail** → **Other** → type `fmitt` → click **Generate**
4. Copy the 16-character password shown (format: `xxxx xxxx xxxx xxxx`)

### 4. Create your .env file

```bash
cp .env.example .env
```

Then open `.env` and fill in every value:

```env
APP_NAME="Find me in the terminal"
APP_URL="http://localhost:8000"
DEBUG=true

DATABASE_URL="postgresql+asyncpg://user:pass@ep-xxx.neon.tech/neondb?sslmode=require"

SMTP_HOST="smtp.gmail.com"
SMTP_PORT=587
SMTP_USER="your@gmail.com"
SMTP_PASSWORD="xxxx xxxx xxxx xxxx"
FROM_NAME="Find me in the terminal"
FROM_EMAIL="your@gmail.com"

SECRET_KEY="run-openssl-rand-hex-32-and-paste-here"
UNSUBSCRIBE_SALT="another-random-string"
```

Generate SECRET_KEY:
```bash
openssl rand -hex 32
```

### 5. Run the app

```bash
uvicorn app.main:app --reload --port 8000
```

Visit [http://localhost:8000](http://localhost:8000) — you should see the landing page.

API docs are at [http://localhost:8000/api/docs](http://localhost:8000/api/docs)

---

## API Reference

### Public Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Landing page |
| `POST` | `/subscribe` | Subscribe a new email |
| `GET` | `/unsubscribe?token=xxx` | One-click unsubscribe from email link |
| `POST` | `/unsubscribe` | Unsubscribe by email address |
| `GET` | `/health` | Health check |
| `GET` | `/privacy` | Privacy policy page |

### Admin Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/send-daily` | Send daily Linux command drop to all subscribers |
| `POST` | `/admin/broadcast` | Send custom HTML email to all subscribers |
| `GET` | `/admin/subscribers` | List all subscribers with stats |
| `GET` | `/admin/stats` | Dashboard stats (total, active, sent today) |

### Subscribe — Example

```bash
curl -X POST http://localhost:8000/subscribe \
  -H "Content-Type: application/json" \
  -d '{"email": "dev@example.com"}'
```

Response:
```json
{
  "success": true,
  "message": "Subscribed! Check dev@example.com — your Vim cheat sheet is on the way."
}
```

### Send Daily Drop — Example

```bash
curl -X POST http://localhost:8000/admin/send-daily \
  -H "Content-Type: application/json" \
  -d '{
    "command": "grep -rn \"pattern\" . --include=\"*.py\"",
    "description": "Recursively search for a pattern in all Python files with line numbers.",
    "example": "$ grep -rn \"def authenticate\" . --include=\"*.py\"\n./auth/views.py:23:def authenticate(request):",
    "tip": "Add --color=auto to highlight matches. Use -l to list only filenames."
  }'
```

### Broadcast — Example

```bash
curl -X POST http://localhost:8000/admin/broadcast \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "This week: eBPF deep dive is live",
    "html_body": "<h1>The eBPF deep dive is ready</h1><p>Read it here...</p>",
    "email_type": "deep_dive"
  }'
```

---

## Automating Daily Drops (Cron)

### Option A — System cron (on any Linux server)

```bash
crontab -e
```

Add this line to send at 06:00 UTC every day:

```cron
0 6 * * * curl -s -X POST https://your-deployed-url.com/admin/send-daily \
  -H "Content-Type: application/json" \
  -d '{"command":"find . -name","description":"Find files by name pattern","example":"$ find . -name \"*.log\" -mtime -7","tip":"Always run without -delete first to preview."}' \
  >> /var/log/fmitt_cron.log 2>&1
```

### Option B — Railway Cron Jobs (recommended)

1. In Railway dashboard → your project → **New Service** → **Cron**
2. Set schedule: `0 6 * * *`
3. Set command:
```bash
curl -X POST $APP_URL/admin/send-daily \
  -H "Content-Type: application/json" \
  -d '{"command":"...","description":"...","example":"...","tip":"..."}'
```

### Option C — GitHub Actions (free)

Create `.github/workflows/daily-drop.yml`:

```yaml
name: Daily Linux Drop
on:
  schedule:
    - cron: '0 6 * * *'   # 06:00 UTC every day
  workflow_dispatch:        # also allows manual trigger

jobs:
  send:
    runs-on: ubuntu-latest
    steps:
      - name: Send daily drop
        run: |
          curl -s -X POST ${{ secrets.APP_URL }}/admin/send-daily \
            -H "Content-Type: application/json" \
            -d '{"command":"awk NF","description":"Remove blank lines from any file instantly.","example":"$ awk NF file.txt","tip":"Combine with > output.txt to save the result."}'
```

Add `APP_URL` to your GitHub repo secrets.

---

## Deployment

### Railway (Recommended — easiest)

1. Push your code to GitHub
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub Repo**
3. Select your repo — Railway detects the `railway.toml` automatically
4. Go to **Variables** tab and add all values from `.env.example`
5. Set `APP_URL` to your Railway-provided domain (e.g. `https://fmitt.up.railway.app`)
6. Railway builds the Docker image and deploys — takes ~2 minutes
7. Visit your Railway URL — the landing page is live

### Render

1. Push to GitHub
2. Go to [render.com](https://render.com) → **New** → **Blueprint**
3. Connect your repo — Render reads `render.yaml` automatically
4. Fill in the `sync: false` environment variables in the dashboard
5. Click **Apply** — Render builds and deploys

### Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login and launch
fly auth login
fly launch                    # detects Dockerfile, asks a few questions
fly secrets set DATABASE_URL="postgresql+asyncpg://..."
fly secrets set SMTP_USER="your@gmail.com"
fly secrets set SMTP_PASSWORD="xxxx xxxx xxxx xxxx"
fly secrets set FROM_EMAIL="your@gmail.com"
fly secrets set SECRET_KEY="$(openssl rand -hex 32)"
fly secrets set APP_URL="https://your-app.fly.dev"
fly deploy
```

---

## Local Docker Testing

```bash
# Build and run with docker compose
docker compose up --build

# Visit http://localhost:8000
# API docs at http://localhost:8000/api/docs

# Stop
docker compose down
```

---

## Database Schema

Three tables are created automatically on first startup:

**`subscribers`** — every person who signs up
- `id`, `email`, `status` (active/unsubscribed), `unsubscribe_token`
- `ip_address`, `source`, `subscribed_at`, `last_emailed_at`

**`emails`** — every campaign/broadcast sent
- `id`, `email_type`, `subject`, `html_body`, `sent_at`

**`email_logs`** — one row per subscriber per email sent
- `subscriber_id`, `email_id`, `status` (sent/failed), `sent_at`, `error_message`

---

## Troubleshooting

**Emails not sending**
- Double-check `SMTP_PASSWORD` is the App Password (16 chars), not your Gmail login password
- Make sure 2FA is enabled on your Google account — App Passwords won't appear without it
- Check logs: `uvicorn` will print `✅ Email sent` or `❌ Email failed` for each attempt

**Database connection error**
- Make sure `DATABASE_URL` starts with `postgresql+asyncpg://` not `postgresql://`
- Neon free tier pauses after inactivity — the first request may be slow (cold start)
- Confirm `?sslmode=require` is at the end of your connection string

**`ModuleNotFoundError` on startup**
- Make sure your virtual environment is activated: `source .venv/bin/activate`
- Re-run: `pip install -r requirements.txt`

**Port already in use**
```bash
lsof -i :8000          # find what's using the port
kill -9 <PID>          # kill it
```
