// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Provider-agnostic AI foundation for the MCAT features (Phase 2).
//!
//! Everything here is designed so the app keeps working with AI OFF. The
//! [`AiClient`] trait abstracts an OpenAI-compatible Chat Completions endpoint;
//! [`OpenAiClient`] talks to a real provider (OpenAI, a local Ollama server,
//! etc.) and [`MockAiClient`] returns deterministic canned JSON so unit tests
//! and the eval harness run with no network and no key.
//!
//! Failures never propagate as hard errors into the core app: transport,
//! configuration and parsing problems become a typed [`AiError`], which the
//! feature code folds into an `ai_available = false` response so callers fall
//! back to deterministic behaviour (the recommender, offline review, etc.).

pub(crate) mod checker;
pub(crate) mod client;
pub(crate) mod explain;
pub(crate) mod generate;
pub(crate) mod mock;
pub(crate) mod perfgen;
pub(crate) mod planner;
pub(crate) mod prompt;
pub(crate) mod sources;

#[cfg(test)]
mod tests;

use std::fmt;

pub(crate) use client::OpenAiClient;
pub(crate) use mock::MockAiClient;
use serde::de::DeserializeOwned;

use crate::prelude::*;

/// Default OpenAI-compatible endpoint.
pub(crate) const DEFAULT_BASE_URL: &str = "https://api.openai.com/v1";
/// Default (cheap) model.
pub(crate) const DEFAULT_MODEL: &str = "gpt-4o-mini";
/// Default card-quality passing cutoff (0..1). **Set before testing.** A card
/// must reach this overall score (and clear the hard-fail categories) to leave
/// the Blocked state. Documented in steps.md and the eval report.
pub(crate) const DEFAULT_CHECKER_CUTOFF: f64 = 0.7;

/// Optional built-in AI proxy. When set, the app works with **no** user-entered
/// key: it points at an OpenAI-compatible proxy YOU host (see `mcat/proxy/`),
/// which injects the real OpenAI key server-side. The value carried by the app
/// is a LOW-PRIVILEGE, revocable proxy token — NOT your OpenAI key.
///
/// Provide it at BUILD time so no secret ever lands in the repo:
///
/// ```text
/// MCAT_AI_PROXY_URL=https://your-site/v1 \
/// MCAT_AI_PROXY_TOKEN=your-app-token just installer
/// ```
///
/// (or edit the fallback constants below). When unset/empty the app behaves as
/// before: OpenAI endpoint + a user-supplied key.
///
/// NOTE: the token below is the LOW-PRIVILEGE proxy app token (not an OpenAI
/// key). It is intentionally embedded in the client; rotate it any time by
/// updating `APP_TOKEN` on the proxy and changing the value here.
const PROXY_BASE_URL_FALLBACK: &str = "https://enchanting-llama-3dec8a.netlify.app/v1";
const PROXY_APP_TOKEN_FALLBACK: &str = "ce3b3ae9aeacae55e63edd1e1af470b4a07a9e81511a973f";

/// The built-in proxy `(base_url, app_token)` if one was configured at build
/// time (env) or via the fallback constants; `None` disables the proxy default.
fn builtin_proxy() -> Option<(String, String)> {
    let url = match option_env!("MCAT_AI_PROXY_URL") {
        Some(u) if !u.trim().is_empty() => u,
        _ => PROXY_BASE_URL_FALLBACK,
    };
    if url.trim().is_empty() {
        return None;
    }
    let token = match option_env!("MCAT_AI_PROXY_TOKEN") {
        Some(t) if !t.trim().is_empty() => t,
        _ => PROXY_APP_TOKEN_FALLBACK,
    };
    Some((url.trim().to_string(), token.trim().to_string()))
}

// Collection config keys (checked before environment variables).
const CFG_BASE_URL: &str = "mcat.ai.base_url";
const CFG_MODEL: &str = "mcat.ai.model";
const CFG_API_KEY: &str = "mcat.ai.api_key";
const CFG_CUTOFF: &str = "mcat.ai.checker_cutoff";
const CFG_ENABLED: &str = "mcat.ai.enabled";

/// Which feature is calling. Real clients ignore this; the mock uses it (with
/// [`ChatRequest::payload`]) to produce deterministic canned output.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum AiTask {
    GenerateCards,
    CheckCard,
    Explain,
    Plan,
    PerfQuestions,
}

/// A single Chat Completions call. `system`/`user` are what a real provider
/// sees; `payload` is structured data only the mock consumes.
#[derive(Clone)]
pub(crate) struct ChatRequest {
    pub task: AiTask,
    pub system: String,
    pub user: String,
    pub temperature: f32,
    pub payload: serde_json::Value,
}

impl ChatRequest {
    pub(crate) fn new(task: AiTask, system: impl Into<String>, user: impl Into<String>) -> Self {
        ChatRequest {
            task,
            system: system.into(),
            user: user.into(),
            temperature: 0.2,
            payload: serde_json::Value::Null,
        }
    }

    pub(crate) fn with_payload(mut self, payload: serde_json::Value) -> Self {
        self.payload = payload;
        self
    }
}

/// Typed AI failure. Kept separate from [`AnkiError`] because AI problems must
/// never break the core app — they are surfaced as an unavailable result.
#[derive(Debug, Clone)]
pub(crate) enum AiError {
    /// No key / no reachable endpoint / disabled.
    Unconfigured { reason: String },
    /// Network unreachable (offline).
    Offline { reason: String },
    /// Non-success HTTP status.
    Http { status: u16, reason: String },
    /// 429 / quota.
    RateLimited { reason: String },
    /// The model returned output that failed schema validation twice.
    Malformed { reason: String },
}

impl AiError {
    /// A short, user-facing reason for the AI-status pill / fallbacks.
    pub(crate) fn reason(&self) -> String {
        match self {
            AiError::Unconfigured { reason } => format!("AI not configured: {reason}"),
            AiError::Offline { reason } => format!("AI offline: {reason}"),
            AiError::Http { status, reason } => format!("AI error {status}: {reason}"),
            AiError::RateLimited { reason } => format!("AI rate limited: {reason}"),
            AiError::Malformed { reason } => format!("AI returned invalid output: {reason}"),
        }
    }
}

impl fmt::Display for AiError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.reason())
    }
}

pub(crate) type AiResult<T> = std::result::Result<T, AiError>;

/// An OpenAI-compatible chat client. Returns the assistant message content as a
/// string; JSON parsing/validation is done by [`complete_json`].
pub(crate) trait AiClient: Send + Sync {
    fn config(&self) -> &AiConfig;
    fn complete(&self, req: &ChatRequest) -> AiResult<String>;
}

// Lets a `Box<dyn AiClient>` (what `mcat_ai_client` returns) be passed where a
// `&dyn AiClient` is expected via ordinary reference coercion.
impl AiClient for Box<dyn AiClient> {
    fn config(&self) -> &AiConfig {
        (**self).config()
    }

    fn complete(&self, req: &ChatRequest) -> AiResult<String> {
        (**self).complete(req)
    }
}

/// Resolved AI configuration.
#[derive(Debug, Clone)]
pub(crate) struct AiConfig {
    pub base_url: String,
    pub model: String,
    pub api_key: Option<String>,
    pub checker_cutoff: f64,
    pub enabled: bool,
}

impl AiConfig {
    /// True when a call can be attempted: either a key is present, or the
    /// endpoint is local/keyless (e.g. an Ollama server).
    pub(crate) fn configured(&self) -> bool {
        self.api_key.as_deref().map(|k| !k.is_empty()) == Some(true)
            || is_local_endpoint(&self.base_url)
    }

    /// available = enabled && configured. The actual reachability is only known
    /// at call time (a failed call yields [`AiError`]).
    pub(crate) fn available(&self) -> bool {
        self.enabled && self.configured()
    }

    pub(crate) fn status_reason(&self) -> String {
        if !self.enabled {
            "AI is disabled in settings.".to_string()
        } else if !self.configured() {
            "No API key set (and endpoint is not local). Add a key in AI settings.".to_string()
        } else {
            format!("Ready — {} via {}", self.model, self.base_url)
        }
    }
}

/// A local, keyless endpoint (Ollama / LM Studio / localhost proxy).
pub(crate) fn is_local_endpoint(base_url: &str) -> bool {
    let u = base_url.to_ascii_lowercase();
    u.contains("localhost")
        || u.contains("127.0.0.1")
        || u.contains("0.0.0.0")
        || u.contains("[::1]")
}

fn env_nonempty(key: &str) -> Option<String> {
    std::env::var(key).ok().filter(|v| !v.trim().is_empty())
}

impl Collection {
    /// Resolve AI config: collection config keys first, then environment
    /// variables, then built-in defaults.
    pub(crate) fn mcat_ai_config(&self) -> AiConfig {
        let model = self
            .get_config_optional::<String, _>(CFG_MODEL)
            .filter(|v| !v.trim().is_empty())
            .or_else(|| env_nonempty("MCAT_AI_MODEL"))
            .unwrap_or_else(|| DEFAULT_MODEL.to_string());
        // base_url + api_key are resolved together so the built-in proxy can be
        // the zero-config default without clashing with an explicit user key.
        let base_url_set = self
            .get_config_optional::<String, _>(CFG_BASE_URL)
            .filter(|v| !v.trim().is_empty())
            .or_else(|| env_nonempty("MCAT_AI_BASE_URL"));
        let api_key_set = self
            .get_config_optional::<String, _>(CFG_API_KEY)
            .filter(|v| !v.trim().is_empty())
            .or_else(|| env_nonempty("MCAT_AI_API_KEY"))
            .or_else(|| env_nonempty("OPENAI_API_KEY"));
        let (base_url, api_key) = match (base_url_set, api_key_set) {
            // An explicit endpoint always wins (paired with whatever key exists).
            (Some(b), k) => (b, k),
            // An explicit key with no endpoint => talk to OpenAI directly.
            (None, Some(k)) => (DEFAULT_BASE_URL.to_string(), Some(k)),
            // Nothing configured => use the built-in proxy if present, else OpenAI.
            (None, None) => match builtin_proxy() {
                Some((url, token)) => (url, (!token.is_empty()).then_some(token)),
                None => (DEFAULT_BASE_URL.to_string(), None),
            },
        };
        let checker_cutoff = self
            .get_config_optional::<f64, _>(CFG_CUTOFF)
            .filter(|v| *v > 0.0 && *v <= 1.0)
            .unwrap_or(DEFAULT_CHECKER_CUTOFF);
        // Enabled defaults to true so a configured key "just works".
        let enabled = self
            .get_config_optional::<bool, _>(CFG_ENABLED)
            .unwrap_or(true);
        AiConfig {
            base_url,
            model,
            api_key,
            checker_cutoff,
            enabled,
        }
    }

    /// Build the AI client from resolved config.
    ///
    /// When the `MCAT_AI_MOCK` environment variable is set, a deterministic
    /// [`MockAiClient`] is returned instead of the network client (with config
    /// forced to "available"). This lets the eval harness and Python
    /// integration tests exercise the full RPC path offline with no key.
    pub(crate) fn mcat_ai_client(&self) -> Box<dyn AiClient> {
        let mut cfg = self.mcat_ai_config();
        let mock = self.mcat_ai_mock_enabled();
        if mock {
            cfg.enabled = true;
            if cfg.api_key.as_deref().unwrap_or("").is_empty() {
                cfg.api_key = Some("mock-key".to_string());
            }
            Box::new(MockAiClient::new(cfg))
        } else {
            Box::new(OpenAiClient::new(cfg))
        }
    }

    /// Persist AI configuration. An empty `api_key` on the request leaves the
    /// stored key untouched (so the masked round-trip from the UI is safe); a
    /// value of "-" clears it.
    pub(crate) fn mcat_set_ai_config(&mut self, req: anki_proto::mcat::AiConfig) -> Result<()> {
        let base_url = req.base_url.trim();
        if !base_url.is_empty() {
            self.set_config(CFG_BASE_URL, &base_url.to_string())?;
        }
        let model = req.model.trim();
        if !model.is_empty() {
            self.set_config(CFG_MODEL, &model.to_string())?;
        }
        let key = req.api_key.trim();
        if key == "-" {
            self.remove_config_inner(CFG_API_KEY)?;
        } else if !key.is_empty() && !key.starts_with("sk-...") {
            self.set_config(CFG_API_KEY, &key.to_string())?;
        }
        if req.checker_cutoff > 0.0 && req.checker_cutoff <= 1.0 {
            self.set_config(CFG_CUTOFF, &req.checker_cutoff)?;
        }
        self.set_config(CFG_ENABLED, &req.enabled)?;
        Ok(())
    }
}

impl Collection {
    /// Whether the deterministic offline mock provider is active (env var or
    /// collection config). Used by the client factory and status pill so the
    /// two stay consistent during offline tests / evals.
    pub(crate) fn mcat_ai_mock_enabled(&self) -> bool {
        std::env::var("MCAT_AI_MOCK").is_ok()
            || self.get_config_optional::<bool, _>("mcat.ai.mock") == Some(true)
    }

    /// Build the AI status pill payload from resolved config.
    pub(crate) fn mcat_ai_status(&self) -> anki_proto::mcat::AiStatus {
        let cfg = self.mcat_ai_config();
        if self.mcat_ai_mock_enabled() {
            return anki_proto::mcat::AiStatus {
                available: true,
                reason: "Offline mock AI provider active.".to_string(),
                provider: cfg.base_url.clone(),
                model: cfg.model.clone(),
                configured: true,
                enabled: true,
                checker_cutoff: cfg.checker_cutoff,
            };
        }
        anki_proto::mcat::AiStatus {
            available: cfg.available(),
            reason: cfg.status_reason(),
            provider: cfg.base_url.clone(),
            model: cfg.model.clone(),
            configured: cfg.configured(),
            enabled: cfg.enabled,
            checker_cutoff: cfg.checker_cutoff,
        }
    }

    /// Build the (masked) AI config for the settings UI.
    pub(crate) fn mcat_ai_config_pb(&self) -> anki_proto::mcat::AiConfig {
        let cfg = self.mcat_ai_config();
        let key_set = cfg.api_key.as_deref().map(|k| !k.is_empty()) == Some(true);
        anki_proto::mcat::AiConfig {
            base_url: cfg.base_url,
            model: cfg.model,
            api_key: cfg.api_key.as_deref().map(mask_key).unwrap_or_default(),
            checker_cutoff: cfg.checker_cutoff,
            enabled: cfg.enabled,
            api_key_set: key_set,
        }
    }
}

/// Mask an api key for display: keep a hint of the tail only.
pub(crate) fn mask_key(key: &str) -> String {
    let key = key.trim();
    if key.is_empty() {
        String::new()
    } else if key.len() <= 6 {
        "sk-...".to_string()
    } else {
        format!("sk-...{}", &key[key.len() - 4..])
    }
}

/// Extract a JSON object/array from a possibly fenced/prefixed model reply.
pub(crate) fn extract_json(raw: &str) -> &str {
    let trimmed = raw.trim();
    // Strip a leading ```json / ``` fence if present.
    let without_fence = trimmed
        .strip_prefix("```json")
        .or_else(|| trimmed.strip_prefix("```"))
        .map(|s| s.trim_start())
        .unwrap_or(trimmed);
    let body = without_fence
        .strip_suffix("```")
        .map(|s| s.trim_end())
        .unwrap_or(without_fence);
    // Find the first opening brace/bracket and the matching last closer.
    let start = body.find(['{', '[']);
    let end = body.rfind(['}', ']']);
    match (start, end) {
        (Some(s), Some(e)) if e >= s => &body[s..=e],
        _ => body,
    }
}

/// Call the model, parse + validate the JSON, and retry once on malformed
/// output before giving up with [`AiError::Malformed`].
pub(crate) fn complete_json<T: DeserializeOwned>(
    client: &dyn AiClient,
    req: &ChatRequest,
) -> AiResult<T> {
    let mut last_reason = String::new();
    for _ in 0..2 {
        let raw = client.complete(req)?;
        let json = extract_json(&raw);
        match serde_json::from_str::<T>(json) {
            Ok(value) => return Ok(value),
            Err(e) => last_reason = e.to_string(),
        }
    }
    Err(AiError::Malformed {
        reason: last_reason,
    })
}
