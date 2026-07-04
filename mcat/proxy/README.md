# MCAT AI proxy (zero-key distribution)

A tiny OpenAI-compatible **forwarding proxy** so the Anki MCAT app can use AI
features **without any user entering an API key**. The real OpenAI key lives
only on this server; the app carries a low-privilege, revocable **app token**.

```
Anki app ──(APP_TOKEN)──▶ this proxy ──(OPENAI_API_KEY, server-side)──▶ OpenAI
```

Why not embed the OpenAI key in the app? Because a desktop/mobile app ships to
users' machines — anything inside it (hardcoded, config, env, or in traffic)
can be extracted and abused, and OpenAI auto-revokes keys committed to public
repos. The proxy keeps the real key server-side; if the app token leaks you
just rotate `APP_TOKEN`.

## Deploy (Netlify)

```bash
cd mcat/proxy
npm i -g netlify-cli        # if needed
netlify deploy --prod       # creates/links a site and deploys
```

Then set two environment variables in **Site settings → Environment variables**:

| Variable          | Value                                                             |
| ----------------- | ----------------------------------------------------------------- |
| `OPENAI_API_KEY`  | your real OpenAI secret key (never leaves the server)             |
| `APP_TOKEN`       | any random string you choose; the app sends this, rotate any time |
| `OPENAI_BASE_URL` | _(optional)_ upstream, default `https://api.openai.com/v1`        |

Your endpoint is then `https://<your-site>.netlify.app/v1/chat/completions`.

Any host that runs serverless JS works (Cloudflare Workers, Vercel, Deno
Deploy); only the handler wiring differs — the logic in
`netlify/functions/chat.mjs` is portable.

## Point the app at it (no user input)

Build the app with the proxy baked in as the default — no secret touches the
repo, and users never see a key field:

```bash
MCAT_AI_PROXY_URL="https://<your-site>.netlify.app/v1" \
MCAT_AI_PROXY_TOKEN="<your APP_TOKEN>" \
just installer          # or: just run / just build
```

(Those are read at build time via `option_env!` in
`rslib/src/mcat/ai/mod.rs`; you can instead edit the `PROXY_*_FALLBACK`
constants there. A clean rebuild picks up changes.)

Resolution order is unchanged and still overridable: in-app **AI Settings** and
env vars (`MCAT_AI_BASE_URL` / `OPENAI_API_KEY`) still win over the built-in
proxy, so you can point a dev build straight at OpenAI when you want.

## Abuse protection (important)

A baked-in app token means anyone with the app can spend **your** OpenAI credits
through the proxy. Before wide distribution:

- Set a **hard monthly spend limit** on the OpenAI account (Billing → Limits).
- Consider Netlify rate limiting / a per-user auth check in the function.
- Rotate `APP_TOKEN` (and rebuild) if it is abused.

This is fine for personal use and small/beta groups as-is.
