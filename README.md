# Virtual–Real Transition Axis

**VRTA v0.5.0 · Experimental reference prototype · Python 3.11+ · [MIT License](LICENSE)**

Virtual–Real Transition Axis (VRTA) is a standard-library-only Python model for independent authority control in **Zero-Style AI Orchestration**. Virtual roles receive observations. Real roles request a small set of simulated operations. The axis decides which requests are allowed and when the system must stop or may recover.

> **Restore restrictions. Do not restore authority.**

In v0.5, every startup begins in `zero_neutral`. The axis can restore confirmed restrictions from a local checkpoint, but it does not restore role credentials, five-element tokens, accepted events, evidence receipts, or earlier approval. Going back to normal requires fresh approval for the current startup and checkpoint revision.

## Design principle

Virtual roles observe. Real roles perform only explicitly permitted operations. Neither role can rewrite the rules the independent axis uses to grant authority, enforce restrictions, or change modes.

The axis uses deterministic Python rules without an LLM. This lets tests cover what the system permits, what it denies, and what it does when a transition is interrupted. The domains are logical roles in one interpreter, not separate security perimeters.

## Quick start

Run these commands from the repository root. No dependencies need to be installed.

```bash
python -m unittest discover -s tests -v
python axis.py
python feedback.py
```

The suite contains **143 tests**. `python axis.py` runs the v0.1 compatibility simulation, and `python feedback.py` runs the v0.3 feedback simulation. To work with restart recovery, use `TransitionAxisV5`.

### Try the v0.5 restart model

Run this example from the repository root. It uses a temporary checkpoint and creates a second axis instance to illustrate a restart. The integration suite separately tests an actual stop and restart in child processes.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from axis import Mode, Role, TransitionAxisV5
from checkpoint import CheckpointStore
from evidence import build_evidence
from five_elements import RestrictionAction

admin = object()  # Local administrative capability in this prototype.


def open_axis(path):
    return TransitionAxisV5(
        checkpoint=CheckpointStore(path, store_id="demo"),
        trusted_sources=frozenset({"sensor-1"}),
        element_bindings={},
        administrator=admin,
    )


with TemporaryDirectory() as directory:
    path = Path(directory) / "checkpoint.json"
    axis = open_axis(path)
    axis.provision_checkpoint(
        administrator=admin,
        restrictions=frozenset({"suspend_analysis"}),
    )
    approval_context = axis.recovery_context()
    assert axis.recover(
        administrator=admin,
        context=approval_context,
        safety_verified=True,
        human_approved=True,
    )

    virtual = axis.issue_token("observer", Role.VIRTUAL, administrator=admin)
    real = axis.issue_token("recorder", Role.REAL, administrator=admin)
    axis.receive_virtual(virtual, {"event_id": "event-1"})
    receipt = axis.verify_evidence(build_evidence(
        evidence_id="evidence-1",
        event_id="event-1",
        source_id="sensor-1",
        payload={"kind": "sample"},
    ))
    assert axis.execute_real_verified(real, "record", receipt_id=receipt.receipt_id)

    restarted = open_axis(path)
    assert restarted.mode == Mode.ZERO_NEUTRAL
    assert restarted.restriction_active(RestrictionAction.SUSPEND_ANALYSIS)
    assert not restarted.recover(
        administrator=admin,
        context=approval_context,
        safety_verified=True,
        human_approved=True,
    )
```

`provision_checkpoint()` is explicit commissioning for a new store, not a way to resume an existing one. To recover after restart, inspect the checkpoint, obtain the new `recovery_context()`, and supply fresh simulated safety verification and human approval. Issue new credentials and verify new evidence after recovery.

## How the axis works

| Boundary | What the reference model checks |
|---|---|
| Observation and evidence | A virtual credential may submit observations, not execute real operations. Evidence verification checks source registration, content binding, and an accepted event before issuing a receipt. |
| Real operations | `analyze`, `record`, and `propose` require current real authority and a matching receipt. They are simulated operations, not external commands. |
| Restrictions and load | The five-element matrix constrains which roles may request restrictions. Virtual-event limits and hysteresis can cause degradation independently. Low load does not release a restriction or exit `zero_neutral`. |
| Role handover | An administrator can request replacement of a holder of the same domain role. The old credential is revoked before a replacement is published. A normal handover does not grant another role's permissions. |

| Mode | Behavior |
|---|---|
| `normal` | Requests still need the appropriate authority, evidence, and clearance under active restrictions. |
| `degraded` | Load control applies backpressure to virtual input. It does not by itself revoke real authority. |
| `zero_neutral` | Role operations, credential issuance, handovers, and ordinary restriction changes are blocked. Recovery and reconciliation are separate administrator-gated actions. |

An authorized emergency neutralization invalidates previously issued role credentials. Returning to `normal` does not make them usable again.

## Restart and checkpoint rules

| Checkpoint on startup | What happens |
|---|---|
| Valid `clean` record | Load the confirmed restrictions and stay in `zero_neutral` until the current startup is approved. |
| Valid `pending` record | Stay neutral and require `reconcile_checkpoint()`. Do not resume or roll back the interrupted operation. |
| Missing, unreadable, corrupt, or incompatible record | Stay neutral. Do not assume an empty restriction set or use an older backup automatically. A missing or corrupt record can be rebuilt from an independently reviewed baseline by an administrator. |

Before changing a role assignment or restriction, the axis writes a `pending` checkpoint and confirms it by reading it back. It then applies the change under its serialized command boundary and confirms a final `clean` checkpoint before returning success. If the final write cannot be confirmed, the running axis stays or enters neutral and does not publish a new credential or lift a restriction.

Reconciliation abandons an interrupted handover. It retains restrictions that were active before the interruption, keeps a pending activation, and does not apply a pending release. Reconciliation itself never grants recovery approval. A valid `clean` record found on a later startup can establish the saved restrictions, but it cannot establish that the previous caller saw success or make prior authority usable.

## Repository map

| File | Purpose |
|---|---|
| [`axis.py`](axis.py) | Versioned axis implementations, including `TransitionAxisV5`. Older APIs are retained for regression and comparison. |
| [`evidence.py`](evidence.py) and [`five_elements.py`](five_elements.py) | Evidence verification and cross-role restriction rules. |
| [`feedback.py`](feedback.py) and [`role_rotation.py`](role_rotation.py) | Hysteresis-based load control and same-role credential handover. |
| [`checkpoint.py`](checkpoint.py) | Versioned local checkpoint storage, readback, and conservative reconciliation. |
| [`tests/`](tests/) and [`validate.yml`](.github/workflows/validate.yml) | Regression and integration tests, plus the GitHub Actions workflow. |
| [`CHANGELOG.md`](CHANGELOG.md) | Release changes and validation scope. |

Specifications: [v0.2 — Evidence and five-element rules](specs/vrta-v0.2.md) · [v0.3 — Load feedback](specs/vrta-v0.3.md) · [v0.4 — Role handover](specs/vrta-v0.4.md) · [v0.5 — Restart recovery](specs/vrta-v0.5.md).

## What each version added

| Version | Boundary made testable |
|---|---|
| v0.1 | Separate virtual observation from permitted real operations. Invalidate earlier authority on neutralization. |
| v0.2 | Bind evidence receipts to accepted events and enforce the five-element restriction matrix. |
| v0.3 | Use load feedback and hysteresis to govern transitions between normal and degraded operation. |
| v0.4 | Rotate a holder within the same role, revoking the outgoing authority before publishing its replacement. |
| v0.5 | Preserve confirmed restrictions across a restart. Require fresh approval and credentials before operations resume. |

## Validation

GitHub Actions runs **143 tests per Python version** on Python **3.11, 3.12, and 3.13**. The suite contains 118 v0.4 baseline tests, 14 checkpoint tests, and 11 restart-recovery tests. CI also runs syntax checks, legacy simulation checks, and the v0.3 integration smoke test.

The restart suite exits a child process just after revoking an outgoing credential. A fresh process opens the same checkpoint and verifies that it stays neutral with a pending handover and cannot recover before reconciliation.

## Scope and limitations

VRTA is a behavioral prototype, not a production security control. Its roles share one Python interpreter. Credentials are not cryptographically authenticated, source verification does not establish real-world provenance, and the recovery flags do not authenticate a person. Checkpoint checksums and the in-memory audit chain show internal consistency, not tamper resistance or durable audit storage.

v0.5 models one axis process and one writer using local storage. Power-loss durability, concurrent writers, distributed recovery, and protection against deliberate checkpoint replacement or rollback are outside the validated scope.
