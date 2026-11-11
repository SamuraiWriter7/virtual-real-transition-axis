# Virtual–Real Transition Axis v0.2

## Independent Evidence Verification &
## Five-Element Authority Matrix

**Specification Version:** 0.2.0  
**Status:** Experimental Specification  
**Baseline:** VRTA v0.1.0  
**Runtime Target:** Python 3.11+  
**Dependencies:** Python Standard Library Only

---

## 1. Purpose

Virtual–Real Transition Axis (VRTA) v0.2 extends the
deterministic control model introduced in v0.1.

The purpose of v0.2 is to address two limitations:

1. Caller-controlled evidence verification flags.
2. Lack of explicit cross-role restriction rules.

v0.1 established:

- Virtual and real role separation.
- Authority token generation tracking.
- Virtual event backpressure.
- Degraded and zero-neutral modes.
- Emergency authority invalidation.
- Conditional recovery.
- In-memory hash-chained auditing.

v0.2 preserves these mechanisms while introducing
independent evidence verification and a restrictive
five-element authority matrix.

This specification defines behavioral requirements,
not production security guarantees.

---

## 2. Scope

### 2.1 Included

v0.2 introduces:

- Evidence identity and content binding.
- Trusted-source registration within the local model.
- Deterministic evidence validation.
- Axis-owned verification receipts.
- Receipt-to-operation binding.
- Rejection of forged or mismatched receipts.
- Evidence invalidation after authority rotation.
- Five-element role definitions.
- Explicit cross-role restriction permissions.
- Denial of unauthorized restriction requests.
- Audit records for verification and restriction.
- Regression testing against v0.1 behavior.

### 2.2 Excluded

v0.2 does not implement:

- Public-key cryptographic identity.
- Production digital signatures.
- Network-based evidence verification.
- External trust authorities.
- Operating-system process isolation.
- Container orchestration.
- Distributed consensus.
- Adaptive feedback or hysteresis.
- Dynamic role rotation.
- Durable tamper-resistant audit storage.

These mechanisms require separate implementation
and validation.

---

## 3. Architectural Principle

The central principle is:

> Evidence verification, authority decisions, and
> real operations must remain separate responsibilities.

A verified observation does not automatically
grant operational authority.

A permitted role does not automatically establish
the truth of its evidence.

An authorization decision requires both valid
authority and valid evidence when evidence is
required by the operation.

---

## 4. Logical Architecture

```text
                  EXTERNAL EVENT
                         |
                         v
              +---------------------+
              |   VIRTUAL DOMAIN    |
              |                     |
              | Event observation   |
              | Format validation   |
              | Load limiting       |
              +---------------------+
                         |
                         v
              +---------------------+
              | EVIDENCE VERIFIER   |
              |                     |
              | Source validation   |
              | Content binding     |
              | Evidence evaluation |
              +---------------------+
                         |
                         v
              +---------------------+
              | INDEPENDENT AXIS    |
              |                     |
              | Receipt validation  |
              | Authority control   |
              | Five-element rules  |
              | State transitions   |
              | Audit               |
              +---------------------+
                         |
                         v
              +---------------------+
              |    REAL DOMAIN      |
              |                     |
              | Analyze             |
              | Record              |
              | Propose             |
              +---------------------+
```

All components remain logical modules within
a local reference implementation.

The diagram does not imply process-level
or cryptographic isolation.

---

## 5. Normative Language

The terms MUST, MUST NOT, SHOULD, SHOULD NOT,
and MAY indicate normative requirements.

MUST and MUST NOT define mandatory behavior
for a conforming v0.2 implementation.

SHOULD and SHOULD NOT define recommended behavior.

MAY indicates an optional behavior.

---

## 6. Evidence Model

### 6.1 Evidence Record

Each evidence record MUST include:

- `evidence_id`
- `event_id`
- `source_id`
- `payload`
- `payload_digest`

Example:

```json
{
  "evidence_id": "evidence-001",
  "event_id": "event-001",
  "source_id": "sensor-alpha",
  "payload": {
    "event_type": "simulated_anomaly",
    "severity": "medium"
  },
  "payload_digest": "<sha256-hex>"
}
```

The `payload_digest` MUST be calculated from
a deterministic canonical representation of
the payload.

For the Python reference implementation,
canonical serialization is defined as:

```python
json.dumps(
    payload,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8")
```

The digest is the lowercase hexadecimal
SHA-256 value of those bytes.

### 6.2 Source Registry

The verifier MUST maintain a local registry
of trusted source identifiers.

A source identifier MUST NOT become trusted
merely because it appears in an evidence record.

Source registration MUST occur through an
axis-controlled administrative interface.

Virtual and real role tokens MUST NOT be able
to modify the trusted-source registry.

The trusted-source registry models an
administrative trust decision.

It does not authenticate the real-world
identity of a source.

### 6.3 Evidence Validation

The verifier MUST reject evidence when:

- Required fields are missing.
- Field types are invalid.
- Identifiers are empty.
- The source is not registered.
- The payload digest does not match.
- The evidence identifier conflicts with
  an existing evidence record.
- The corresponding event has not been
  accepted by the virtual domain.
- The evidence references a different event.
- The axis is in zero-neutral mode.

A structurally valid payload MUST NOT be
treated as proof that its contents are true.

---

## 7. Verification Receipt

### 7.1 Purpose

The verifier produces a verification receipt
only after the evidence passes all required
checks.

A receipt represents the result of an
explicit verification procedure.

It does not grant execution authority.

### 7.2 Receipt Fields

Each receipt MUST contain:

- `receipt_id`
- `evidence_id`
- `event_id`
- `payload_digest`
- `verifier_id`
- `generation`
- `status`

The status of an accepted receipt MUST be
`verified`.

### 7.3 Receipt Ownership

The axis MUST maintain an internal registry
of accepted verification receipts.

The caller MUST NOT be allowed to register
an arbitrary receipt as verified.

A caller-supplied receipt object MUST NOT
be sufficient to establish verification.

The axis MUST resolve the receipt identifier
against its own internal registry.

Receipt identity, contents, and authority
generation MUST be checked before use.

### 7.4 Receipt Validity

A receipt MUST be rejected when:

- Its identifier is unknown.
- Its stored contents do not match.
- Its status is not `verified`.
- Its evidence has been invalidated.
- Its event or payload binding is incorrect.
- Its authority generation is stale.
- The operation references unrelated evidence.

After emergency neutralization, receipts
from previous generations MUST NOT authorize
new operations.

---

## 8. Real Operation Authorization

### 8.1 Permitted Operations

v0.2 preserves the three permitted
simulated real operations:

- `analyze`
- `record`
- `propose`

All other operation names MUST be rejected.

### 8.2 Authorization Requirements

A real operation requiring evidence MUST pass:

1. Registered real-role token validation.
2. Current authority generation validation.
3. Current axis-mode validation.
4. Operation allowlist validation.
5. Verification receipt validation.
6. Receipt-to-evidence binding validation.
7. Applicable five-element restriction checks.

Failure of any mandatory condition MUST
deny the operation.

### 8.3 Caller-Controlled Verification

The v0.1 pattern:

```python
execute_real(
    token,
    operation,
    verified=True,
)
```

MUST NOT be accepted as sufficient evidence
verification in v0.2.

The v0.2 interface SHOULD use a registered
verification receipt identifier.

Example:

```python
axis.execute_real_verified(
    real_token,
    "analyze",
    receipt_id="receipt-001",
)
```

The receipt identifier MUST be resolved
against the axis-owned receipt registry.

This method is the normative evidence-gated
operation interface for v0.2.

If the legacy `execute_real()` method remains
available for compatibility, it MUST NOT
provide an alternative path to evidence-gated
real operations.

---

## 9. Five-Element Role Model

The five elements define functional
control roles.

They are not AI personalities or claims
about natural laws.

| Element | Role | Primary Responsibility |
|---|---|---|
| Wood | Observation | Virtual event intake |
| Fire | Analysis | Authorized real analysis |
| Earth | Verification | Evidence assessment |
| Metal | Authority | Permission enforcement |
| Water | Audit | Observation of state and recovery conditions |

The independent axis remains above
the five-element role model.

No element may modify the axis hard policy.

---

## 10. Mutual Restriction Matrix

### 10.1 Principle

Mutual restriction means bounded control
over another functional role.

It MUST NOT imply unrestricted command
authority.

A restriction request may reduce or
suspend permitted activity.

It MUST NOT increase the requester's
privileges or grant the requester
the target's privileges.

### 10.2 Allowed Relations

The following five relationships are
defined for v0.2:

| Source | Target | Allowed Restriction |
|---|---|---|
| Wood | Earth | Request evidence review |
| Earth | Water | Flag audit or recovery inconsistency |
| Water | Fire | Request analysis suspension |
| Fire | Metal | Propose authority review |
| Metal | Wood | Restrict virtual event intake |

These relationships describe allowed
requests, not direct target mutations.

### 10.3 Explicit Actions

Each relationship has one allowed action:

| Source | Target | Action |
|---|---|---|
| Wood | Earth | `request_review` |
| Earth | Water | `flag_inconsistency` |
| Water | Fire | `suspend_analysis` |
| Fire | Metal | `request_authority_review` |
| Metal | Wood | `restrict_intake` |

All other source-target-action combinations
MUST be rejected.

### 10.4 Restriction Request

A restriction request MUST contain:

- `request_id`
- `source_element`
- `target_element`
- `action`
- `reason`

The source element MUST be associated
with a registered authority token.

The request MUST NOT be accepted solely
because the caller claims an element name.

### 10.5 Enforcement

The independent axis MUST:

1. Authenticate the local registered token
   according to the reference authority model.
2. Resolve the token's assigned element.
3. Validate the allowed relation.
4. Validate the requested action.
5. Validate the reason.
6. Record the decision.
7. Apply only explicitly defined state changes.

In v0.2, the actions
`request_review`,
`flag_inconsistency`, and
`request_authority_review`
are advisory requests only.

They MUST NOT directly mutate the target
role's privileges.

The actions `suspend_analysis` and
`restrict_intake` are restrictive controls.

When accepted:

- `suspend_analysis` MUST deny subsequent
  `analyze` operations while active.
- `restrict_intake` MUST deny subsequent
  virtual event intake while active.

A successful restriction request MUST
NOT implicitly enable a new operation.

### 10.6 Restriction Release

Restrictive controls MUST remain active
until the independent axis explicitly
releases them.

A release MUST NOT be performed by the
requesting element itself.

v0.2 MAY implement release as a
local administrative operation.

Releasing a restriction MUST NOT override
zero-neutral mode, stale-token checks,
or other mandatory authorization rules.

---

## 11. Authority Boundaries

### 11.1 Element Binding

A token's element assignment MUST be
stored in the axis-controlled registry.

The caller MUST NOT choose or alter
its element during a restriction request.

### 11.2 Least Authority

An element token MUST authorize only
its explicitly assigned capabilities.

Possession of a five-element token
MUST NOT automatically grant virtual
or real operation privileges.

### 11.3 Hard Policy

The existing v0.1 hard policy remains
applicable.

No five-element token may:

- Modify hard policy.
- Mint unrestricted authority.
- Bypass evidence verification.
- Cancel neutralization.
- Revalidate stale tokens.
- Self-approve recovery.

---

## 12. State Transitions

The three v0.1 modes remain unchanged:

- `normal`
- `degraded`
- `zero_neutral`

### 12.1 Normal to Degraded

The virtual event limit MAY trigger
the existing degraded mode.

### 12.2 Neutralization

Emergency neutralization MUST:

- Enter zero-neutral mode.
- Increment authority generation.
- Invalidate existing role tokens.
- Invalidate prior-generation receipts.
- Block evidence-gated real operations.
- Block virtual event intake.
- Block new role-token issuance.

### 12.3 Recovery

Recovery MUST require both:

- A positive safety verification condition.
- An authorized human approval condition.

The v0.1 Boolean recovery parameters
remain a documented simulation limitation
unless replaced by a stronger mechanism.

Recovery MUST NOT reactivate invalidated
tokens or evidence receipts.

Recovery MUST NOT silently remove
unresolved restrictive controls.

---

## 13. Audit Requirements

The audit system MUST record:

- Evidence accepted for verification.
- Evidence verification rejected.
- Verification receipt issued.
- Verification receipt rejected.
- Real operation permitted or denied.
- Restriction request accepted or denied.
- Restrictive control activated.
- Restrictive control released.
- Emergency neutralization.
- Recovery decision.

Audit records SHOULD contain:

- Event or evidence identifier.
- Relevant role or element.
- Operation or restriction action.
- Decision.
- Reason code.
- Authority generation.

Audit records SHOULD avoid storing
unnecessary sensitive payload content.

The v0.1 in-memory SHA-256 hash chain
remains the audit mechanism.

It does not provide durable
tamper-resistant storage.

---

## 14. Failure Behavior

### 14.1 Fail Closed

Evidence verification failures MUST
deny evidence-gated operations.

Unknown receipts MUST be rejected.

Unknown element relationships MUST
be rejected.

Unrecognized operation names MUST
be rejected.

### 14.2 Verifier Failure

If evidence verification cannot complete,
no verified receipt may be issued.

The verifier MUST NOT issue a positive
receipt merely because of timeout,
missing data, or an internal exception.

### 14.3 Axis State

A failure of evidence verification MUST
NOT automatically grant permission
through another route.

Emergency neutralization remains the
highest-priority operational restriction.

### 14.4 Input Validation

Malformed external input MUST be rejected
without granting new authority.

Invalid data MUST NOT be silently
converted into a successful decision.

---

## 15. Required Invariants

### INV-01 — Domain Separation

Virtual-role authority MUST NOT execute
real-domain operations.

### INV-02 — No Self-Verification

A caller MUST NOT authorize an operation
by asserting its own verified status.

### INV-03 — Evidence Binding

Each verified receipt MUST be bound to
a specific evidence record, event, and
payload digest.

### INV-04 — Separation of Duties

Evidence verification MUST NOT itself
grant permission to execute real operations.

### INV-05 — Element Authority Boundaries

Five-element roles MUST NOT expand
their own authority.

### INV-06 — Restrictive Controls

Cross-element controls MUST NOT grant
new permissions to their requester.

### INV-07 — Hard Policy Protection

Role-level interfaces MUST NOT permit
modification of the independent axis policy.

### INV-08 — Generation Invalidation

Neutralization MUST invalidate
previous-generation tokens and receipts.

### INV-09 — Conditional Recovery

Recovery MUST require the configured
safety and approval conditions.

### INV-10 — Fail-Closed Verification

Invalid, unknown, or stale verification
receipts MUST NOT authorize operations.

### INV-11 — Restriction Persistence

Active restrictions MUST NOT disappear
implicitly during recovery.

### INV-12 — Auditable Decisions

Verification, authorization, restriction,
neutralization, and recovery decisions
MUST produce audit records.

---

## 16. Required Test Categories

A conforming v0.2 implementation MUST
provide automated tests covering the
following cases.

### 16.1 Evidence Verification

- Valid trusted-source evidence.
- Unknown evidence source.
- Missing evidence identifier.
- Malformed payload digest.
- Payload modification after digest creation.
- Unknown or unaccepted event.
- Duplicate or conflicting evidence identifier.
- Unknown verification receipt.
- Mismatched receipt and evidence.
- Forged receipt object or identifier.
- Stale receipt after neutralization.
- Verifier failure without positive receipt.

### 16.2 Real Operations

- Verified evidence with valid real authority.
- Verified evidence with virtual authority.
- Unverified evidence with real authority.
- Forbidden operation with verified evidence.
- Active analysis suspension.
- Recovery without receipt revalidation.

### 16.3 Five-Element Authority

- Every allowed source-target-action relation.
- Invalid source-target relation.
- Invalid action.
- Forged source-element claim.
- Unauthorized token.
- Missing reason.
- Restriction that would expand privileges.
- Restriction activation.
- Restriction persistence.
- Unauthorized restriction release.
- Valid administrative release.

### 16.4 State and Audit

- Normal mode behavior.
- Degraded mode behavior.
- Neutralization.
- Stale-token rejection.
- Stale-receipt rejection.
- Recovery condition enforcement.
- Audit-chain consistency.
- Audit-chain modification detection.

### 16.5 Regression

All 15 v0.1 unit tests MUST remain
passing, or a documented and tested
compatibility replacement MUST be provided.

---

## 17. Reference Implementation Structure

The intended repository layout is:

```text
virtual-real-transition-axis/
├── README.md
├── CHANGELOG.md
├── axis.py
├── evidence.py
├── five_elements.py
├── specs/
│   └── vrta-v0.2.md
├── tests/
│   ├── test_axis.py
│   ├── test_evidence.py
│   └── test_five_elements.py
└── .github/
    └── workflows/
        └── validate.yml
```

### Module Responsibilities

`evidence.py`

- Evidence record validation.
- Deterministic digest calculation.
- Trusted-source lookup.
- Verification receipt representation.

`five_elements.py`

- Element definitions.
- Restriction relation matrix.
- Allowed-action validation.
- Restriction request representation.

`axis.py`

- Authority registry.
- Evidence and receipt registry coordination.
- Operation authorization.
- Restriction state enforcement.
- Neutralization and recovery.
- Audit integration.

The axis remains the final authority
decision point.

---

## 18. Compatibility Policy

v0.2 MUST preserve the safety-relevant
behavior of v0.1.

The original API MAY be extended.

However, a legacy method MUST NOT
allow callers to bypass evidence-gated
authorization.

The preferred migration is:

```text
v0.1:
Caller -> verified=True -> Real Operation

v0.2:
Caller -> Evidence -> Independent Verification
       -> Registered Receipt
       -> Axis Authorization
       -> Real Operation
```

Any incompatible API changes MUST be
documented in the changelog.

Existing simulation behavior SHOULD remain
reproducible using an explicitly identified
v0.1 compatibility path or test fixture.

Such a path MUST NOT be enabled as a
verification bypass in the v0.2
evidence-gated interface.

---

## 19. Acceptance Criteria

v0.2 is eligible for release when:

1. All mandatory evidence validation rules
   are implemented and tested.

2. Caller-supplied verification flags cannot
   authorize v0.2 evidence-gated operations.

3. Receipts are generated and registered
   only through the designated verifier path.

4. Unknown, altered, and stale receipts
   are rejected.

5. The five-element matrix is enforced
   as an explicit allowlist.

6. Cross-element actions cannot expand
   the requester's authority.

7. Active restrictive controls are enforced
   and cannot be removed by role-level calls.

8. Neutralization invalidates previous
   tokens and receipts.

9. Audit records cover mandatory decisions.

10. All applicable v0.1 regression tests
    and new v0.2 tests pass in GitHub Actions.

Passing these criteria validates
the implemented behavioral model.

It does not establish production-level
security assurance.

---

## 20. Deferred Work

The following subjects are intentionally
deferred.

### v0.3

- Hysteresis.
- Time-window load control.
- Negative feedback.
- Oscillation detection.
- Concurrent overload handling.

### v0.4

- Dynamic role rotation.
- Crash-safe transitions.
- Independent-axis failure handling.
- Audit subsystem failure handling.
- More durable authority lifecycle controls.

Production cryptographic identity,
trusted human approval, process isolation,
and durable audit anchoring remain
separate security-engineering requirements.

They MUST NOT be represented as completed
v0.2 features.

---

## 21. Foundational Statement

> Verification is not authorization.
> Authority is not evidence.
> Observation is not execution.

The purpose of the independent axis is
to prevent these responsibilities
from being collapsed into one
unrestricted decision path.

The five-element model adds bounded
cross-role restrictions without
allowing any element to become
an unrestricted controller.

Virtual–Real Transition Axis v0.2
therefore extends the v0.1 separation
model into an explicit structure for
verification, authority, and controlled
interaction.

---

## Disclaimer

VRTA v0.2 is an experimental
reference architecture.

It is not independently security-audited.

It does not establish cryptographic
trust boundaries or process isolation.

Do not use it as a production
security enforcement system.
