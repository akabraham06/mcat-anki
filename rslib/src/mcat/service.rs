// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

use crate::collection::Collection;
use crate::error;

impl crate::services::McatService for Collection {
    fn get_topic_mastery(
        &mut self,
        input: anki_proto::mcat::TopicMasteryRequest,
    ) -> error::Result<anki_proto::mcat::TopicMasteryList> {
        self.topic_mastery(input)
    }

    fn get_exam_readiness(
        &mut self,
        input: anki_proto::mcat::ExamReadinessRequest,
    ) -> error::Result<anki_proto::mcat::ExamReadiness> {
        self.mcat_exam_readiness(input)
    }

    fn get_study_recommendation(
        &mut self,
        input: anki_proto::mcat::ExamReadinessRequest,
    ) -> error::Result<anki_proto::mcat::StudyRecommendation> {
        let snap = self.mcat_snapshot(&input.tag_prefix)?;
        Ok(self.recommendation_from_snapshot(&snap))
    }

    fn build_interleaved_session(
        &mut self,
        input: anki_proto::mcat::InterleavedSessionRequest,
    ) -> error::Result<anki_proto::mcat::InterleavedSession> {
        self.mcat_interleaved_session(input)
    }

    fn get_topic_targets(
        &mut self,
        input: anki_proto::mcat::ExamReadinessRequest,
    ) -> error::Result<anki_proto::mcat::TopicTargetList> {
        self.mcat_topic_targets(input)
    }
}
