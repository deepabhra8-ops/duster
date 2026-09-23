# DUSTER - React Frontend

React (Vite + Axios) frontend for DUSTER. This is the
**foundational scaffold**: project structure, navigation shell, API layer,
constants, hooks, and utilities. Page bodies are stubs to be implemented next.

## Stack

- React 18 (JavaScript, no TypeScript)
- Vite 5
- Axios for all backend calls
- Navigation via `activePage` state (no React Router)

## Backend

Expects the existing Flask backend at **http://localhost:5050** (routes under
`/api`). The backend is **not modified**. Configure the URL in `.env`:

```
VITE_API_BASE_URL=http://localhost:5050/api
```

## Getting started

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # production build → dist/
npm run preview  # preview the production build
```

## Project structure

```
dq-engine-react/
├─ index.html                 # Vite HTML entry (#root)
├─ vite.config.js
├─ .env / .env.example        # VITE_API_BASE_URL
├─ public/
│  └─ img/favicon.png
└─ src/
   ├─ main.jsx                # mounts <App/>, imports global.css
   ├─ App.jsx                 # activePage state + health banner
   ├─ styles/
   │  └─ global.css           # original style.css, reused verbatim
   ├─ api/
   │  └─ api.js               # Axios instance + endpoint functions
   ├─ components/
   │  ├─ Sidebar.jsx          # nav driven by activePage
   │  ├─ PageShell.jsx        # <main>, renders active page (registry switch)
   │  └─ PagePlaceholder.jsx  # shared scaffold body for stubs
   ├─ hooks/
   │  └─ useLocalStorage.js   # state synced to localStorage
   ├─ utils/
   │  └─ helpers.js           # scoreClass, fmtBytes, debounce, …
   ├─ constants/
   │  ├─ appConfig.js         # pages, nav model, storage keys, defaults
   │  ├─ sourceTypes.js       # source type + database type options
   │  ├─ dbFields.js          # per-DB dynamic field configs + required fields
   │  └─ dqRules.js           # DQ1–DQ11 rules + score thresholds
   └─ pages/                  # stubs - implement these next
      ├─ ConfigurePage.jsx
      ├─ RunPage.jsx
      ├─ ResultsPage.jsx
      ├─ UploadsPage.jsx
      ├─ JobsPage.jsx
      └─ RulesPage.jsx
```

## Navigation model

`App` holds `activePage` (persisted via `useLocalStorage`). `Sidebar` renders
items from `NAV_SECTIONS` and calls `onNavigate(id)`. `PageShell` maps the
active id to a page component through `PAGE_REGISTRY`. To wire a real page,
replace the matching stub in `src/pages/`.

## API layer contract

Every `api.js` function returns `{ ok: true, data }` on success or
`{ ok: false, error }` on failure, matching the original vanilla app so page
logic ports cleanly.
