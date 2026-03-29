# 🤖 BROKAI – Lead Intelligence System

> Upload a spreadsheet. Get a fully researched lead list with contact details and personalised outreach messages — powered by a multi-agent AI pipeline.

---

## 📌 What It Does

BROKAI takes a simple Excel sheet containing company names and locations, then automatically:

1. **Researches** each company online (what they do, size signals, digital presence, existing tools)
2. **Finds contacts** (phone number, email, WhatsApp) by scraping their website, IndiaMart, and JustDial
3. **Writes a personalised cold outreach message** ready to send over WhatsApp or email

All three steps are wired together as a [LangGraph](https://github.com/langchain-ai/langgraph) multi-agent pipeline running behind a FastAPI backend with a clean one-page frontend.

---

## 🖼️ Output

<!-- Add your output screenshot(s) here -->

---

## 🏗️ Architecture

```
Excel Upload  →  FastAPI  →  LangGraph Pipeline
                                      │
                            ┌─────────▼─────────┐
                            │   Agent 01        │
                            │   Researcher      │  ← DuckDuckGo Search + Web Scraping + Gemini / Groq
                            └─────────┬─────────┘
                                      │  business profile
                            ┌─────────▼─────────┐
                            │   Agent 02        │
                            │   Contact Finder  │  ← Regex + Website Scraping + IndiaMart/JustDial + Gemini / Groq
                            └─────────┬─────────┘
                                      │  contact card
                            ┌─────────▼─────────┐
                            │   Agent 03        │
                            │   Outreach Writer │  ← Gemini / Groq
                            └─────────┬─────────┘
                                      │
                               JSON Response  →  Frontend Table
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, LangGraph, LangChain |
| LLM | Google Gemini 1.5 Flash (free) **or** Groq (Llama 3) |
| Search | DuckDuckGo (free, no API key needed) |
| Scraping | httpx + BeautifulSoup4 |
| Frontend | Vanilla HTML / CSS / JavaScript |
| Deployment | Render (backend) + Vercel (frontend) |

---

## ⚙️ How It Works (Step by Step)

### 1 – You provide an Excel file
The sheet must have at least two columns: **Company Name** and **Location**.

| Company Name | Location |
|---|---|
| Acme Clinic | Mumbai |
| XYZ Plumbers | Pune |

### 2 – Agent 01: Researcher
- Runs four parallel DuckDuckGo searches for the company
- Scrapes the most likely website pages (`/about`, `/services`, etc.)
- Feeds the raw text into Gemini (or Groq) to extract a structured JSON profile:
  - `what_they_do`, `size_signals`, `digital_presence`, `existing_tools`, `website_url`

### 3 – Agent 02: Contact Finder
Uses a multi-strategy approach (tries each in order until contacts are found):
1. Scrapes `/contact`, `/contact-us`, `/about`, `/reach-us` pages of the company website
2. Searches IndiaMart and JustDial directories
3. Falls back to Gemini / Groq LLM extraction from DuckDuckGo snippets

### 4 – Agent 03: Outreach Writer
Receives the full profile and contact card, then prompts Gemini / Groq to write a human-sounding, ≤5-sentence WhatsApp-style cold outreach message.

### 5 – Results
The frontend polls the backend for live progress and renders results in a table with:
- Company overview, size & digital presence, existing tools
- Phone, email, and WhatsApp contact info
- Ready-to-send outreach message

---

## 🚀 How to Run Locally

### Prerequisites
- Python 3.10+
- A free [Google Gemini API key](https://aistudio.google.com) **or** a [Groq API key](https://console.groq.com) (optional)

### 1 – Clone the repository
```bash
git clone https://github.com/Arohi-jd/BROKAI-.git
cd BROKAI-/brokai-lead-intel/backend
```

### 2 – Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3 – Configure environment variables
```bash
cp .env.example .env
```
Open `.env` and fill in your API key(s):
```env
GEMINI_API_KEY=your_gemini_api_key_here
# Optional – if set, Groq (Llama 3) is used instead of Gemini
GROQ_API_KEY=your_groq_api_key_here
```

### 4 – Start the backend
```bash
uvicorn main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.

### 5 – Open the frontend
Open `brokai-lead-intel/frontend/index.html` directly in your browser.

> **Note:** The frontend points to `http://127.0.0.1:8000` by default. If you change the backend address, update the `API_BASE` constant at the top of `index.html`.

### 6 – Upload and run
1. Click **Choose File** and select your `.xlsx` file
2. Click **Run Pipeline**
3. Watch per-row progress update live; results appear in the table when complete

---

## 🔑 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes (if not using Groq) | Google Gemini API key – get one free at [aistudio.google.com](https://aistudio.google.com) |
| `GROQ_API_KEY` | No | Groq API key – if set, Llama 3 models are used instead of Gemini |

---

## 📂 Project Structure

```
brokai-lead-intel/
├── backend/
│   ├── main.py              # FastAPI app & endpoints
│   ├── pipeline.py          # LangGraph pipeline definition
│   ├── agents/
│   │   ├── researcher.py    # Agent 01 – company profile builder
│   │   ├── contact_finder.py# Agent 02 – phone/email/WhatsApp finder
│   │   └── outreach_writer.py# Agent 03 – personalised message writer
│   ├── utils/
│   │   ├── scraper.py       # httpx + BeautifulSoup web scraper
│   │   └── search.py        # DuckDuckGo search wrapper
│   ├── requirements.txt
│   ├── .env.example
│   └── sample.xlsx          # Example input file
└── frontend/
    └── index.html           # Single-page UI
```

---

## 🌐 API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/process` | Synchronous – upload Excel and wait for all results |
| `POST` | `/process/start` | Async – upload Excel, receive a `job_id` |
| `GET` | `/process/status/{job_id}` | Poll progress and retrieve results for an async job |

---

## 📝 Excel Input Format

The uploaded file must be `.xlsx` or `.xls`. Column names are case-insensitive; the first two columns are used if the expected names are not found.

| Company Name | Location |
|---|---|
| Acme Clinic | Mumbai |
| XYZ Plumbers | Pune |
| Green Farms Co | Delhi |
