# HeatShift

HeatShift is a responsive, installable, offline-first planning aid for workers, supervisors, volunteers, and small teams preparing for work in hot conditions. It converts basic conditions and work factors into a briefing card with a planning tier, check-in rhythm, reassessment schedule, checklist, and printable timeline.

It is **not** a medical device, heat-exposure limit, or substitute for local regulation, a qualified safety professional, or an employer heat program.

## User stories

- As a crew lead, I can turn conditions into a consistent pre-shift discussion.
- As a worker, I can see when buddy checks and plan reviews are expected.
- As a small organization, I can save, reopen, print, and export plans without an account.
- As a user with unreliable connectivity, I can use the app after its first successful load.

## Architecture

HeatShift is a dependency-free static PWA. `logic.js` contains pure heat-index and planning logic; `app.js` owns DOM interactions and device-local persistence; `sw.js` caches the app shell. Plans are stored in browser `localStorage` and can be exported as JSON. There is no backend, analytics, location access, or third-party API.

## Run

Requirements: Node.js 20+ and Python 3 for the optional local static server.

```bash
npm install
npm run verify
python3 -m http.server 8080
```

Open `http://localhost:8080`. To test install/offline behavior, use a browser that supports service workers and PWA installation.

## Build and tests

```bash
npm run check   # JavaScript syntax checks
npm test        # Node unit tests for critical planning logic
npm run build   # Copies deployable files to dist/
npm run smoke   # Serves dist/ and checks the primary route and logic asset
```

No configuration or credentials are required. `.env.example` documents the optional smoke-test port.

## Validation, errors, and accessibility

Inputs have explicit bounds and helpful errors. Results are announced through a live region, forms and controls have labels, keyboard focus is visible, colors are not the sole tier indicator, and layouts adapt down to small screens. Saved-data parsing fails closed to an empty list.

## Privacy and security

- All plan data stays in this browser unless the user explicitly exports it.
- No account, cookies, remote database, analytics, or location access.
- Exported JSON may reveal shift names and times; users should store it appropriately.
- Text is rendered with DOM `textContent`; user input is not injected as HTML.
- The service worker only caches same-app static files.

## Evidence and rationale

WHO says heat stress is a leading cause of weather-related deaths and that heat risks are increasing. ILO research published 13 August 2026 highlights occupational risks and prevention measures including water, rest, adapted schedules, training, and acclimatization.

- [WHO — Heat and health](https://www.who.int/news-room/fact-sheets/detail/climate-change-heat-and-health)
- [ILO — Climate-Related Heat Stress and Occupational Mortality in Colombia](https://www.ilo.org/publications/climate-related-heat-stress-and-occupational-mortality-colombia)

An offline PWA fits because workers may have weak connectivity, shared devices, low budgets, and no appetite for another account.

## Limitations

- The estimated heat index uses air temperature and humidity; it does not measure radiant heat, wind, or metabolic rate like WBGT assessment can.
- Planning tiers are deliberately conservative prompts, not exposure thresholds.
- The app does not fetch weather; conditions must be measured or entered by the user.
- Device-local data does not sync between browsers or users.

## Responsible production path

Validate the planning model with occupational-hygiene experts in each intended jurisdiction; localize emergency language and units; add a user-controlled WBGT input without pretending to measure it; conduct field usability and accessibility testing; define a reviewed content-update process; and deploy the static build behind HTTPS with a strict Content Security Policy.
