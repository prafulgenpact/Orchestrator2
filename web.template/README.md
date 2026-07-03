# Frontend template (inactive until renamed)

To activate the web verification lane:

1. Scaffold your app here (Vite/Next/etc.), or merge this folder into it.
2. Keep these exact script names in package.json — `scripts/verify.sh` calls them:
   `lint`, `typecheck`, `test:unit`, `test:e2e`.
3. Rename `web.template/` → `web/` and run `npm --prefix web install`
   (this creates package-lock.json — commit it; CI uses `npm ci`).
4. Add the web checks to REQUIRED_CHECKS in `verify.config`:
   `REQUIRED_CHECKS="py-lint py-format py-types py-unit e2e web-lint web-types web-unit"`
5. For Playwright e2e, set `WEB_E2E=1` in `verify.config` and add a
   `playwright.config.ts` with a deterministic baseURL + `webServer` block.

Pinned devDependency versions are intentional (determinism). Bump them
deliberately in a dedicated PR, never ad hoc.
