# Brokai Lead Intelligence System

A multi-agent pipeline that researches companies, finds contact info,
and generates personalised cold outreach messages automatically.

Live App: [https://YOUR-VERCEL-URL.vercel.app](https://YOUR-VERCEL-URL.vercel.app)  
Backend API: [https://YOUR-RENDER-URL.onrender.com](https://YOUR-RENDER-URL.onrender.com)

## Architecture

Excel Upload → FastAPI → LangGraph Pipeline
                              │
                    ┌─────────▼─────────┐
                    │   Agent 01        │
                    │   Researcher      │ ← DuckDuckGo + Groq/Gemini
                    └─────────┬─────────┘
                              │ business profile
                    ┌─────────▼─────────┐
                    │   Agent 02        │
                    │   Contact Finder  │ ← Regex + Scraping + Groq/Gemini
                    └─────────┬─────────┘
                              │ contact card
                    ┌─────────▼─────────┐
                    │   Agent 03        │
                    │   Outreach Writer │ ← Groq/Gemini
                    └─────────┬─────────┘
                              │
                         JSON Response → Frontend Table

## Tech Stack

- Backend: Python, FastAPI, LangGraph, LangChain
- LLM: Groq (primary) or Gemini (fallback)
- Search: DuckDuckGo (free, no API key)
- Scraping: httpx + BeautifulSoup
- Frontend: Vanilla HTML/CSS/JS
- Deployment: Render (backend) + Vercel (frontend)

## How to Run Locally

1. Clone the repo
   git clone your-repo-url
   cd brokai-lead-intel/backend

2. Install dependencies
   pip install -r requirements.txt

3. Set up environment variables
   cp .env.example .env
   Edit .env and add your GROQ_API_KEY
   (Optional fallback) add GEMINI_API_KEY

4. Run the backend
   uvicorn main:app --reload

5. Open frontend/index.html in your browser
   Set API URL in the input box to [http://127.0.0.1:8000](http://127.0.0.1:8000) and click Save API URL

## Environment Variables

See .env.example
GROQ_API_KEY — get from [https://console.groq.com/keys](https://console.groq.com/keys)
GEMINI_API_KEY — optional fallback from [https://aistudio.google.com](https://aistudio.google.com)

## Deploy Backend on Render

1. Push this repository to GitHub.
2. In Render, create a new Web Service from the repo.
3. Set Root Directory to backend.
4. Build Command: pip install -r requirements.txt
5. Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
6. Add environment variables:
   - GROQ_API_KEY (required)
   - GEMINI_API_KEY (optional fallback)
7. Deploy and copy your Render URL.

You can also use render.yaml from repo root for faster setup.

## Deploy Frontend on Vercel

1. Import the repo in Vercel.
2. Set Root Directory to frontend.
3. Deploy.
4. Open deployed app and set API URL to your Render backend URL in the API input field.
5. Click Save API URL once; it is stored in browser localStorage.

## Excel Format

| Company Name | Location |
| --- | --- |
| Acme Clinic | Mumbai |
| XYZ Plumbers | Pune |
