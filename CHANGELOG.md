# Changelog

All notable changes to the Virtual–Real Transition Axis
(VRTA) project are documented in this file.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Version numbers follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html)
where applicable.

---

## [Unreleased]

---

## [0.5.0] - 2026-11-17

### Added

- Added `checkpoint.py` for a single local checkpoint store. It reads versioned records, checks store identity and integrity, and confirms writes by reading them back.
- Added `TransitionAxisV5` with fail-closed restart recovery. Every startup begins in `zero_neutral`. Confirmed restrictions are restored, but domain credentials, five-element tokens, evidence receipts, and approvals are not.
- Added administrator-led reconciliation for interrupted operations and an explicit rebuild path for missing or corrupt checkpoints. An interrupted handover is abandoned. A pending restriction activation is retained, and a pending release does not remove the restriction.

### Changed

- Role handovers and restriction changes now confirm a `pending` checkpoint before applying changes. An unconfirmed final write does not return success, publish a replacement credential, or lift a live restriction.
- Recovery requires fresh simulated safety verification and human approval for the current startup and checkpoint revision. Reconciliation alone does not exit neutral mode. New credentials must be issued explicitly, and evidence must be verified again.
- Preserved the v0.1–v0.4 APIs for regression and comparison.

### Validation

- GitHub Actions validation passed with 143 tests per configured Python version (3.11, 3.12, and 3.13): 118 baseline tests, 14 checkpoint tests, and 11 restart-recovery tests.
- The restart suite exits a child process immediately after outgoing credential revocation. A fresh process reopens the same checkpoint and confirms that the pending handover is not resumed and that recovery remains blocked until reconciliation.
- Kept the existing simulation checks and v0.3 integration smoke test.

### Scope

- Validation covers single-process stop and restart with a single writer and local storage. It does not establish power-loss durability, distributed recovery, protection against deliberate checkpoint tampering or rollback, or authenticated human approval.

---

## [0.1.0] - 2026-11-09

### Initial Experimental Release

Virtual–Real Transition Axis v0.1.0 establishes
a minimal, deterministic reference implementation
of independent authority control for
Zero-Style AI Orchestration.

The release focuses on defining and testing
the boundaries between virtual observation,
real operations, and an independent control axis.

### Added

#### Core Architecture

- Introduced the Virtual–Real Transition Axis model.
- Defined the Virtual domain for simulated event reception.
- Defined the Real domain for restricted operations.
- Introduced an independent deterministic control axis.
- Established application-level hard policy rules.
- Separated role authority from axis state control.

#### Virtual Domain

- Added virtual event format validation.
- Added configurable event-count limits.
- Added backpressure when the limit is exceeded.
- Added degraded operating mode.
- Added virtual observation-window reset.

#### Real Domain

- Added role-restricted real operation validation.
- Added three permitted simulated operations:
  - `analyze`
  - `record`
  - `propose`
- Added rejection of unauthorized operations.
- Added rejection of operations marked as unverified.
- Added virtual-to-real role escalation prevention.

#### Authority Control

- Added role-based token registration.
- Added unique token identifier validation.
- Added authority generation tracking.
- Added stale-token rejection.
- Added authority invalidation during neutralization.
- Added rejection of role-level hard policy changes.

#### State Management

- Introduced three operating modes:
  - `normal`
  - `degraded`
  - `zero_neutral`
- Added emergency zero-neutralization.
- Added blocking of role operations in neutral mode.
- Added recovery condition evaluation.
- Required both simulated safety verification
  and human approval for recovery.
- Preserved invalidation of old authority
  generations after recovery.

#### Audit

- Added an in-memory hash-chained audit log.
- Added SHA-256 record hashing.
- Added deterministic JSON serialization.
- Added audit-chain consistency verification.
- Added modification detection for existing records.
- Added logging of important state transitions.

#### Simulation

- Added a deterministic local simulation.
- Demonstrated acceptance of three virtual events.
- Demonstrated backpressure on the fourth event.
- Demonstrated transition to degraded mode.
- Demonstrated permitted real-domain analysis.
- Demonstrated emergency neutralization.
- Demonstrated denied recovery without approval.
- Demonstrated recovery when both flags are true.
- Demonstrated audit-chain verification.

### Tests

Added 15 unit tests covering:

1. Initial state and hard policy.
2. Invalid virtual event limit.
3. Token issuance validation.
4. Virtual event acceptance.
5. Backpressure and degraded mode.
6. Invalid virtual event rejection.
7. Virtual-to-real privilege escalation rejection.
8. Unverified real operation rejection.
9. Permitted real operations.
10. Forbidden real operations.
11. Hard policy modification rejection.
12. Emergency neutralization.
13. Stale authority rejection after recovery.
14. Recovery condition enforcement.
15. Audit-chain integrity and modification detection.

### Validation

- GitHub Actions validation reported as passed.
- Configured validation environments:
  - Python 3.11
  - Python 3.12
  - Python 3.13
- 15 unit tests per Python environment.
- 45 total unit-test executions across the matrix.
- Python syntax validation included.
- Deterministic simulation execution included.
- Simulation output assertions included.
- No third-party Python dependencies required.

### Documentation

- Added `README.md`.
- Documented the core architecture.
- Documented the virtual and real role boundaries.
- Documented the independent axis and hard policy.
- Documented operating modes and state transitions.
- Documented simulation and unit-test commands.
- Documented known security limitations.
- Documented the development roadmap.

### Security Limitations

This release is an experimental behavioral model.

It does not provide:

- Cryptographically authenticated role tokens.
- Independent evidence verification.
- Authenticated human approval.
- Operating-system-level role isolation.
- Network or container isolation.
- Persistent tamper-resistant audit storage.
- Trusted timestamps or external audit anchoring.
- Production-grade denial-of-service protection.
- Verified resistance to real-world attacks.

The `verified` and `human_approved` parameters
are caller-supplied simulation flags.

The hard policy is enforced through designated
application APIs, not protected against arbitrary
code execution inside the Python process.

The in-memory hash chain provides consistency
checking, not independent tamper resistance.

### Design Decisions

- Prioritized boundary definition over feature expansion.
- Used deterministic control logic instead of LLM inference
  for the independent axis.
- Kept the initial implementation dependency-free.
- Limited real-domain operations to simulated actions.
- Separated implemented behavior from future concepts.
- Deferred cryptographic verification and complex
  orchestration mechanisms to later versions.

### Scope Freeze

v0.1.0 serves as the baseline reference implementation.

The following concepts are intentionally excluded:

- Five-element mutual restriction control.
- Seesaw-based continuous feedback.
- Adaptive hysteresis.
- Dynamic AI role rotation.
- Distributed control-axis coordination.
- Crash-tolerant authority transitions.

Future development must preserve or explicitly revise
the documented v0.1 safety invariants, with
corresponding tests and migration notes.

---

## Release Principle

> Specification does not prove that a concept is correct.
> It makes the concept testable and exposes where
> its assumptions may fail.

Virtual–Real Transition Axis v0.1.0 establishes
the first reproducible behavioral baseline for
the continued development of Zero-Style AI Orchestration.
