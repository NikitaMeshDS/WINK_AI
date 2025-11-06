## Project structure

```
project/
├── backend/             # FastAPI app
│   ├── app/
│   │   ├── main.py      # Application entrypoint
│   │   ├── database.py  # SQLAlchemy engine and session
│   │   ├── models.py    # ORM models
│   │   ├── schemas.py   # Pydantic schemas
│   │   ├── crud.py      # Database operations
│   │   └── ml_stub.py   # Placeholder script processor
│   └── requirements.txt # Backend dependencies
├── frontend/            # React + Vite + Tailwind frontend
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── api/
│   │   │   └── index.ts
│   │   ├── components/
│   │   │   ├── UploadForm.tsx
│   │   │   ├── TableDisplay.tsx
│   │   │   ├── HistoryList.tsx
│   │   │   └── ThemeToggle.tsx
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   └── History.tsx
│   │   ├── theme/
│   │   │   └── ThemeProvider.tsx
│   │   ├── App.tsx
│   │   └── main.tsx
│   └── README.md
├── Dockerfile          # Container definition
└── README.md           # This file
```

## Running locally

### With Docker

The repository includes a `Dockerfile` that produces a single image
containing both the built frontend and the backend.  To build and run
the container, run:

```bash
docker build -t preprod-service ./project
docker run -p 8000:8000 preprod-service
```

The frontend will be available at `http://localhost:8000/` and the
backend API at `/upload`, `/history`, `/result/{id}` and
`/download/{id}`.

### Without Docker

If you prefer to run services separately during development:

1. **Backend**

   ```bash
   cd project/backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

2. **Frontend**

   ```bash
   cd project/frontend
   npm install
   npm run dev
   ```

   The frontend will run on `http://localhost:5173` and proxy API
   requests to `http://localhost:8000` (see `vite.config.ts`).



