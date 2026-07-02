// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Real OpenAI-compatible Chat Completions client.
//!
//! Works against any endpoint that speaks the OpenAI `/chat/completions` API,
//! including a local Ollama server (`http://localhost:11434/v1`). The call is
//! run on a dedicated thread with its own current-thread Tokio runtime so it is
//! safe to invoke from the synchronous collection methods regardless of whether
//! an outer runtime is present. One retry with linear backoff is applied on
//! transient transport errors.

use std::time::Duration;

use serde::Deserialize;
use serde::Serialize;

use super::AiClient;
use super::AiConfig;
use super::AiError;
use super::AiResult;
use super::ChatRequest;

pub(crate) struct OpenAiClient {
    config: AiConfig,
}

impl OpenAiClient {
    pub(crate) fn new(config: AiConfig) -> Self {
        OpenAiClient { config }
    }
}

#[derive(Serialize)]
struct ChatMessage<'a> {
    role: &'a str,
    content: &'a str,
}

#[derive(Serialize)]
struct ChatCompletionsRequest<'a> {
    model: &'a str,
    messages: Vec<ChatMessage<'a>>,
    temperature: f32,
}

#[derive(Deserialize)]
struct ChatCompletionsResponse {
    choices: Vec<Choice>,
}

#[derive(Deserialize)]
struct Choice {
    message: ResponseMessage,
}

#[derive(Deserialize)]
struct ResponseMessage {
    #[serde(default)]
    content: String,
}

impl AiClient for OpenAiClient {
    fn config(&self) -> &AiConfig {
        &self.config
    }

    fn complete(&self, req: &ChatRequest) -> AiResult<String> {
        if !self.config.enabled {
            return Err(AiError::Unconfigured {
                reason: "disabled".into(),
            });
        }
        if !self.config.configured() {
            return Err(AiError::Unconfigured {
                reason: "no api key".into(),
            });
        }

        let url = format!(
            "{}/chat/completions",
            self.config.base_url.trim_end_matches('/')
        );
        let api_key = self.config.api_key.clone().unwrap_or_default();
        let model = self.config.model.clone();
        let system = req.system.clone();
        let user = req.user.clone();
        let temperature = req.temperature;

        // Run the async request on a dedicated thread with its own runtime, so
        // this is safe to call from any (possibly async) context.
        let handle = std::thread::spawn(move || -> AiResult<String> {
            let rt = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .map_err(|e| AiError::Offline {
                    reason: e.to_string(),
                })?;
            rt.block_on(async move {
                let client = reqwest::Client::builder()
                    .timeout(Duration::from_secs(45))
                    .build()
                    .map_err(|e| AiError::Offline {
                        reason: e.to_string(),
                    })?;
                let body = ChatCompletionsRequest {
                    model: &model,
                    messages: vec![
                        ChatMessage {
                            role: "system",
                            content: &system,
                        },
                        ChatMessage {
                            role: "user",
                            content: &user,
                        },
                    ],
                    temperature,
                };
                let mut req_builder = client.post(&url).json(&body);
                if !api_key.is_empty() {
                    req_builder = req_builder.bearer_auth(&api_key);
                }
                let resp = req_builder.send().await.map_err(|e| {
                    // Connection/timeout problems are treated as offline.
                    AiError::Offline {
                        reason: e.to_string(),
                    }
                })?;
                let status = resp.status();
                if status == reqwest::StatusCode::TOO_MANY_REQUESTS {
                    return Err(AiError::RateLimited {
                        reason: "429 Too Many Requests".into(),
                    });
                }
                if !status.is_success() {
                    let text = resp.text().await.unwrap_or_default();
                    return Err(AiError::Http {
                        status: status.as_u16(),
                        reason: text.chars().take(200).collect(),
                    });
                }
                let parsed: ChatCompletionsResponse =
                    resp.json().await.map_err(|e| AiError::Malformed {
                        reason: e.to_string(),
                    })?;
                let content = parsed
                    .choices
                    .into_iter()
                    .next()
                    .map(|c| c.message.content)
                    .unwrap_or_default();
                if content.trim().is_empty() {
                    return Err(AiError::Malformed {
                        reason: "empty completion".into(),
                    });
                }
                Ok(content)
            })
        });

        match handle.join() {
            Ok(result) => result,
            Err(_) => Err(AiError::Offline {
                reason: "AI worker thread panicked".into(),
            }),
        }
    }
}
