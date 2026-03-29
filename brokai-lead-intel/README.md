# Brokai Lead Intelligence System

A multi-agent pipeline that researches companies, finds contact info,
and generates personalised cold outreach messages — automatically.

**Live App:** https://YOUR-VERCEL-URL.vercel.app
**Backend API:** https://YOUR-RENDER-URL.onrender.com

## Architecture

Excel Upload → FastAPI → LangGraph Pipeline
                              │
                    ┌─────────▼─────────┐
                    │   Agent 01        │
                    │   Researcher      │ ← DuckDuckGo + Gemini
                    └─────────┬─────────┘
                              │ business profile
                    ┌─────────▼─────────┐
                    │   Agent 02        │
                    │   Contact Finder  │ ← Regex + Scraping + Gemini
                    └─────────┬─────────┘
                              │ contact card
                    ┌─────────▼─────────┐
                    │   Agent 03        │
                    │   Outreach Writer │ ← Gemini
                    └─────────┬─────────┘
                              │
                         JSON Response → Frontend Table

## Tech Stack

- Backend: Python, FastAPI, LangGraph, LangChain
- LLM: Google Gemini 1.5 Flash (free tier)
- Search: DuckDuckGo (free, no API key)
- Scraping: httpx + BeautifulSoup
- Frontend: Vanilla HTML/CSS/JS
- Deployment: Render (backend) + Vercel (frontend)

## How to Run Locally

1. Clone the repo
   git clone https://github.com/yourusername/brokai-lead-intel
   cd brokai-lead-intel/backend

2. Install dependencies
   pip install -r requirements.txt

3. Set up environment variables
   cp .env.example .env
   Edit .env and add your GEMINI_API_KEY

4. Run the backend
   uvicorn main:app --reload

5. Open frontend/index.html in your browser
   Update API_BASE in index.html to http://localhost:8000

## Environment Variables

See .env.example
GEMINI_API_KEY — get free at https://aistudio.google.com

## Excel Format

| Company Name | Location |
|---|---|
| Acme Clinic | Mumbai |
| XYZ Plumbers | Pune |
