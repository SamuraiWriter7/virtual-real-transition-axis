# Virtual–Real Transition Axis v0.3

## Seesaw Negative Feedback Control

**Specification Version:** 0.3.0  
**Status:** Experimental Specification  
**Baseline:** VRTA v0.2  
**Runtime Target:** Python 3.11+  
**Dependencies:** Python Standard Library Only

---

## 1. Purpose

Virtual–Real Transition Axis (VRTA) v0.3
introduces deterministic negative feedback
control for virtual and real processing loads.

The purpose is to reduce unstable state
transitions caused by fluctuating workloads.

v0.1 established the basic transition axis.

v0.2 introduced independent evidence
verification and five-element authority
restrictions.

v0.3 extends the architecture with
load observation, hysteresis, stability
confirmation, and controlled recovery.

The independent axis remains responsible
for final state transitions.

The feedback controller MUST NOT grant
authority or bypass existing safety
boundaries.

---

## 2. Design Principles

VRTA v0.3 follows six principles.

### P-01: Observe Before Acting

Control decisions MUST be based on
explicitly supplied load observations.

The reference controller MUST NOT infer
load conditions from unverified
external commands.

### P-02: Preserve Independent Domains

Virtual and real loads MUST be evaluated
independently.

A low load in one domain MUST NOT
conceal an overload in the other.

### P-03: Avoid Oscillation

The controller MUST use separate
degradation and recovery thresholds.

A single threshold MUST NOT control
both degradation and recovery.

### P-04: Confirm Stability

Recovery MUST require multiple
consecutive stable observation windows.

A single low-load observation MUST NOT
automatically restore normal operation.

### P-05: Preserve Authority Boundaries

Feedback decisions MUST NOT:

- Issue role tokens.
- Modify hard policy.
- Validate evidence.
- Approve real operations.
- Release five-element restrictions.
- Authorize recovery from zero-neutral mode.

### P-06: Prefer Minimal Control

The controller SHOULD apply the
least complex deterministic response
necessary to maintain the defined
operating boundaries.

---

## 3. Scope

### 3.1 Included

v0.3 introduces:

- Normalized virtual load measurements.
- Normalized real load measurements.
- Fixed-length observation windows.
- Configurable load thresholds.
- Hysteresis.
- Consecutive stability confirmation.
- Deterministic negative feedback.
- Controlled degraded-to-normal recovery.
- Simultaneous overload handling.
- Feedback decision audit records.
- Regression testing for previous versions.

### 3.2 Excluded

v0.3 does not implement:

- Machine-learning-based feedback control.
- Automatic AI-agent role reassignment.
- Dynamic process migration.
- Distributed control consensus.
- Adaptive threshold learning.
- Predictive workload forecasting.
- Production traffic shaping.
- Operating-system-level resource limits.
- Automatic recovery from zero-neutral mode.

These features require separate
design and validation.

---

## 4. Logical Architecture

```text
                  LOAD OBSERVATIONS
                         |
              +----------+----------+
              |                     |
              v                     v
       +-------------+       +-------------+
       | VIRTUAL LOAD|       |  REAL LOAD  |
       |             |       |             |
       | Observation |       | Observation |
       +-------------+       +-------------+
              |                     |
              +----------+----------+
                         |
                         v
              +---------------------+
              | FEEDBACK CONTROLLER |
              |                     |
              | Observation windows |
              | Thresholds          |
              | Hysteresis          |
              | Stability checks    |
              +---------------------+
                         |
                         v
              +---------------------+
              |  INDEPENDENT AXIS   |
              |                     |
              | Authority checks    |
              | Evidence boundaries |
              | Five-element rules  |
              | State transitions   |
              | Audit               |
              +---------------------+
                         |
                         v
              +---------------------+
              | CONTROLLED RESPONSE |
              |                     |
              | Normal              |
              | Degraded            |
              | Zero-neutral        |
              +---------------------+
```

The feedback controller produces
control recommendations.

The independent axis decides whether
the recommended transition is permitted.

The logical separation does not imply
process isolation.

---

## 5. Normative Language

The terms MUST, MUST NOT, SHOULD,
SHOULD NOT, and MAY are used as
normative requirement keywords.

MUST and MUST NOT define mandatory
behavior for the reference implementation.

SHOULD and SHOULD NOT indicate
recommended behavior.

MAY indicates optional behavior.

---

## 6. Load Observation Model

### 6.1 Load Values

Each observation contains:

- `virtual_load`
- `real_load`
- `window_id`

Both load values MUST be normalized
within the inclusive range:

0.0 to 1.0

Examples:

```json
{
  "window_id": 1,
  "virtual_load": 0.35,
  "real_load": 0.42
}
```

```json
{
  "window_id": 2,
  "virtual_load": 0.91,
  "real_load": 0.24
}
```

### 6.2 Validation

The controller MUST reject:

- Missing required fields.
- Non-numeric load values.
- Boolean load values.
- Negative load values.
- Load values greater than 1.0.
- NaN.
- Positive or negative infinity.
- Non-integer window identifiers.
- Negative window identifiers.
- Duplicate window identifiers.
- Out-of-order window identifiers.

Window identifiers MUST increase
strictly between accepted observations.

### 6.3 Observation Trust Boundary

Load observations are inputs to a
simulation model.

The feedback controller MUST NOT
treat an observation as an authorization
request.

In v0.3, measurements are supplied
through a local application interface.

Their physical origin and authenticity
are not independently verified.

An untrusted caller controlling these
measurements could influence the
simulated control decisions.

Production measurement authenticity
is outside the scope of v0.3.

---

## 7. Observation Windows

### 7.1 Window Definition

A window represents one ordered
control observation interval.

The reference implementation uses
explicit window identifiers rather than
relying on real-time scheduling.

For example:

```text
Window 1
Window 2
Window 3
Window 4
```

This makes tests deterministic and
independent of wall-clock timing.

### 7.2 Window Size

The controller MUST support a
configurable positive integer
observation capacity.

Recommended reference default:

```text
window_size = 3
```

This value means that up to three
recent accepted load observations
are retained for inspection.

### 7.3 Sliding Window

When the number of accepted
observations exceeds the configured
capacity, the oldest observation
MUST be removed.

The controller MUST preserve the
order of retained observations.

### 7.4 Decision Input

Each accepted observation MUST be
evaluated using its raw virtual
and real load values.

The controller MAY retain a rolling
window for diagnostic purposes.

It MUST NOT use an average that hides
a current single-domain overload.

A rolling average MUST NOT override
the overload condition defined in
Section 9.

---

## 8. Feedback Configuration

The reference configuration is:

```yaml
degrade_threshold: 0.80
recover_threshold: 0.40
stable_windows_required: 3
window_size: 3
```

### 8.1 Configuration Validation

The following conditions MUST hold:

```text
0.0 <= recover_threshold
recover_threshold < degrade_threshold
degrade_threshold <= 1.0
```

Additionally:

```text
stable_windows_required >= 2
window_size >= 1
```

Both integer parameters MUST be
strictly positive integers where
applicable.

Boolean values MUST NOT be
accepted as numeric configuration.

NaN and infinity MUST be rejected.

### 8.2 Threshold Interpretation

The degradation threshold is inclusive.

If either domain reaches or exceeds
`degrade_threshold`, the controller
MUST recommend degraded operation.

The recovery threshold is also inclusive.

A window is considered stable only if
both domains are at or below
`recover_threshold`.

### 8.3 Hysteresis Band

The interval between the two thresholds
is the hysteresis band.

For the default configuration:

```text
Recover threshold: 0.40
Degrade threshold: 0.80
```

A load between these thresholds
does not automatically trigger
a state change.

The current operational state is
preserved unless another rule
requires a more restrictive state.

---

## 9. Overload Evaluation

### 9.1 Independent Evaluation

For each accepted observation,
the controller MUST evaluate:

```python
virtual_overloaded = (
    virtual_load >= degrade_threshold
)

real_overloaded = (
    real_load >= degrade_threshold
)
```

The combined overload condition is:

```python
overloaded = (
    virtual_overloaded
    or real_overloaded
)
```

### 9.2 Simultaneous Overload

When both domains exceed the
degradation threshold, the
controller MUST report both
overload conditions.

Neither domain may conceal
the condition of the other.

### 9.3 No Average-Based Override

The following example MUST trigger
degradation:

```text
Virtual load: 0.95
Real load:    0.05
Average:      0.50
```

Even though the average is 0.50,
the virtual domain is overloaded.

### 9.4 Overload Priority

A current overload MUST take priority
over accumulated recovery progress.

Any overload MUST reset the consecutive
stable-window counter to zero.

---

## 10. Operating Modes

VRTA v0.3 preserves the existing
operating modes:

| Mode | Meaning |
|---|---|
| `normal` | Standard operation |
| `degraded` | Restricted operation |
| `zero_neutral` | Emergency neutralization |

The feedback controller MUST NOT
introduce additional axis modes
in v0.3.

---

## 11. State Transition Rules

### 11.1 Normal to Degraded

If the axis is in normal mode
and either domain is overloaded,
the feedback controller MUST
recommend:

```text
NORMAL -> DEGRADED
```

The independent axis applies
the transition if no stronger
restriction is already active.

### 11.2 Normal to Normal

If no overload is detected
while the axis is in normal mode,
the controller MUST preserve
normal operation.

### 11.3 Degraded to Degraded

When the axis is degraded,
it MUST remain degraded if:

- Either domain is overloaded.
- Either domain exceeds the
  recovery threshold.
- The consecutive stable-window
  requirement has not been met.

### 11.4 Degraded to Normal

Recovery MAY occur only when
both domains remain at or below
the recovery threshold for the
required number of consecutive
accepted windows.

Default:

```text
stable_windows_required = 3
```

Example:

```text
Window 1: Virtual 0.30, Real 0.35
Window 2: Virtual 0.28, Real 0.31
Window 3: Virtual 0.25, Real 0.29

Result: Recovery eligible
```

The independent axis MUST perform
the final transition decision.

### 11.5 Interrupted Stability

If either domain exceeds
the recovery threshold before
the required consecutive stable
count is reached, the counter
MUST reset to zero.

Example:

```text
Window 1: Stable
Window 2: Stable
Window 3: Unstable
Window 4: Stable

Result:
Stable count = 1
Recovery denied
```

### 11.6 Zero-Neutral Mode

When the independent axis is in
zero-neutral mode, feedback MUST
NOT restore normal or degraded
operation.

Recovery from zero-neutral mode
remains controlled by the existing
authority and approval mechanism.

The feedback controller MUST
NOT interpret low load as human
approval.

---

## 12. Negative Feedback Behavior

### 12.1 Basic Principle

The feedback controller MUST
recommend reduced operational
activity when an overload is
detected.

It MUST NOT respond to overload
by granting additional authority.

### 12.2 Restrictive Response

The reference implementation
uses degraded mode as the
primary negative feedback output.

The model does not execute
actual operating-system resource
throttling.

### 12.3 Recovery Response

The controller MUST delay
degraded-to-normal recovery until
the configured stability
requirement is met.

This delay is intended to reduce
frequent state oscillation.

### 12.4 No Automatic Privilege Expansion

Returning to normal mode MUST NOT:

- Mint new tokens.
- Reactivate stale tokens.
- Revalidate stale receipts.
- Release five-element restrictions.
- Modify the trusted-source registry.
- Override hard policy.

Normal mode means that
feedback-related degradation
has been cleared.

It does not mean that all
other restrictions are removed.

---

## 13. Integration with v0.2

### 13.1 Evidence Verification

The feedback controller MUST NOT
issue verification receipts.

It MUST NOT bypass the
`TransitionAxisV2` evidence
verification path.

### 13.2 Five-Element Restrictions

Active five-element restrictions
MUST remain enforceable regardless
of the feedback state.

For example:

```text
Feedback state: NORMAL
Five-element control:
SUSPEND_ANALYSIS active

Result:
Analysis remains denied.
```

### 13.3 Authority Generations

Feedback transitions MUST NOT
modify authority generations.

Emergency neutralization remains
responsible for generation
invalidation.

### 13.4 Existing Degraded State

The v0.2 axis already supports
a degraded state caused by its
virtual event-count limit.

The v0.3 integration MUST NOT
clear a degraded state while
another active degradation cause
remains unresolved.

The reference integration MUST
track feedback-related
degradation separately from
legacy event-count degradation.

A feedback recovery decision
MUST NOT implicitly reset
the legacy event counter.

### 13.5 State Ownership

The feedback module owns
observation history and
stability counters.

The independent axis owns
the authoritative operating mode.

The feedback module MUST NOT
directly mutate the axis mode.

---

## 14. Feedback Decision Model

Each decision SHOULD contain:

- `window_id`
- `virtual_load`
- `real_load`
- `virtual_overloaded`
- `real_overloaded`
- `stable_count`
- `recommended_mode`
- `reason`

Example:

```json
{
  "window_id": 4,
  "virtual_load": 0.92,
  "real_load": 0.30,
  "virtual_overloaded": true,
  "real_overloaded": false,
  "stable_count": 0,
  "recommended_mode": "degraded",
  "reason": "virtual_overload"
}
```

Recommended reason codes:

```text
normal_stable
virtual_overload
real_overload
simultaneous_overload
hysteresis_hold
recovery_pending
recovery_eligible
zero_neutral_hold
```

These codes describe control
decisions, not security
authorization results.

---

## 15. Failure Behavior

### 15.1 Invalid Observation

Invalid observations MUST
be rejected.

Rejected observations MUST NOT
advance the stable-window count.

Rejected observations MUST NOT
trigger a recovery transition.

### 15.2 Incomplete Observation

If either domain load is missing,
the controller MUST NOT assume
a zero load for that domain.

### 15.3 Invalid Configuration

Invalid threshold or window
configuration MUST prevent
controller initialization.

### 15.4 Observation Failure

When observation data cannot
be evaluated, the reference
controller MUST NOT recommend
a less restrictive state.

### 15.5 Controller Failure

The independent axis MUST NOT
enter normal mode solely because
the feedback controller fails.

A failed feedback evaluation
MUST NOT bypass existing
authorization checks.

### 15.6 Fail-Closed Boundaries

Feedback failures MUST NOT:

- Authorize real operations.
- Invalidate required evidence checks.
- Release existing restrictions.
- Trigger zero-neutral recovery.

---

## 16. Audit Requirements

The axis MUST record significant
feedback decisions.

Required events include:

- Feedback-induced degradation.
- Recovery eligibility.
- Recovery accepted.
- Recovery denied by another
  active restriction.
- Invalid control recommendations.
- Rejected observations when
  presented through the axis.

Audit records SHOULD include:

- Window identifier.
- Relevant domain loads.
- Previous mode.
- New mode.
- Reason code.
- Stability counter.
- Authority generation.

The feedback module MAY retain
diagnostic observations independently.

Such diagnostic history MUST NOT
replace the axis audit log.

The existing in-memory hash chain
remains the reference audit system.

---

## 17. Required Invariants

The v0.1 and v0.2 invariants
remain applicable.

v0.3 adds the following.

### INV-13 — Stable Recovery

Degraded-to-normal recovery MUST
require consecutive stable windows.

### INV-14 — Hysteresis

Loads within the hysteresis band
MUST NOT independently trigger
a state transition.

### INV-15 — Independent Load Evaluation

Overload in one domain MUST NOT
be hidden by low load in another.

### INV-16 — No Authority Expansion

Feedback control MUST NOT
grant or restore authority.

### INV-17 — Zero-Neutral Priority

Feedback control MUST NOT
automatically recover the axis
from zero-neutral mode.

### INV-18 — Auditable Transitions

Feedback-induced state transitions
MUST be auditable.

### INV-19 — Cause Preservation

Feedback recovery MUST NOT clear
an unrelated degradation cause.

### INV-20 — Invalid Input Isolation

Invalid observations MUST NOT
advance recovery or alter the
authoritative operating mode.

---

## 18. Required Test Categories

### 18.1 Configuration

- Valid default configuration.
- Invalid threshold ordering.
- Equal recovery and degradation thresholds.
- Negative thresholds.
- Thresholds above 1.0.
- NaN and infinity.
- Invalid window size.
- Invalid stability count.
- Boolean values rejected as numbers.

### 18.2 Observations

- Valid normalized loads.
- Missing virtual load.
- Missing real load.
- Invalid load types.
- Out-of-range loads.
- Duplicate window identifiers.
- Out-of-order window identifiers.
- Sliding-window capacity.

### 18.3 Degradation

- Virtual overload.
- Real overload.
- Simultaneous overload.
- Exact threshold boundary.
- Average masking prevention.
- Normal-mode retention below threshold.

### 18.4 Hysteresis

- Load within hysteresis band.
- Degraded-state retention.
- Recovery threshold boundary.
- Interrupted stable sequence.
- Overload resetting recovery progress.

### 18.5 Recovery

- Recovery after required stable windows.
- Recovery denied before sufficient stability.
- No recovery from zero-neutral.
- Stable-window counter reset.
- Recovery without privilege expansion.

### 18.6 Axis Integration

- Feedback degradation applied by axis.
- Feedback recovery applied by axis.
- Legacy degradation cause preserved.
- Active five-element restrictions preserved.
- Stale-token rejection preserved.
- Receipt validation preserved.
- Invalid feedback decision rejected.
- Feedback transition audited.

### 18.7 Regression

All applicable v0.1 and v0.2 tests
MUST continue to pass.

Any intentional compatibility change
MUST be documented and covered
by replacement tests.

---

## 19. Reference Implementation

The intended repository structure is:

```text
virtual-real-transition-axis/
├── README.md
├── CHANGELOG.md
├── axis.py
├── evidence.py
├── five_elements.py
├── feedback.py
├── specs/
│   ├── vrta-v0.2.md
│   └── vrta-v0.3.md
├── tests/
│   ├── test_axis.py
│   ├── test_evidence.py
│   ├── test_five_elements.py
│   └── test_feedback.py
└── .github/
    └── workflows/
        └── validate.yml
```

### feedback.py

Responsibilities:

- Feedback configuration validation.
- Load observation validation.
- Sliding-window history.
- Hysteresis evaluation.
- Stability counting.
- Deterministic control decisions.

### axis.py

Responsibilities:

- Authoritative operating mode.
- Feedback decision application.
- Degradation-cause tracking.
- Authority invariants.
- Evidence and five-element integration.
- State-transition auditing.

### tests/test_feedback.py

Responsibilities:

- Controller unit tests.
- Boundary-condition tests.
- Recovery stability tests.
- Integration tests.
- Regression protection.

---

## 20. Reference State Machine

```text
                  +-----------+
                  |  NORMAL   |
                  +-----------+
                        |
                        | Either load >= 0.80
                        v
                  +-----------+
                  | DEGRADED  |
                  +-----------+
                        |
                        | Both loads <= 0.40
                        | for 3 consecutive
                        | accepted windows
                        v
                  +-----------+
                  |  NORMAL   |
                  +-----------+


Emergency neutralization:

NORMAL or DEGRADED
        |
        v
  +--------------+
  | ZERO_NEUTRAL |
  +--------------+
        |
        | Independent safety verification
        | and authorized human approval
        v
  +--------------+
  |    NORMAL    |
  +--------------+

Feedback alone cannot perform
the final transition.
```

This diagram describes the
reference decision policy.

Additional active degradation causes
may prevent feedback recovery.

---

## 21. Acceptance Criteria

VRTA v0.3 is eligible for release when:

1. The feedback controller validates
   all required configuration fields.

2. Invalid observations are rejected
   without advancing recovery progress.

3. Virtual and real overloads are
   evaluated independently.

4. Separate degradation and recovery
   thresholds prevent immediate
   threshold-based oscillation.

5. Consecutive stable observations
   are required for recovery.

6. Simultaneous overload conditions
   are represented correctly.

7. Feedback does not authorize
   evidence-gated operations.

8. Feedback does not release
   five-element restrictions.

9. Feedback does not invalidate or
   reactivate authority generations.

10. Zero-neutral mode cannot be
    automatically exited by feedback.

11. Legacy degradation causes are
    preserved during feedback recovery.

12. Required feedback transitions
    are recorded in the axis audit.

13. All applicable previous-version
    regression tests pass.

14. The complete test suite passes
    through GitHub Actions.

Passing these criteria establishes
conformity with the tested behavioral
requirements.

It does not establish real-world
control stability or attack resistance.

---

## 22. Deferred Work

### v0.4 — Role Rotation and Fault Tolerance

Planned areas include:

- Safe role reassignment.
- Authority overlap detection.
- Fault injection during transitions.
- Crash recovery.
- Independent-axis failure handling.
- Audit subsystem failure handling.

### Future Security Engineering

Additional work may include:

- Authenticated load measurement.
- Cryptographically protected authority.
- External evidence verification.
- Durable audit checkpoints.
- Process-level isolation.
- Production resource enforcement.

These capabilities are outside
the v0.3 reference scope.

---

## 23. Foundational Statement

> A stable control system does not
> eliminate fluctuation.
>
> It prevents ordinary fluctuation
> from becoming uncontrolled
> state oscillation.

The Seesaw Negative Feedback Control
model allows changing workloads
without treating every small change
as a reason to switch operating modes.

The independent axis retains
authority over state transitions.

The feedback controller observes,
evaluates, and recommends.

It does not govern itself.

VRTA v0.3 therefore extends
Zero-Style AI Orchestration from
static authority boundaries toward
testable dynamic stability rules.

---

## Disclaimer

Virtual–Real Transition Axis v0.3
is an experimental reference
architecture and simulation model.

It does not implement real-time
operating-system scheduling,
production load balancing,
or independently verified
security enforcement.

The reference thresholds are
experimental parameters.

They are not validated
production safety limits.

Do not deploy this prototype
as a production security control.
