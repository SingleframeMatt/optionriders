# Option Riders

Option Riders is a live intraday trading dashboard focused on high-signal watchlists, USD red-folder macro events, and Barchart-powered options flow.

## Features

- Quick watchlist with click-through ticker detail modal
- Weekly USD high-impact economic calendar
- Local-time NYSE market open badge with DST-safe conversion
- Sticky top warning bar for key daily and weekly risks
- Barchart unusual options, most traded options, and ATM spread checks

## Local development

Run the local dashboard server:

```bash
python3 server.py
```

Open:

```text
http://127.0.0.1:8125
```

## Deployment

This project is set up for Vercel:

- Static frontend served from the repo root
- Barchart proxy exposed through `api/options-flow.py`
- Routing configured in `vercel.json`

## Domain

Intended production domain:

```text
https://www.optionriders.com
```
