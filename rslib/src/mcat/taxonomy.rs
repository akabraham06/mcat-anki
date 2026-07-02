// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! The MCAT exam outline (sections, topics, weights, timing targets).
//!
//! Embedded at compile time so the scoring/coverage logic is fully
//! self-contained and runs identically on desktop and mobile. This is the
//! authoritative "coverage map" against which the deck is measured.

use serde::Deserialize;

pub(crate) const TAXONOMY_JSON: &str = include_str!("taxonomy.json");

#[derive(Debug, Clone, Deserialize)]
pub(crate) struct Taxonomy {
    pub exam: String,
    pub score_scale: ScoreScale,
    pub tag_prefix: String,
    pub sections: Vec<Section>,
}

#[derive(Debug, Clone, Copy, Deserialize)]
pub(crate) struct ScoreScale {
    pub section_min: f64,
    pub section_max: f64,
    pub total_min: f64,
    pub total_max: f64,
}

#[derive(Debug, Clone, Deserialize)]
pub(crate) struct Section {
    pub key: String,
    pub name: String,
    pub topics: Vec<Topic>,
}

#[derive(Debug, Clone, Deserialize)]
pub(crate) struct Topic {
    pub key: String,
    pub name: String,
    pub weight: u32,
    pub target_seconds: f64,
    #[serde(default)]
    pub fact_based: bool,
}

impl Taxonomy {
    pub(crate) fn load() -> Taxonomy {
        serde_json::from_str(TAXONOMY_JSON).expect("embedded MCAT taxonomy is valid JSON")
    }
}
