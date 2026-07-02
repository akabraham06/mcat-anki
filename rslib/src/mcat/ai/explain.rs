// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! 9.5 AI explanations for missed questions.
//!
//! Grounded in the card's own content (the note fields) and its topic. Returns
//! why the correct answer is correct, why the chosen answer is wrong, a source
//! citation, the related topic and a suggested review action. **Never used as
//! scoring evidence.** When AI is offline/unavailable the reviewer still works;
//! the caller simply shows a friendly "AI unavailable" note.

use anki_proto::mcat as pb;
use serde::Deserialize;

use super::complete_json;
use super::prompt::fence_source;
use super::prompt::DATA_ONLY_INSTRUCTION;
use super::AiTask;
use super::ChatRequest;
use crate::prelude::*;

#[derive(Deserialize, Default)]
struct AiExplainResponse {
    #[serde(default)]
    why_correct: String,
    #[serde(default)]
    why_chosen_wrong: String,
    #[serde(default)]
    source_citation: String,
    #[serde(default)]
    related_topic: String,
    #[serde(default)]
    suggested_review_action: String,
}

impl Collection {
    pub(crate) fn mcat_explain_miss(
        &mut self,
        req: pb::ExplainMissRequest,
    ) -> Result<pb::MissExplanation> {
        let unavailable = |reason: String| pb::MissExplanation {
            ai_available: false,
            unavailable_reason: reason,
            card_id: req.card_id,
            ..Default::default()
        };

        let card = match self.storage.get_card(CardId(req.card_id))? {
            Some(c) => c,
            None => return Ok(unavailable("Card not found.".to_string())),
        };
        let note = match self.storage.get_note(card.note_id)? {
            Some(n) => n,
            None => return Ok(unavailable("Note not found.".to_string())),
        };

        let prefix = if req.tag_prefix.trim().is_empty() {
            "mcat".to_string()
        } else {
            req.tag_prefix.trim().to_string()
        };
        let child_prefix = format!("{prefix}::");
        let topic_tag = note
            .tags
            .iter()
            .find(|t| t.starts_with(&child_prefix))
            .cloned()
            .unwrap_or_default();

        let client = self.mcat_ai_client();
        if !client.config().available() {
            return Ok(unavailable(client.config().status_reason()));
        }

        // Ground strictly in the card's own fields (treated as data).
        let card_text = note.fields().join("\n");
        let fenced = fence_source("This flashcard", &topic_tag, &card_text);
        let system = format!(
            "You are an MCAT tutor helping a student who just missed a question. \
             {DATA_ONLY_INSTRUCTION} Respond with strict JSON \
             {{\"why_correct\":\"...\",\"why_chosen_wrong\":\"...\",\"source_citation\":\"...\",\"related_topic\":\"...\",\"suggested_review_action\":\"...\"}}. \
             Base every claim only on the provided card content; do not invent facts."
        );
        let chosen = if req.chosen_answer.trim().is_empty() {
            "(the student rated this Again / did not choose)".to_string()
        } else {
            req.chosen_answer.trim().to_string()
        };
        let user = format!("The student's chosen/incorrect answer: {chosen}\n\n{fenced}");
        let payload = serde_json::json!({
            "card_text": card_text,
            "chosen": req.chosen_answer,
            "topic": topic_tag,
        });
        let chat = ChatRequest::new(AiTask::Explain, system, user).with_payload(payload);

        match complete_json::<AiExplainResponse>(&client, &chat) {
            Ok(exp) => Ok(pb::MissExplanation {
                ai_available: true,
                unavailable_reason: String::new(),
                why_correct: exp.why_correct,
                why_chosen_wrong: exp.why_chosen_wrong,
                source_citation: if exp.source_citation.trim().is_empty() {
                    format!("This card ({topic_tag})")
                } else {
                    exp.source_citation
                },
                related_topic: if exp.related_topic.trim().is_empty() {
                    topic_tag.clone()
                } else {
                    exp.related_topic
                },
                suggested_review_action: exp.suggested_review_action,
                card_id: req.card_id,
            }),
            Err(e) => Ok(unavailable(e.reason())),
        }
    }
}
