# Nächster Schritt – Bewerbungs-Workspace

Eigenständiger Nachbau der Replit-App "Nächster Schritt" (Bewerbungs-Tracker,
Jobsuche, Anschreiben-Generator, Interview-Training, Lebenslauf-Builder).

## Hintergrund

Der ursprüngliche Export aus Replit enthielt nur den Frontend-Teil eines
pnpm-Monorepos (`apps/web` o. ä.) und importierte ein Paket
`@workspace/api-client-react`, das die eigentliche Backend-Anbindung
(insbesondere die Jobsuche über Adzuna + Arbeitnow) enthielt. Dieses Paket
lag nicht im Export vor. Dieser Ordner ist deshalb kein 1:1-Kopie, sondern
ein eigenständiges Vite-Projekt:

- Alle UI-Komponenten, Seiten und Styles wurden unverändert übernommen.
- `package.json`/`vite.config.ts`/`tsconfig.json` wurden von Monorepo- auf
  Standalone-Konfiguration umgestellt (echte Versionsnummern statt
  `catalog:`/`workspace:*`, keine Replit-only Vite-Plugins).
- `src/hooks/use-search-jobs.ts` ersetzt `@workspace/api-client-react`:
  ruft Adzuna und Arbeitnow **direkt aus dem Browser** auf (kein eigenes
  Backend). Die BA-Jobbörse wird weiterhin wie im Original direkt aus
  `App.tsx` abgefragt.

## Setup

```bash
npm install
cp .env.example .env   # dann VITE_ADZUNA_APP_ID / VITE_ADZUNA_APP_KEY eintragen
npm run dev
```

- `npm run build` – Production-Build nach `dist/`
- `npm run typecheck` – TypeScript ohne Emit prüfen

## Adzuna-Zugangsdaten

Kostenloser Account unter https://developer.adzuna.com/. Ohne gesetzte
`VITE_ADZUNA_APP_ID`/`VITE_ADZUNA_APP_KEY` liefert die Jobsuche nur
BA-Jobbörse- und Arbeitnow-Ergebnisse (beide brauchen keinen Key).

**Wichtig:** Da es kein eigenes Backend gibt, landet der Adzuna-Key im
Browser-Bundle (alle `VITE_`-Variablen sind client-seitig sichtbar). Für
einen privaten Prototyp ist das meist unkritisch, für eine öffentlich
verlinkte App wäre ein schmaler Server-Proxy (der den Key serverseitig
hält) die sauberere Lösung – aktuell nicht Teil dieses Rebuilds.

## Was noch fehlt

- Es gibt aktuell keine Persistenz über den Browser-Local-Storage hinaus
  (kein echtes Backend/DB für Bewerbungen, Lebenslauf etc.) – das war im
  Originalexport ebenfalls nicht enthalten.
- KI-Features (z. B. Textvorschläge) sind, soweit im UI vorhanden, aktuell
  nicht an einen LLM-Provider angebunden.
