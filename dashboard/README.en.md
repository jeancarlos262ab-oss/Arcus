# Arcus — Dashboard

![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3-38BDF8?logo=tailwindcss&logoColor=white)
![Recharts](https://img.shields.io/badge/Charts-Recharts-22B5BF)

[Español](README.md) · **English**

Web interface for the [Arcus](../README.en.md) project. This README covers only the frontend
that lives in the `dashboard/` folder.

---

## Overview

The **Repo Health Dashboard** is a **read-only** Single Page Application (SPA) that
visualizes the results produced by the Arcus PR review pipeline. It shows each
repository's health over time: reviews executed, findings by severity and type, per-agent
reliability, recent activity, and the repository's context graph.

**Purpose within Arcus.** The backend (webhook → Step Functions → 5 agents) analyzes each
Pull Request and persists the result in DynamoDB. The dashboard **consumes** that data and
presents it in a readable way; it **never writes** to DynamoDB or S3. This boundary is
intentional: being read-only, the frontend can be developed independently and does not
block the rest of the system.

**Who it's for.** Maintainers and tech leads who want an aggregated view of their
repositories' code quality, and the Arcus team to demo and debug the pipeline's behavior.

> **Current status:** the dashboard runs today against a **mock data layer**
> (deterministic) that mirrors the real DynamoDB schema, so it is fully navigable without a
> deployed backend. Connecting to the real read-only API is a localized swap of the data
> source (see [Backend / API connection](#backend--api-connection)).

---

## Technologies and frameworks

| Area | Technology |
|---|---|
| UI library | **React 18** |
| Build tool / dev server | **Vite 5** |
| Language | **TypeScript 5** (strict mode) |
| Styling | **Tailwind CSS 3** (class-based dark mode, tokens via CSS variables) |
| Charts | **Recharts** |
| Interactive graph | **react-force-graph-2d** |
| Icons | **lucide-react** |
| Accessible components | **@radix-ui/react-switch** |
| Date utilities | **date-fns** |
| Linting | **ESLint** |

Notable technical points:
- **Per-page lazy loading** (`React.lazy` + `Suspense`): each screen and its heavy
  dependencies (Recharts, react-force-graph-2d) are downloaded only when the user navigates
  to them, keeping the initial bundle light.
- **Import alias** `@/` → `src/` (configured in `vite.config.ts` and `tsconfig.json`).
- **Light/dark theming** based on CSS variables resolved by Tailwind.

---

## Folder structure

```
dashboard/
├── index.html                 # HTML entry point
├── package.json               # Dependencies and scripts
├── vite.config.ts             # Vite config (React plugin, @ alias, port 5173)
├── tailwind.config.js         # Theme (colors via CSS vars, fonts, animations)
├── postcss.config.js          # PostCSS + Autoprefixer
├── tsconfig*.json             # TypeScript configuration
├── .env.example               # Display-only VITE_* variables
├── public/                    # Static assets (favicon, etc.)
└── src/
    ├── main.tsx               # React bootstrap (mounts <App/>)
    ├── App.tsx                # Root layout: Sidebar + per-page routing + providers
    ├── index.css              # Base styles and theme tokens
    ├── pages/                 # One view per screen
    │   ├── OverviewPage.tsx   #   KPIs and overall health
    │   ├── ActivityPage.tsx   #   Recent activity / simulated run
    │   ├── GraphPage.tsx      #   Repository context graph
    │   ├── FindingsPage.tsx   #   Filterable findings
    │   └── SettingsPage.tsx   #   Settings (read-only, backend-owned)
    ├── components/            # Reusable UI components
    │   ├── charts/            #   Recharts charts (severity, types, over time…)
    │   ├── ui/                #   Primitives and previews
    │   ├── Sidebar.tsx, Header.tsx, KpiCard.tsx, FindingCard.tsx, GraphView.tsx …
    ├── state/                 # Global state via React Context
    │   ├── StoreProvider.tsx  #   Data (runs, findings, settings) + local persistence
    │   └── ThemeProvider.tsx  #   Light/dark theme
    └── lib/                   # Logic and data (no JSX)
        ├── types.ts           #   Domain types (ReviewRun, Finding, Severity…)
        ├── mockData.ts        #   Deterministic generator with the real DynamoDB shape
        ├── mockGraph.ts       #   Sample graph for GraphPage
        ├── simulate.ts        #   Simulated "review" flow with logs
        ├── selectors.ts       #   Derivations/aggregations for the charts
        ├── runtimeConfig.ts   #   Region and model (display-only, with fallback)
        └── theme.ts           #   Theme helpers
```

Three-layer organization: **`pages/`** assembles screens, **`components/`** provides
reusable UI pieces, and **`lib/`** concentrates types, data, and pure logic that is easy to
test and to replace with the real API.

---

## Prerequisites

- **Node.js 18 or higher** (Vite 5 requires Node 18+; an LTS version is recommended).
- **npm** (the repository includes `package-lock.json`). You may also use `pnpm` or `yarn`
  if you prefer, adapting the commands.

Check your versions:

```bash
node -v
npm -v
```

---

## Local install and run guide

All commands run **inside the `dashboard/` folder**.

```bash
# 1. Enter the frontend folder
cd dashboard

# 2. Install dependencies
npm install

# 3. Start the development server (Vite, with HMR)
npm run dev
```

Vite will serve the app at **http://localhost:5173** (the port is fixed in
`vite.config.ts`; `host: true` also exposes it on the local network).

**Other available scripts:**

```bash
npm run build     # Type-check (tsc -b) + production build into dist/
npm run preview   # Serve the production build locally to verify it
npm run lint      # ESLint over .ts / .tsx files
```

**Environment variables (optional).** They are only used to display reference values; they
are not secret. Create a `.env.local` (or `.env`) from the example:

```bash
cp .env.example .env.local
```

```bash
VITE_ARCUS_AWS_REGION=us-east-1
VITE_ARCUS_BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0
```

Since these are Vite variables, they must carry the `VITE_` prefix to be available in the
client, and changing them requires restarting the dev server.

---

## Backend / API connection

The dashboard is designed to consume a **read-only HTTP API** backed by the DynamoDB table
`arcus-{env}-review-history`, where the pipeline persists each review (per-agent status,
findings summary by severity/type, link to the PR comment, timestamp, etc.).

**How it works today (mock mode):**
- The data source is `src/lib/mockData.ts`, which generates a **deterministic** dataset with
  the **same shape** the real API will return (the schema defined in the backend design).
  This makes the UI look and behave like production without depending on the live pipeline.
- Global state lives in `src/state/StoreProvider.tsx` and is **persisted to `localStorage`**
  across reloads. `src/lib/simulate.ts` lets you trigger a simulated "review" with live logs
  for the demo.

**How it will connect to the real API:**
- All data reads go through the *store*, so switching from mock data to the real API is a
  matter of replacing the data source with an HTTP client that queries the read-only
  endpoint, keeping the same types from `src/lib/types.ts`.
- The dashboard is **read-only**: it never writes to DynamoDB or S3.

**Backend-owned configuration.** Values such as the **AWS region**, the
**`BEDROCK_MODEL_ID`**, the **GitHub App ID**, and whether the **webhook is configured** are
owned by the deployed backend, not the browser. In `StoreProvider` these fields are
**forced** to the current runtime value (`src/lib/runtimeConfig.ts`) instead of being read
from a previous `localStorage` save. The `VITE_ARCUS_*` variables are only a display
*fallback* for the standalone dashboard; the source of truth remains the backend.

To deploy the backend that will feed this API, see the
[main project README](../README.en.md).
