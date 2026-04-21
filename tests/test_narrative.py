from __future__ import annotations

from datetime import datetime, timezone

from sensegnat.models.findings import Finding
from sensegnat.narrative.builder import NarrativeBuilder


def _finding(
    finding_type: str = "rare-destination",
    severity: str = "medium",
    score: float = 0.65,
    subject_id: str = "alice",
) -> Finding:
    return Finding(
        finding_id="find-001",
        finding_type=finding_type,
        seen_at=datetime.now(timezone.utc),
        subject_id=subject_id,
        severity=severity,
        score=score,
        summary="test finding",
        evidence={},
    )


class TestNarrativeBuilder:
    def setup_method(self) -> None:
        self.builder = NarrativeBuilder()

    def test_returns_none_for_empty_findings(self) -> None:
        assert self.builder.build("alice", []) is None

    def test_finding_count(self) -> None:
        findings = [_finding(), _finding(), _finding()]
        narrative = self.builder.build("alice", findings)
        assert narrative is not None
        assert narrative.finding_count == 3

    def test_finding_types_ordered_by_frequency(self) -> None:
        findings = [
            _finding("rare-destination"),
            _finding("rare-destination"),
            _finding("peer-deviation"),
        ]
        narrative = self.builder.build("alice", findings)
        assert narrative is not None
        assert narrative.finding_types[0] == "rare-destination"
        assert narrative.finding_types[1] == "peer-deviation"

    def test_severity_rollup_picks_highest(self) -> None:
        findings = [
            _finding(severity="low"),
            _finding(severity="high"),
            _finding(severity="medium"),
        ]
        narrative = self.builder.build("alice", findings)
        assert narrative is not None
        assert narrative.severity == "high"

    def test_severity_rollup_critical_beats_high(self) -> None:
        findings = [_finding(severity="high"), _finding(severity="critical")]
        narrative = self.builder.build("alice", findings)
        assert narrative is not None
        assert narrative.severity == "critical"

    def test_score_is_maximum(self) -> None:
        findings = [_finding(score=0.50), _finding(score=0.90), _finding(score=0.70)]
        narrative = self.builder.build("alice", findings)
        assert narrative is not None
        assert narrative.score == 0.90

    def test_summary_names_subject(self) -> None:
        narrative = self.builder.build("alice", [_finding()])
        assert narrative is not None
        assert "alice" in narrative.summary

    def test_summary_includes_severity_and_score(self) -> None:
        narrative = self.builder.build("alice", [_finding(severity="high", score=0.85)])
        assert narrative is not None
        assert "high" in narrative.summary
        assert "0.85" in narrative.summary

    def test_single_finding_produces_narrative(self) -> None:
        narrative = self.builder.build("bob", [_finding(subject_id="bob")])
        assert narrative is not None
        assert narrative.subject_id == "bob"
        assert narrative.finding_count == 1

    def test_repeated_type_shows_count_in_summary(self) -> None:
        findings = [_finding("rare-destination")] * 3
        narrative = self.builder.build("alice", findings)
        assert narrative is not None
        assert "×3" in narrative.summary
