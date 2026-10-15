# TraderScheme AI-Bots: evidence-scoped reverse-engineering assessment

Date: 2026-10-15. Target supplied by user: https://www.traderscheme.com/#AI-Bots. REA source: https://github.com/morluto/rea.git .

## Status: PUBLIC RESEARCH ONLY — TARGET NOT YET CAPTURED WITH REA

**Do not present this as a reverse engineering of TraderScheme proprietary bot algorithms.** The exact supplied .com page returned no page text from the available public web interface; its fragment `#AI-Bots` does not identify a server-side endpoint. No authorized browser session, HAR, screenshots, public JS bundle or browser trace of that exact target was captured. Thus no verified implementation details, bot thresholds, hidden weights, API schema, internal strategy logic, actual execution or real profitability are established for the target.

The GitHub REA repo was inspected directly. Its README states that website investigation can return page structure, scripts, network observations and screenshots, requires a Chrome-family browser, and Node.js 22.x >=22.19, 24.x >=24.11 or 26+. REA uses local MCP/CLI and its documented setup command is `npx rea-agents setup`. REA is licensed MIT. It is a *tool* to perform investigation; merely reading its source does not execute a site investigation.

The current runtime has Chromium and Node.js v22.16.0, which does not satisfy REA's stated Node version requirement. Network requests to the exact target from this runtime failed DNS resolution. **REA was not installed, launched or used to capture the target.** Do not claim otherwise.

## Public observations from other sites — separate, non-authoritative comparators

- `https://www.traderscheme.co/marketplace` has a search-indexed public listing of 17 purported AI-enabled Deriv strategy bots with categories like Digits, Trend, Recovery, Copy and AI. The page describes configurations such as rolling last-digit distribution, moving-average + ATR trend filter and stepwise staking. The page **explicitly labels displayed win rates and download counts simulated demo figures, M-PESA sandbox payments and placeholder files**. Never use its marketing metrics as genuine observed performance.
- `https://www.traderscheme.fit/` has search-indexed UI labels Dashboard, Bot Builder, Free Bots, Auto Trades, DTrader, TradingView, Copy Trading, Calculator, Analysis Tool, AI Bots and Digits Analysis, with Summary / Transactions / Journal views.
- `https://traderschemepro.com/` is another distinct domain advertising strategies and statistical win rates. No affiliation with the user's exact .com site has been established. Do not transplant claims or algorithms from it.
- These domains might be unrelated or independently run. No equivalence has been verified.

## Safe REA investigation procedure, once target access is established

1. Work only on unauthenticated, publicly accessible pages or an account you are authorized to inspect. Do not access third-party accounts, bypass authentication, decrypt protected traffic, attack rate limits or extract proprietary credentials.
2. Upgrade local Node.js to a REA-supported version; use the upstream `morluto/rea` repository and official `rea-agents` package. Verify package and version before setup; use an isolated dev workstation.
3. Use REA browser-observation workflow from its official `docs/browser-observation.md`. Capture exact requested URL, load behaviour, DOM hierarchy, screenshots, scripts, source maps only if publicly served, and normal browser network requests. Record UTC observation time and immutable hashes for saved files.
4. Focus on the AI-Bots navigation and visible UI: catalogue, contract/market selectors, indicators, strategy configuration, displayed risk warnings, session monitoring, explainability and export. Explicitly mark logged-in or paid features **NOT OBSERVED** unless access is lawful and authorized.
5. Build a feature matrix with columns `feature`, `observed_on_exact_target`, `public_evidence_url_or_hash`, `verified_vs_inferred`, `proposed_original_implementation`, `testing_requirements`.
6. No copying logos, brand assets, restricted source, paid bot payloads, secret tokens or proprietary texts. Build original research modules for any feature we choose.
7. No browser/runtime injection into trading flows or purchase APIs. In `bot_builder`, keep `LIVE_EXECUTION_DISABLED=True`, `NO_TRADE`, `SHADOW_RESEARCH_ONLY`.

## Original research-only features that can be evaluated

- A catalogue of **candidate research strategies** (not claims of functioning profitable bots): momentum baseline, trend filter, last-digit distribution baseline, Even/Odd baseline, and fixed-stake vs recovery *risk simulations*.
- Every strategy card must show its contract family, eligible data provenance, model hash, quote-matched predicted EV, effective independent sample size and whether prospective confirmation is authorized.
- A journaled session dashboard for observed tick/proposal coverage, strict-cohort eligibility, pending vs resolved predictions and replay mismatches.
- An evidence scorecard that refuses to display illustrative website 'win rates' as actual backtest/live return.
- Only implement strategies that can be expressed using authorized public Deriv API data and verified against future independent SHADOW observations. No purchase execution.

## Scientific interpretation

Deriv product win rate alone cannot determine positive expected value: contract ask, payout, costs, timing, true occurrence probability and regime dependence all matter. Recovery/martingale position sizing does not create underlying positive EV and can increase tail risk. The historical four-session pilot in this repo found negative mean model-predicted quote EV in every tested group. The later separated calibration was incomplete (one accepted session of eight). Consequently **NO_VALIDATED_POSITIVE_EV_EDGE** still applies.

## Blockers

- Exact .com website content / JS / capture is not available via the current web interface.
- No installed/launchable REA runtime was used.
- No evidence that the similarly named domains share ownership or backend implementation.
- Need an authorized Chrome capture of the exact target (screenshots and sanitized HAR or publicly served scripts) to move from feature hypotheses to evidence-based reconstruction.

Reference: https://github.com/morluto/rea/blob/main/README.md and https://github.com/morluto/rea/blob/main/docs/browser-observation.md .
