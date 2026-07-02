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

    // --- Phase 2: AI features ---

    fn get_ai_status(
        &mut self,
        _input: anki_proto::mcat::AiStatusRequest,
    ) -> error::Result<anki_proto::mcat::AiStatus> {
        Ok(self.mcat_ai_status())
    }

    fn get_ai_config(
        &mut self,
        _input: anki_proto::mcat::AiStatusRequest,
    ) -> error::Result<anki_proto::mcat::AiConfig> {
        Ok(self.mcat_ai_config_pb())
    }

    fn set_ai_config(
        &mut self,
        input: anki_proto::mcat::AiConfig,
    ) -> error::Result<anki_proto::mcat::AiStatus> {
        self.mcat_set_ai_config(input)?;
        Ok(self.mcat_ai_status())
    }

    fn register_ai_source(
        &mut self,
        input: anki_proto::mcat::AiSource,
    ) -> error::Result<anki_proto::mcat::AiSourceList> {
        self.mcat_register_source(input)
    }

    fn list_ai_sources(
        &mut self,
        _input: anki_proto::mcat::AiStatusRequest,
    ) -> error::Result<anki_proto::mcat::AiSourceList> {
        Ok(self.mcat_list_sources())
    }

    fn remove_ai_source(
        &mut self,
        input: anki_proto::mcat::AiSourceId,
    ) -> error::Result<anki_proto::mcat::AiSourceList> {
        self.mcat_remove_source(&input.source_id)
    }

    fn generate_cards(
        &mut self,
        input: anki_proto::mcat::GenerateCardsRequest,
    ) -> error::Result<anki_proto::mcat::GeneratedCardList> {
        self.mcat_generate_cards(input)
    }

    fn check_card(
        &mut self,
        input: anki_proto::mcat::CheckCardRequest,
    ) -> error::Result<anki_proto::mcat::CardQualityReport> {
        self.mcat_check_card(input)
    }

    fn accept_generated_cards(
        &mut self,
        input: anki_proto::mcat::AcceptCardsRequest,
    ) -> error::Result<anki_proto::mcat::AcceptCardsResponse> {
        self.mcat_accept_cards(input)
    }

    fn explain_miss(
        &mut self,
        input: anki_proto::mcat::ExplainMissRequest,
    ) -> error::Result<anki_proto::mcat::MissExplanation> {
        self.mcat_explain_miss(input)
    }

    fn get_ai_study_plan(
        &mut self,
        input: anki_proto::mcat::ExamReadinessRequest,
    ) -> error::Result<anki_proto::mcat::AiStudyPlan> {
        self.mcat_ai_study_plan(input)
    }

    fn generate_perf_questions(
        &mut self,
        input: anki_proto::mcat::GeneratePerfQuestionsRequest,
    ) -> error::Result<anki_proto::mcat::GeneratedPerfQuestionList> {
        self.mcat_generate_perf_questions(input)
    }

    fn accept_perf_questions(
        &mut self,
        input: anki_proto::mcat::AcceptPerfQuestionsRequest,
    ) -> error::Result<anki_proto::mcat::AcceptCardsResponse> {
        self.mcat_accept_perf_questions(input)
    }
}
