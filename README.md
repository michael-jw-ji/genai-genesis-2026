# WasteLess

WasteLess helps restaurants prep closer to demand by combining their own operating data with weather and local event signals. The goal is simple: reduce overproduction, cut food waste, and support smarter daily planning.

## Why it matters
Restaurants often overstock and overprep to avoid stockouts during service. When traffic comes in lower than expected, that buffer turns into wasted ingredients, wasted labor, and unnecessary environmental impact.

WasteLess reframes that decision with better forecasting inputs.

## What WasteLess does
- Takes in restaurant sales data and turns it into model-ready features
- Layers in weather and event context that can affect traffic
- Forecasts likely usage and prep demand
- Surfaces a cleaner workflow through a restaurant-facing web app

## Product highlights
- Restaurant-specific data flow
- Weather-aware forecasting
- Event-aware demand context
- Upload-based workflow for CSV sales data
- Waste reduction and sustainability angle built into the product story

## Tech stack
- Frontend: React + TypeScript + Vite
- Backend/API: FastAPI
- Data/ML: Python, pandas, joblib, scikit-learn-style model artifacts

## Repo structure

```text
.
├── apps/
│   └── web/                  # React frontend
├── data/
│   ├── raw/
│   │   ├── events/
│   │   ├── inventory/
│   │   ├── recipes/
│   │   ├── uploads/
│   │   ├── waste/
│   │   └── weather/
│   └── processed/
├── models_dir/               # trained model artifacts
├── scripts/
│   └── data/                 # data utilities
├── api.py                    # FastAPI upload/prediction endpoint
├── agents_core.py            # forecasting + optimization helpers
├── dataset_creator.py        # dataset assembly pipeline
├── ingest_uploads.py         # convert uploads into pipeline format
├── train_model.py            # model training entrypoint
└── README.md
```

## Key files
- [apps/web](/Users/liamzhang/GitHub/Hackathons/WasteLess/apps/web): frontend experience for home, mission, privacy, and upload pages
- [api.py](/Users/liamzhang/GitHub/Hackathons/WasteLess/api.py): backend endpoint for uploading sales CSVs and generating predictions
- [agents_core.py](/Users/liamzhang/GitHub/Hackathons/WasteLess/agents_core.py): forecasting, optimization, and summary logic
- [ingest_uploads.py](/Users/liamzhang/GitHub/Hackathons/WasteLess/ingest_uploads.py): normalizes uploaded sales/weather/events files into the project data format
- [data/raw](/Users/liamzhang/GitHub/Hackathons/WasteLess/data/raw): source inputs including weather, events, recipes, inventory, waste, and upload staging files
- [data/processed](/Users/liamzhang/GitHub/Hackathons/WasteLess/data/processed): cleaned and joined modeling outputs
- [models_dir](/Users/liamzhang/GitHub/Hackathons/WasteLess/models_dir): trained model and feature-column artifacts

## Current data flow
1. Upload or stage restaurant sales data.
2. Normalize raw inputs and join them with weather and event context.
3. Build weekly features for forecasting.
4. Run the trained model.
5. Return predicted usage and estimated savings.

## Running the project

### Frontend
```bash
cd apps/web
npm install
npm run dev
```

### Backend API
```bash
python api.py
```

### Data pipeline
```bash
python ingest_uploads.py
python train_model.py
```

## Demo-ready framing
WasteLess is not just a forecasting demo. It is a decision-support tool for restaurant operations, built around a real waste problem:

- better planning inputs
- tighter prep targets
- less food waste
- stronger sustainability outcomes

## What's next
- Add a stronger live events pipeline
- Improve event attendance and impact scoring
- Expand from forecast output to clearer prep recommendations
- Validate the workflow with real restaurant operators
