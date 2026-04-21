# Policy-Guided Baselining: Why Pure Rules and Pure Learning Both Fall Short

## The Problem Behavioral Analytics Is Trying to Solve

Network behavior analytics rests on a simple idea: if we know what normal looks like for a user or host, we can detect when something abnormal happens. An employee who always SSHes to the build server and one day SSHes to an IP in a different country is worth a look. A host that contacts three or four internal services and then suddenly starts sending data to a cloud storage endpoint is worth a look. The anomaly is meaningful not because the destination is inherently suspicious, but because it is *unusual for this subject*.

The difficulty is in establishing "normal." Two approaches dominate the field, and both have significant weaknesses.

---

## The Cold-Start Problem with Pure Unsupervised Baselines

A pure unsupervised approach builds baselines exclusively from observed telemetry. Nothing is assumed in advance; the system watches and learns. After enough data accumulates, the baseline reflects reality.

On paper this is appealing. In practice it fails on day one.

Imagine a new employee — call her Alice — joins the engineering team. Her laptop is configured, her accounts are provisioned, and on her first day she does what every engineer does: she SSHes to the build server at `10.0.0.1`, hits the code review system at `10.0.0.2`, and pulls dependencies from the package registry at `10.0.0.5`. These are expected, legitimate, policy-sanctioned destinations.

But from the unsupervised baseline's perspective, Alice has no history. Everything she does is rare. Every destination she contacts fires as anomalous. The analyst desk is flooded with findings for Alice's first week — findings that carry no signal, because everything Alice is doing is exactly what she is supposed to be doing. The analyst learns to ignore them. Alert fatigue sets in. Real findings get buried.

This is the cold-start problem: a new subject's first days of activity generate a storm of false positives that train analysts to tune out the very finding types that matter.

The cold-start problem is worst for new subjects, but it recurs whenever an employee changes roles, gets a new machine, starts a new project, or returns from extended leave. Any gap in activity resets the "normal window," and the warmup period begins again.

---

## The Brittleness Problem with Pure Static Rules

The other approach is pure static rules: an administrator explicitly defines what each subject is allowed to do, and anything outside the rule set fires a finding. No baseline learning involved.

This approach has clarity. Rules are auditable, predictable, and easy to explain. But enterprise environments are not static, and rule sets do not maintain themselves.

Consider what happens in practice. The engineering team gets a new CI/CD vendor. Their traffic now flows to `203.0.113.88` in addition to the original build server. Someone needs to update every engineer's rule before the deployment, or every engineer fires a finding on day one of the new tool. Meanwhile, a contractor who joined six months ago is still using an IP address that was assigned to them temporarily and has since been rotated out of the allow-list — but no one has noticed because their rule was never cleaned up.

Rules also cannot capture what a subject actually does versus what they are allowed to do. If Alice's rule says she can contact twelve internal services but in two years of logs she has only ever contacted four of them, those eight allowed-but-unused destinations are noise in the allow-list. They dilute the signal. More importantly, if Alice *starts* contacting one of those eight destinations for the first time in year three, that is potentially interesting — but a pure rule-based system has no way to notice, because the destination is on the allow-list.

Rules tell you what is *permitted*. They cannot tell you what is *normal*.

---

## The Hybrid Approach: Seeding the Baseline with Policy

SenseGNAT uses a hybrid: policy seeds the baseline, and telemetry fills in the reality.

Here is the core idea. When `ProfileBuilder` constructs a behavioral profile for a subject, it does two things before processing any telemetry:

1. It asks the `PolicyEngine` for the subject's allowed destinations, allowed ports, and allowed protocols.
2. It pre-populates the profile's `common_destinations`, `common_ports`, and `common_protocols` frozensets with those policy-defined values.

Then it processes the event batch and adds observed destinations, ports, and protocols on top.

The result is that from the very first event, a subject's profile already contains everything their policy says they should be doing. The cold-start storm does not happen because policy knowledge is already loaded before the first event fires.

---

## A Concrete Example

Alice joins the engineering group. Her group's YAML policy looks like this:

```yaml
groups:
  engineering:
    allowed_destinations:
      - 10.0.0.1    # build server
      - 10.0.0.2    # code review
      - 10.0.0.5    # package registry
    allowed_ports:
      - 22
      - 443
      - 80

subjects:
  alice:
    peer_group: engineering
    allowed_destinations:
      - 203.0.113.10  # alice's personal dev VM, approved by security
```

When `ProfileBuilder` processes Alice's first day of events, it calls `policy_engine.allowed_destinations("alice")` before touching any events. This returns `{10.0.0.1, 10.0.0.2, 10.0.0.5, 203.0.113.10}` — the union of her group's destinations and her personal allow-list.

Alice's profile is pre-seeded with those four destinations. Now her first event arrives: she SSHes to `10.0.0.1`. The `RareDestinationDetector` checks: is `10.0.0.1` in Alice's `common_destinations`? Yes. No finding. Alice's normal first day generates zero false positives.

On Wednesday, Alice's laptop makes a request to `198.51.100.99` — an IP not in her policy and not in her observed history. Her profile does not contain it. `RareDestinationDetector` fires: "alice contacted a rare destination 198.51.100.99." This finding is signal. It is worth looking at.

---

## Policy Drift and the Reverse Direction

The hybrid approach also enables detecting the gap between what policy permits and what actually happens.

`PolicyViolationDetector` fires in the other direction: it catches events that contact destinations *outside* the policy allow-list. This is the complement of `RareDestinationDetector` for subjects who have active policies. A `rare-destination` finding says "this is new to this subject's history." A `policy-violation` finding says "this is outside what the subject is explicitly permitted to do" — a higher-severity signal.

Over time, the real baseline grows to reflect what subjects actually do, not just what they are permitted to do. If Alice's policy says she can contact twelve destinations but after a year she has only ever contacted four, the remaining eight are approved-but-unused. This is useful operational intelligence. It means the allow-list has grown stale, and those unused entries should probably be removed.

---

## Peer Groups and Collective Baselines

Subject-level baselines capture individual behavior. Peer groups capture collective behavior — what a cohort of similar subjects does.

The `PolicyEngine` assigns subjects to named peer groups. All members of the `engineering` peer group share the same group-level allow-list for seeding. But more importantly, `PeerDeviationDetector` compares each subject's current event against the union of all peer profiles.

If every engineer contacts `10.0.0.1` through `10.0.0.5`, and Alice's event goes to `10.99.99.99`, that destination has never appeared in *any* engineering peer's profile. `PeerDeviationDetector` fires: "alice deviated from peer group: destination 10.99.99.99 not seen by peer group." This is a different signal from rarity — it means Alice is doing something none of her colleagues do, even if she has done it before herself.

Peer deviation fires even when a destination is in Alice's own baseline, as long as it has not appeared in any other peer's profile. This catches behavior that has become normal for Alice individually but is still anomalous relative to her cohort — a useful signal for lateral movement or compromised account scenarios where a subject's individual baseline has been "trained" by an attacker over weeks of slow, careful activity.

---

## The Design in Summary

Three tensions shape the SenseGNAT baselining design:

1. **Day-one accuracy vs. unsupervised purity.** Pure telemetry-driven baselines need time to warm up. Policy seeding solves this without requiring manual rule maintenance forever.

2. **Rule auditing vs. rule brittleness.** Policies are auditable and communicate intent. But they need not be the sole arbiter of normalcy. Telemetry refines what policy declares.

3. **Individual behavior vs. cohort context.** A subject's individual baseline tells one story. Their deviation from peers tells another. Both are useful; neither alone is sufficient.

The policy-guided baseline is not a compromise between these tensions. It is a design that uses each approach where it is strongest: policy for seeding known-good state and catching explicit violations; telemetry for capturing reality and detecting drift from it; peer groups for contextualizing individual behavior within a cohort.
