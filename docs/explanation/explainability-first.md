# Explainability First: Why SenseGNAT Chooses Transparency Over Power

## What "Explainable Detection" Means

When SenseGNAT fires a finding, two things are always true:

1. A human can read a sentence that describes exactly what happened.
2. The specific data that caused the detection is recorded as key-value evidence.

This is what explainability means in SenseGNAT's context. It is not a dashboard feature or a post-hoc reporting concern. It is a first-class requirement baked into the `Finding` data model:

```python
@dataclass(frozen=True)
class Finding:
    finding_id:   str
    finding_type: str
    seen_at:      datetime
    subject_id:   str
    severity:     str
    score:        float
    summary:      str           # ← human-readable sentence
    evidence:     dict[str, str] # ← the data that caused the finding
```

`summary` is always a complete sentence an analyst can read and act on: "alice contacted a rare destination 198.51.100.99." `evidence` is always a dict of string key-value pairs that provide the supporting details: `{"destination": "198.51.100.99", "port": "443", "protocol": "tcp"}`. Every detector is required to populate both. There is no such thing as a valid `Finding` in SenseGNAT with an empty summary or empty evidence.

ADR-003 established this as the foundational design constraint for Phase A and Phase B detections: explainable logic before opaque ML.

---

## Why This Matters for Security Operations

Security operations centers deal with alert fatigue. When a detection system produces hundreds of alerts per day, analysts develop filtering habits — they learn which alert types tend to be noise, and they start skimming. Real detections get missed because they look like the noise.

Alert fatigue has a specific cause that is often overlooked: unexplainable alerts. When an alert arrives that says a score of 0.83 was exceeded for user `alice`, the analyst's first question is "why?" If the system cannot answer that question immediately, the analyst has to investigate the investigation — pulling logs, correlating events, reconstructing context — before they can even determine whether the alert is worth pursuing. That overhead, multiplied across hundreds of alerts per day, is unsustainable. Analysts learn to dismiss the unexplainable alerts entirely.

A finding that reads "alice contacted a rare destination 198.51.100.99, port 443, TCP" requires no reconstruction. The analyst can immediately decide whether `198.51.100.99` looks suspicious, check whether Alice had a business reason to contact it, or escalate it. The decision workflow starts from the finding itself, not from a lookup process triggered by the finding.

The difference is not subtle. An explainable finding is actionable in seconds. An unexplainable score requires minutes of context reconstruction before actionability even begins.

---

## The Contrast with Opaque ML

Machine learning models can detect patterns that no human-authored rule would catch. A neural network trained on years of network telemetry might notice that a certain sequence of connection timing, byte counts, and destination transitions correlates with credential theft — a pattern too subtle for any explicit rule. That is genuinely valuable.

But the output of that model is a number. The model cannot tell an analyst why it fired. It cannot tell a CISO which behavioral pattern triggered the alert. It cannot be tuned by adjusting a threshold or changing a rule — it can only be retrained, which requires labeled data, compute time, and an ML pipeline. In regulated industries, an opaque model that flags employees requires extensive validation before it can be used in any formal process. "The model said so" is not a defensible basis for an investigation.

There is also a calibration problem. A model that produces scores without explanation makes it very hard to distinguish between "high score because this is genuinely unusual" and "high score because the model overfit on a feature that happens to be noisy." When a detector's logic is explicit — "destination not in profile frozenset" — any false positive has an obvious cause that can be addressed directly. Add the destination to the allow-list. Broaden the profiling window. Lower the peer deviation threshold. The tuning knobs are legible.

SenseGNAT's position, captured in ADR-003, is that the first production value of a behavioral analytics system should be operational trust, not model novelty. Analysts need to be able to trust the findings they act on. Trust requires explainability. Explainability requires that the detection logic be transparent and that every finding carry the evidence for its own existence.

---

## How SenseGNAT Implements Explainability

Each of the four detectors is a direct comparison between an observed event and a known baseline:

**`RareDestinationDetector`** asks one question: is `event.destination` in `profile.common_destinations`? If not, the destination is rare for this subject. The evidence is exactly the three fields that characterize the event: destination IP, port, and protocol. The summary names the subject and the destination. Nothing is hidden.

**`PeerDeviationDetector`** computes the union of all peer profiles in the current batch and asks whether the event's destination and port appear in that union. If neither appears, it fires. Evidence includes the peer group name, peer count, and the specific destination or port that deviated. The summary states the deviation explicitly: "alice deviated from peer group: destination 10.99.99.99 not seen by peer group."

**`PolicyViolationDetector`** checks the event against the subject's policy allow-list. Evidence includes the specific destination or port that violated the policy. The severity is `high` (higher than `RareDestinationDetector`'s `medium`) because a policy violation is qualitatively different from a rarity — it is explicitly disallowed behavior, not merely unusual behavior.

**`TimeWindowDriftDetector`** counts how many destinations in the current event batch are novel relative to the established profile, and fires if that count exceeds a configured expansion threshold. Evidence includes the novel destination count, established destination count, expansion ratio, and threshold. The summary is a precise, human-readable sentence: "alice contacted 4 novel destination(s) this window (57% expansion over 7-destination profile)."

Every finding produced by these detectors can be fully reconstructed from its own fields. An analyst reviewing a finding a week after it fired can read the evidence dict and understand exactly what the detector saw, without needing access to the original logs.

---

## The NarrativeBuilder and Per-Subject Summaries

`NarrativeBuilder` takes explainability one level higher. After all detectors have run for a batch, it groups findings by subject and produces a `Narrative` — a per-subject summary that rolls up all findings into a single object.

The narrative summary uses a standardized format:

```
alice: 4 finding(s) — rare-destination ×3, peer-deviation. Severity: medium, peak score: 0.70.
```

This gives a GNAT analyst or automated workflow a single line that describes the entire behavioral picture for a subject in one run: how many findings, what types (ordered by frequency), what severity ceiling, and what peak score. An analyst triaging an alert queue can read this and immediately prioritize: a subject with four `rare-destination` findings at medium severity gets different attention than a subject with one `policy-violation` finding at high severity.

The `finding_types` field in the `Narrative` object (and in the STIX `note` record's `x_sensegnat_finding_types` property) also enables programmatic triage. A GNAT workflow rule can filter on `finding_type == "policy-violation"` and escalate those narratives to a different queue without reading the full evidence.

---

## The Tradeoff: What Explainability Cannot Catch

Choosing explainability over opaque ML is a genuine tradeoff. Explainable detectors have inherent limits.

A sophisticated attacker who understands behavioral baselines can evade them. If the attacker moves slowly — one new destination per week, staying below the `TimeWindowDriftDetector` threshold — and chooses destinations that are at least plausible for the subject's peer group, the explainable detectors will not fire. The behavior pattern is too subtle for any rule-based comparison to the known baseline.

An ML model trained on adversarial patterns might catch this. Sequence modeling, graph analytics, and time-series anomaly detection can surface signals that no human-authored rule captures. SenseGNAT does not claim otherwise.

What SenseGNAT does claim is that the common cases — the vast majority of genuine anomalies that security teams encounter — are detectable by explainable methods. Rare destination contacts, peer group deviations, policy violations, and burst destination expansion cover a large surface area of real-world anomalous behavior. And they do so with findings that analysts can trust, tune, and act on without a data science team standing by.

When an ML layer is added in a future phase, the design intent is that it complements rather than replaces the explainable detectors. ML findings can flag patterns too subtle for rules; explainable findings provide the supporting context and the audit trail. A system that outputs "the ML model fired (score: 0.94) and here are three supporting explainable findings" is both powerful and trustworthy. A system that outputs only the score is neither.

---

## Explainability as a Design Constraint

The practical implication of the explainability requirement is this: every new detector added to SenseGNAT must produce a `Finding` with a meaningful `summary` and a populated `evidence` dict. A detector that returns a score without an explanation is not acceptable, regardless of how accurate it is.

This constraint shapes what detectors SenseGNAT can implement. It rules out any detection method whose logic cannot be summarized in a sentence and whose triggering conditions cannot be expressed as key-value evidence. That is a real limitation. It is also a feature: it keeps the detection logic auditable, keeps the analyst trust high, and keeps the system tunable by people who are not ML practitioners.

The convention is enforced by the `Finding` model itself — `summary` and `evidence` are required fields with no defaults. A detector that does not populate them does not compile to a valid `Finding`.
