// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Config-backed source registry (9.3 + 9.9 fake-source defence).
//!
//! Sources are stored as a JSON list in the collection config under
//! `mcat.ai.sources`. This is the simplest store that (a) lets generated
//! content cite a real, registered source, and (b) lets the user inspect the
//! source trace. Generation MUST resolve a valid registered source before it
//! will produce anything.

use anki_proto::mcat as pb;
use serde::Deserialize;
use serde::Serialize;

use crate::prelude::*;

const CFG_SOURCES: &str = "mcat.ai.sources";

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub(crate) struct StoredSource {
    pub source_id: String,
    pub source_name: String,
    #[serde(default)]
    pub source_section: String,
    #[serde(default)]
    pub excerpt: String,
    #[serde(default)]
    pub registered_at: i64,
}

impl StoredSource {
    fn to_pb(&self) -> pb::AiSource {
        pb::AiSource {
            source_id: self.source_id.clone(),
            source_name: self.source_name.clone(),
            source_section: self.source_section.clone(),
            excerpt: self.excerpt.clone(),
            registered_at: self.registered_at,
        }
    }
}

impl Collection {
    pub(crate) fn mcat_stored_sources(&self) -> Vec<StoredSource> {
        self.get_config_optional::<Vec<StoredSource>, _>(CFG_SOURCES)
            .unwrap_or_default()
    }

    pub(crate) fn mcat_find_source(&self, source_id: &str) -> Option<StoredSource> {
        self.mcat_stored_sources()
            .into_iter()
            .find(|s| s.source_id == source_id)
    }

    pub(crate) fn mcat_list_sources(&self) -> pb::AiSourceList {
        pb::AiSourceList {
            sources: self
                .mcat_stored_sources()
                .iter()
                .map(|s| s.to_pb())
                .collect(),
        }
    }

    /// Register (or update by id/name) a source. A valid excerpt is required so
    /// generation can be grounded and the trace inspected.
    pub(crate) fn mcat_register_source(&mut self, req: pb::AiSource) -> Result<pb::AiSourceList> {
        let name = req.source_name.trim();
        if name.is_empty() {
            invalid_input!("source name is required");
        }
        if req.excerpt.trim().is_empty() {
            invalid_input!("a source excerpt is required to ground generation");
        }
        let mut sources = self.mcat_stored_sources();
        let id = if req.source_id.trim().is_empty() {
            format!("src-{}", TimestampSecs::now().0)
        } else {
            req.source_id.trim().to_string()
        };
        let entry = StoredSource {
            source_id: id.clone(),
            source_name: name.to_string(),
            source_section: req.source_section.trim().to_string(),
            excerpt: req.excerpt.trim().to_string(),
            registered_at: TimestampSecs::now().0,
        };
        if let Some(existing) = sources.iter_mut().find(|s| s.source_id == id) {
            *existing = entry;
        } else {
            sources.push(entry);
        }
        self.set_config(CFG_SOURCES, &sources)?;
        Ok(self.mcat_list_sources())
    }

    pub(crate) fn mcat_remove_source(&mut self, source_id: &str) -> Result<pb::AiSourceList> {
        let mut sources = self.mcat_stored_sources();
        sources.retain(|s| s.source_id != source_id);
        self.set_config(CFG_SOURCES, &sources)?;
        Ok(self.mcat_list_sources())
    }
}
