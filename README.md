# Virtual–Real Transition Axis

**Version:** v0.1.0  
**Status:** Experimental / Reference Prototype  
**Language:** Python 3.11+  
**Dependencies:** Python Standard Library Only  
**License:** Not yet specified

## 1. Overview

Virtual–Real Transition Axis (VRTA) is a minimal,
testable Python prototype for independent authority
control between virtual observation and real operations.

The project is part of the conceptual development of
**Zero-Style AI Orchestration**.

Its purpose is to explore how AI-related roles can
operate within explicitly defined boundaries without
being allowed to modify the independent control axis.

The prototype implements:

- Virtual and real role separation
- Role-based authority validation
- Evidence-boundary simulation
- Virtual event load limiting
- Backpressure and degraded mode
- Emergency zero-neutralization
- Authority generation invalidation
- Recovery approval conditions
- In-memory hash-chained auditing

The current implementation is a deterministic
behavioral model.

It is **not a production security system**.

---

## 2. Core Design Principle

> Virtual roles observe.
> Real roles perform explicitly permitted operations.
> The independent axis controls authority and state
> transitions without delegating its hard policy
> to either role.

The design separates three responsibilities:

1. Observation
2. Authorized operation
3. Independent control

The independent axis is intentionally implemented
using deterministic Python logic rather than
requiring a large language model.

This allows the control rules to be inspected,
tested, and reproduced independently from
AI inference behavior.

---

## 3. Architecture

```text
                  External Events
                         |
                         v
             +-----------------------+
             |   VIRTUAL DOMAIN      |
             |   Virtual Spider-Web  |
             |                       |
             | - Event reception     |
             | - Format validation   |
             | - Load observation    |
             +-----------------------+
                         |
                         v
             +-----------------------+
             |   EVIDENCE BOUNDARY   |
             |                       |
             | Unverified input must |
             | not become authority. |
             +-----------------------+
                         |
                         v
             +-----------------------+
             |   INDEPENDENT AXIS    |
             |                       |
             | - Hard policy         |
             | - Authority checking  |
             | - Load limiting       |
             | - Neutralization      |
             | - Recovery control    |
             | - Audit records       |
             +-----------------------+
                         |
                         v
             +-----------------------+
             |     REAL DOMAIN       |
             |                       |
             | - Analyze             |
             | - Record              |
             | - Propose             |
             +-----------------------+
```

This diagram represents logical responsibilities.

The current implementation does not establish
operating-system-level isolation, network isolation,
or a cryptographically authenticated evidence channel.

In particular, the virtual and real domains are
logical roles within one Python process.

---

## 4. Repository Structure

```text
virtual-real-transition-axis/
|
|-- README.md
|-- axis.py
|
|-- tests/
|   `-- test_axis.py
|
`-- .github/
    `-- workflows/
        `-- validate.yml
```

### Files

| File | Purpose |
|---|---|
| `axis.py` | Core transition-axis implementation |
| `tests/test_axis.py` | 15 unit tests |
| `README.md` | Architecture and usage documentation |
| `.github/workflows/validate.yml` | Automated validation workflow |

---

## 5. Virtual Domain

The virtual domain receives simulated external
events and performs basic input validation.

Each accepted event must contain a non-empty
string identifier:

```json
{
  "event_id": "event-1"
}
```

The prototype uses a configurable event-count
limit.

Example:

```python
axis = TransitionAxis(virtual_limit=3)
```

The first three valid events are accepted.

A fourth event produces backpressure:

```text
virtual event 1: accepted
virtual event 2: accepted
virtual event 3: accepted
virtual event 4: backpressure
mode: degraded
```

This behavior models a basic load boundary.

It does not implement a production queue,
time-based rate limiting, or adaptive
traffic control.

---

## 6. Evidence Boundary

The evidence boundary prevents a virtual
role from directly performing real operations.

A virtual token cannot execute an operation
requiring real authority.

Additionally, real operations require
the `verified` parameter to be true.

Example:

```python
axis.execute_real(
    real_token,
    "analyze",
    verified=True,
)
```

The following request is rejected:

```python
axis.execute_real(
    real_token,
    "analyze",
    verified=False,
)
```

### Important Limitation

In v0.1, `verified=True` is a caller-supplied
simulation flag.

It is not generated by an independent
evidence verification service.

Consequently, this mechanism demonstrates
the intended control rule but does not
provide a trustworthy evidence boundary
against a malicious caller with real-role
authority.

Independent evidence verification is
a planned v0.2 improvement.

---

## 7. Real Domain

The real domain supports three simulated
operations:

| Operation | Permission |
|---|---|
| `analyze` | Allowed |
| `record` | Allowed |
| `propose` | Allowed |
| `delete` | Denied |
| `deploy` | Denied |
| `execute` | Denied |
| `modify_policy` | Denied |

Only registered tokens assigned to the
real role may request permitted operations.

These operations are represented by
deterministic validation and audit behavior.

They do not execute external commands,
modify production infrastructure, or
perform network-defense actions.

---

## 8. Independent Transition Axis

The independent axis manages the operational
state of the prototype.

It includes four fixed policy identifiers:

```text
virtual_cannot_execute_real
unverified_evidence_cannot_execute
stale_authority_is_rejected
human_approval_required_for_recovery
```

These identifiers are stored in
`TransitionAxis.HARD_POLICY`.

Role-level calls to
`update_hard_policy()` are rejected.

### Policy Scope

The prototype prevents policy modifications
through its designated role-level API.

It does not protect Python class attributes
or process memory from arbitrary code
running inside the same interpreter.

The hard policy is therefore an application
rule, not an immutable security boundary.

---

## 9. Operating Modes

The axis supports three operating modes.

| Mode | Description |
|---|---|
| `normal` | Standard operation |
| `degraded` | Virtual event limit exceeded |
| `zero_neutral` | Emergency neutralization |

### Basic State Transitions

```text
NORMAL
   |
   | Virtual event limit exceeded
   v
DEGRADED
   |
   | Emergency neutralization
   v
ZERO_NEUTRAL
   |
   | Safety flag + approval flag
   v
NORMAL
```

The prototype also supports direct
neutralization from normal mode.

### Degraded Mode

When the virtual event limit is exceeded:

- The axis enters degraded mode.
- Additional virtual events receive backpressure.
- The accepted-event count does not increase.

In v0.1, degraded mode does not automatically
disable already authorized real operations.

### Zero-Neutral Mode

Emergency neutralization:

- Changes the mode to `zero_neutral`
- Resets the virtual event load
- Increments the authority generation
- Invalidates previously issued tokens
- Blocks virtual and real role operations
- Blocks new token issuance

The independent recovery method remains
available to evaluate recovery conditions.

---

## 10. Authority Generation

Each issued token contains:

```text
token_id
role
generation
```

The axis maintains an independent
authority generation number.

When emergency neutralization occurs,
the generation is incremented.

Tokens issued under a previous generation
are rejected.

This models authority invalidation after
an emergency transition.

### Limitation

v0.1 tokens are local Python data objects.

They are not cryptographically signed,
time-limited, or protected against
forgery by arbitrary in-process code.

Token authenticity, expiration, and
revocation management require a stronger
implementation.

---

## 11. Recovery Control

Recovery from zero-neutral mode requires
two simulated conditions:

```python
safety_verified=True
human_approved=True
```

Both must be true.

The following combinations are rejected:

| Safety Verified | Human Approved | Recovery |
|---|---|---|
| False | False | Denied |
| False | True | Denied |
| True | False | Denied |
| True | True | Allowed |

Example:

```python
axis.recover(
    safety_verified=True,
    human_approved=True,
)
```

Successful recovery returns the axis
to normal mode.

Previously invalidated authority
generations remain invalid.

New role tokens must be issued.

### Limitation

Both recovery parameters are simulated
Boolean values supplied by the caller.

v0.1 does not authenticate the human
approver or independently verify
the safety assessment.

Therefore, the recovery API is not
a production-grade authorization boundary.

---

## 12. Audit System

The prototype includes an in-memory
hash-chained audit log.

Each record contains:

```text
index
action
details
previous_hash
hash
```

The hash is calculated using SHA-256
over a deterministic JSON representation.

The audit verifier recalculates the chain
and checks its internal consistency.

Example:

```python
axis.audit.verify()
```

Expected output for an intact chain:

```text
True
```

Unit tests also simulate modification
of an existing audit record.

The modified chain must fail verification.

### Audit Limitations

The current design does not provide:

- Persistent audit storage
- Cryptographic record signatures
- External checkpoint anchoring
- Trusted timestamps
- Protection against complete log replacement

An attacker who controls the process may
rewrite records and recompute the chain.

Therefore, the audit system demonstrates
hash-chain consistency, not independent
tamper-proof logging.

---

## 13. Requirements

- Python 3.11 or later
- Python standard library
- No third-party packages required

The prototype is intended to run locally.

No external network services are required.

---

## 14. Running the Simulation

From the repository root:

```bash
python axis.py
```

Expected output:

```text
virtual event 1: accepted
virtual event 2: accepted
virtual event 3: accepted
virtual event 4: backpressure
mode: degraded
real verified analysis: True
neutral: zero_neutral
recovery check 1: False
recovery check 2 + approval: True
mode: normal
audit chain valid: True
records: 11
```

This output demonstrates one deterministic
simulation scenario.

It does not measure real-world security
effectiveness or attack resistance.

---

## 15. Running Unit Tests

Run:

```bash
python -m unittest discover -s tests -v
```

Expected summary:

```text
Ran 15 tests in ...s

OK
```

The test suite covers:

1. Initial state and hard policy
2. Invalid configuration
3. Token issuance validation
4. Accepted virtual events
5. Backpressure and degraded mode
6. Invalid virtual event rejection
7. Virtual-to-real escalation rejection
8. Unverified real operation rejection
9. Permitted real operations
10. Forbidden real operations
11. Hard policy modification rejection
12. Emergency neutralization
13. Stale authority rejection
14. Recovery condition enforcement
15. Audit integrity and tamper detection

A passing test suite confirms that
the implemented rules behave as specified
under the tested conditions.

It does not prove the absence of
security vulnerabilities.

---

## 16. GitHub Actions

The repository includes an automated
validation workflow:

```text
.github/workflows/validate.yml
```

The workflow is intended to:

1. Set up Python.
2. Run the deterministic simulation.
3. Execute all 15 unit tests.
4. Fail when an executed command exits
   with an error.

The exact CI configuration is maintained
in the workflow file.

---

## 17. Security Boundaries and Threat Model

### Modeled Threats

v0.1 models rejection of:

- Virtual-to-real role escalation
- Unverified operation requests
- Unauthorized operation types
- Stale authority after neutralization
- Role-level attempts to change hard policy
- Recovery without both required conditions
- Basic audit-record modification

### Not Covered

v0.1 does not defend against:

- Arbitrary code execution inside the process
- Malicious callers controlling verification flags
- Cryptographic token forgery
- Host operating-system compromise
- Container or process escape
- Network-based attacks
- Distributed denial-of-service attacks
- External audit-log replacement
- Compromised human approval systems

The virtual and real domains share
a Python process and trust environment.

No actual defensive deployment
is performed.

**Do not deploy this prototype as a
production security control.**

---

## 18. Development Roadmap

### v0.1 — Virtual–Real Transition Axis

Scope:

- Virtual and real role separation
- Independent authority validation
- Event load limiting
- Degraded mode
- Zero-neutralization
- Authority generation invalidation
- Simulated recovery approval
- In-memory audit chain
- Deterministic unit tests

Status: Reference implementation.

### v0.2 — Independent Verification and
Five-Element Authority Matrix

Planned:

- Independent evidence verification
- Verified evidence receipts
- Stronger authority credentials
- Explicit cross-role constraints
- Five-element mutual restriction matrix

The five-element model will be treated
as a testable role-control hypothesis,
not as an assumed security guarantee.

### v0.3 — Negative Feedback and Seesaw Control

Planned:

- Load observation windows
- Hysteresis
- Feedback damping
- Oscillation detection
- Concurrent overload simulation
- Recovery stability evaluation

### v0.4 — Role Rotation and Fault Tolerance

Planned:

- Safe role reassignment
- Transition fault injection
- Authority overlap prevention
- Crash recovery scenarios
- Independent-axis failure handling
- Audit subsystem failure handling

Roadmap features are not included
in v0.1.

---

## 19. Design Philosophy

Virtual–Real Transition Axis follows
a structural-first approach.

The goal is not to construct a complete
defense system in a single step.

Instead, the development process is:

```text
Define boundaries
        |
        v
Implement minimal rules
        |
        v
Test expected behavior
        |
        v
Test prohibited behavior
        |
        v
Identify limitations
        |
        v
Refine the next version
```

The prototype deliberately separates
conceptual architecture from verified
implementation behavior.

A design concept should not be treated
as validated simply because it can
be expressed as a diagram or analogy.

Its assumptions must be translated
into observable behavior and tests.

---

## 20. Foundational Statement

> Specification is not the process of
> proving that a concept is correct.
>
> It is the process of making the concept
> testable, including the possibility
> of discovering where it is wrong.

Virtual–Real Transition Axis v0.1
establishes a minimal reference point
for the future development of
Zero-Style AI Orchestration.

The control boundary comes first.

Additional intelligence, roles, and
coordination mechanisms must remain
subject to that boundary.

---

## Disclaimer

This repository is an experimental
software architecture and educational
reference prototype.

It is not certified, independently
audited, or suitable for direct
production security deployment.

No real-world attack resistance
or operational safety guarantee
is claimed.
