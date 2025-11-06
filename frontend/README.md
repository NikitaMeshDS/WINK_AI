# Frontend

This directory contains the React/TypeScript implementation of the
preproduction table service.  It is built with Vite and styled using
Tailwind CSS.  The application allows users to upload zipped film
scripts, displays the extracted scene table and lets them browse
historical uploads.

## Development

Install dependencies and start the development server:

```bash
npm install
npm run dev
```

During development API requests to `/upload`, `/history`, `/result` and
`/download` are proxied to `http://localhost:8000` (see
`vite.config.ts`).  If you change the backend port adjust the proxy
accordingly.

## Building

To create a production build, run:

```bash
npm run build
```

The output will be written to `dist/`.  When running inside Docker
this directory is served automatically by the FastAPI application.