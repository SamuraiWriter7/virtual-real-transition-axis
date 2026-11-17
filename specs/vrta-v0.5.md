# Virtual–Real Transition Axis v0.5

## Restart Recovery and Authority Invalidation

**Status:** Experimental specification  
**Baseline:** VRTA v0.4  
**Runtime:** Python 3.11+ · Standard library only

### 1. Scope

v0.5 models the restart of one axis process using one local checkpoint store and one writer. It preserves restrictions across restarts without restoring operational authority. It covers ordinary process termination and controlled process stops at defined checkpoints.

Distributed handover, concurrent writers, power-loss durability, deliberate checkpoint rollback or tampering, and real-world approver authentication are out of scope. MUST and MUST NOT indicate requirements.

### 2. Startup and authority

- Every startup MUST begin in `zero_neutral`, before loading saved state. Neither low load nor approval from a previous run may exit that mode.
- A restart MUST NOT restore domain credentials, five-element tokens, evidence receipts, accepted events, or previously granted approvals. Credentials and receipt references MUST be scoped to the current startup and rejected if taken from a prior startup, even if a local counter or human-readable ID matches. Within a run, v0.4 generation checks still apply.
- While neutral, the axis MUST reject virtual intake, evidence verification, real operations, credential issuance, role handover, and ordinary restriction changes. Recovery and reconciliation use a separate administrator-gated path.
- After recovery, the administrator MAY issue fresh credentials. Real operations still require newly verified evidence and a current receipt. Restored five-element restrictions still apply.

### 3. Local checkpoint

The checkpoint MUST carry a schema version, a configured store identity, a revision, the last confirmed active restriction set, and a phase. A `pending` checkpoint MUST also identify the operation, its kind, and its affected role or restriction. It MUST NOT contain reusable credentials, receipts, evidence payloads, or approval capabilities.

| Checkpoint read at startup | Required behavior |
|---|---|
| Valid `clean` | Load the recorded restrictions. Remain neutral pending explicit recovery. |
| Valid `pending` | Preserve known restrictions and block recovery pending reconciliation. Do not complete or undo the interrupted operation automatically. |
| Missing, unreadable, malformed, inconsistent, or unsupported | Report the condition and remain neutral. Do not substitute an empty restriction set or silently fall back to an older checkpoint. |

The axis MUST verify schema, store identity, and record integrity before relying on a checkpoint. A checksum can detect accidental corruption but does not prove freshness or authenticity. Initial provisioning MUST be an explicit administrative operation for a new store with a declared restriction set, not a fallback for a missing checkpoint. Provisioning does not exit neutral mode.

### 4. Checkpoint ordering

1. Validate the request before writing a `pending` checkpoint. Retain the last confirmed restrictions in that checkpoint. Confirm the write before revoking an old credential, activating a restriction, or releasing a restriction. If the write fails, do not begin the operation. If the authoritative checkpoint is uncertain, enter `zero_neutral`.
2. Run the operation under the axis's serialized command boundary. For a handover, keep the v0.4 sequence of old-credential revocation before replacement, and retain the v0.4 audit requirements.
3. After successful processing, write and confirm a `clean` checkpoint with the resulting restrictions and no pending operation. The checkpoint write MUST replace the record as a unit. Confirmation requires a successful write and readback of the intended record.
4. Only then may the axis return success, allow a replacement credential to authorize public operations, or expose a restriction release. If completion cannot be confirmed, the axis MUST stay or enter `zero_neutral` without depending on audit availability. It MUST NOT return the staged credential or retry automatically.

On restart, a valid `clean` checkpoint may establish the recorded restrictions. It does not establish that the previous caller saw success, and it never authorizes publication of credentials from the previous run. An audit completion entry alone cannot resolve a `pending` checkpoint.

### 5. Reconciliation and recovery

Reconciliation MUST be explicit, administrator-gated, and performed while neutral. For an interrupted handover, record it as abandoned on restart and do not restore either holder. For an interrupted restriction activation, retain the previously confirmed restrictions and include the pending activation. For an interrupted release, retain the restriction that was to be released. Reconciliation MUST NOT silently loosen a restriction.

If the checkpoint is missing or unusable, recovery MUST remain blocked until an administrator supplies a reviewed replacement baseline from independent records. If that baseline cannot be established, the axis stays neutral. Record the reason, the checkpoint revision or failure condition, and the resolved restriction set. Confirm the reconciliation audit entry before publishing the replacement `clean` checkpoint. The replacement MUST retain a non-authorizing reference to the confirmed reconciliation decision. A stop before the replacement is published leaves reconciliation unresolved on restart, even if an audit entry was written.

Exiting neutral mode requires all of the following:

- An administrator explicitly requests recovery for the current startup and confirmed checkpoint revision.
- A valid `clean` checkpoint is confirmed and no reconciliation is outstanding.
- The modeled independent safety check and the modeled human approval are both positive for this startup and revision.
- The axis records and confirms the recovery decision through the available audit path before entering `normal`.

Any failed check or unconfirmed write leaves the axis neutral. Recovery restores neither old authority nor previously received evidence. Simulated approval does not authenticate a human approver.

### 6. Release acceptance

| ID | Required test and expected result |
|---|---|
| RST-01 | After a clean stop and restart, the axis starts neutral and retains confirmed restrictions. Fresh approval is required. |
| RST-02 | Stop a child process immediately after old-credential revocation. The next process finds `pending`, does not resume or roll back the handover, and denies recovery until reconciliation. |
| RST-03 | Reject missing, unreadable, corrupt, and inconsistent checkpoints without automatic provisioning or an empty restriction fallback. |
| RST-04 | Fail the pre-operation checkpoint write. No revocation or restriction change begins. Fail or withhold confirmation of the final write. No success, new credential, or restriction release is exposed. |
| RST-05 | Interrupt restriction activation and release separately. Reconciliation retains the pending activation and does not apply the pending release. |
| RST-06 | Reject prior-startup credentials, element tokens, receipt references, and approvals even when local identifiers repeat. A newly issued credential with a newly verified receipt remains subject to restored restrictions. |
| RST-07 | Deny recovery on missing approval, failed reconciliation, unavailable audit, or a changed checkpoint revision. Passing all recovery checks permits normal mode but does not issue credentials. |

At least one stop test MUST terminate a subprocess without normal cleanup and reopen the same store in a fresh process. In-process exceptions alone do not satisfy this requirement. The 118 v0.4 tests and applicable smoke checks remain the regression baseline. Passing this suite does not establish power-loss durability or production security.
