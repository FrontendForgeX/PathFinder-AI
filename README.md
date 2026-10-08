# PathFinder

**Find what moves you forward.** A student-focused research workspace for discovering hackathons and competitions that match a student's interests, skills, and location.

PathFinder uses **SerpApi for search discovery**, then applies transparent, rule-based scoring, classification, and best-effort webpage research. It is not a trained machine-learning model. Its findings should be verified on the official event pages.

## Features

- Search by branch, year, skills, interests, and location
- Personalized opportunity scores and concise match reasons
- Date parsing, estimated statuses, and registration signals
- Profile-aware search cache to reduce API credit usage
- Reading list saved locally on your computer
- Filter by keyword or event status; sort by name, activity, or match score
- Grid/list layouts, mobile-responsive design, copy-link actions, and subtle motion
- Custom compass identity instead of a generic AI/sparkle logo

## Run on Windows

Requires Python and a SerpApi API key.

```powershell
cd D:\PathFinder-AI
python -m venv venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python app.py
```

In `.env`, set `SERPAPI_KEY=your_actual_key_here`. If you already have a working `.env`, **keep it; do not overwrite it**.

Visit **http://127.0.0.1:5000** in your browser.

## File layout

```text
app.py                 Flask server, search, matching and research
static/style.css       Responsive design
static/app.js          Dashboard interactions
templates/index.html   Dashboard markup
.env.example           Safe API key template
requirements.txt       Python packages
```

## Privacy & limitations

- `.env`, `venv/`, `cache/`, and `saved.json` are ignored by Git and must not be manually uploaded to GitHub.
- Normal searches reuse the profile's cache. **Refresh from web** requests live search results and uses SerpApi credits.
- Search results and extracted dates can be incomplete or inaccurate. `OPEN SIGNAL (VERIFY)` does **not** guarantee that registration is still open.
- The reading list is stored locally and is not synchronized across devices.
- Built for local demonstrations. Public deployment requires additional security and operational safeguards.

## Tech stack

Python · Flask · SerpApi · Requests · BeautifulSoup · Vanilla JavaScript · CSS
