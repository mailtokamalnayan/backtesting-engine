# Static results site

An interactive, read-only snapshot of all saved backtests — clusters runs by
strategy, compares parameter variations, overlays equity curves, and shows full
metrics + in/out-of-sample splits + trades. Pure static files (HTML/CSS/JS); the
data lives in `data.json`, generated from your local results.

## Publish (Vercel)

Once `vercel` is installed and authenticated (`npm i -g vercel`), one command takes
the current saved runs live:

```bash
make publish        # export site/data.json -> deploy to prod -> re-point the alias
```

`publish.py` does all three steps. The third — `vercel alias set` — is the easily
forgotten one: a `*.vercel.app` alias can't be a project production domain, so the
clean alias (`backtest-in-nf.vercel.app`) does **not** auto-follow a prod deploy and
must be re-pointed every time. The project is `backtest-in-nf` under scope
`kamals-projects-ce7b0100`.

If `vercel` is missing/unauthenticated or the token expired, the deploy step prints
the CLI's own error and stops before aliasing — re-run `vercel login` and try again.

## Preview locally

`fetch()` needs HTTP (not `file://`), so serve the folder:
```bash
cd site && python -m http.server 8000   # open http://localhost:8000
```

## Notes
- Only results are exported — no API keys, no raw market data. `.env`,
  `.kite_cache/`, and `results/` never leave your machine.
- Equity curves are downsampled (daily) so the snapshot stays small.
