// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// OpenAI-compatible forwarding proxy for the Anki MCAT app.
//
// The app is built to call `POST {base_url}/chat/completions` with a bearer
// token. Point the app's base_url at this site's `/v1` and give it the APP
// TOKEN (a low-privilege, revocable token you choose) — NOT your OpenAI key.
// This function verifies that app token, then forwards the request to OpenAI
// using the REAL key, which lives ONLY in this server's environment.
//
// Required environment variables (set in Netlify → Site settings → Environment):
//   OPENAI_API_KEY   your real OpenAI secret key (never leaves the server)
//   APP_TOKEN        the shared token the app sends (rotate any time)
// Optional:
//   OPENAI_BASE_URL  upstream base (default https://api.openai.com/v1)
//
// This function is served at the default endpoint /.netlify/functions/chat.
// A redirect in netlify.toml maps the public /v1/chat/completions path to it,
// so the app's base_url is  https://<your-site>.netlify.app/v1

export default async (req) => {
    if (req.method !== "POST") {
        return json({ error: { message: "Method not allowed" } }, 405);
    }

    const appToken = process.env.APP_TOKEN;
    if (!appToken) {
        // Distinct from a token mismatch: this means the env var isn't loaded,
        // usually because the site wasn't redeployed after adding it.
        return json(
            { error: { message: "Proxy misconfigured: APP_TOKEN not set (redeploy the site after adding env vars)" } },
            500,
        );
    }
    const auth = req.headers.get("authorization") || "";
    if (auth !== `Bearer ${appToken}`) {
        // Same shape as OpenAI's error so the app surfaces a clean message.
        return json({ error: { message: "Unauthorized: invalid app token" } }, 401);
    }

    const openaiKey = process.env.OPENAI_API_KEY;
    if (!openaiKey) {
        return json({ error: { message: "Proxy misconfigured: OPENAI_API_KEY not set" } }, 500);
    }

    const upstream = (process.env.OPENAI_BASE_URL || "https://api.openai.com/v1").replace(/\/+$/, "");

    let resp;
    try {
        resp = await fetch(`${upstream}/chat/completions`, {
            method: "POST",
            headers: {
                "content-type": "application/json",
                authorization: `Bearer ${openaiKey}`,
            },
            body: await req.text(),
        });
    } catch (e) {
        return json({ error: { message: `Upstream request failed: ${e}` } }, 502);
    }

    // Stream the upstream response straight back (status + body preserved).
    return new Response(resp.body, {
        status: resp.status,
        headers: { "content-type": resp.headers.get("content-type") || "application/json" },
    });
};

function json(obj, status) {
    return new Response(JSON.stringify(obj), {
        status,
        headers: { "content-type": "application/json" },
    });
}
