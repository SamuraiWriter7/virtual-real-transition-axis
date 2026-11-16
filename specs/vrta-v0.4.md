# Virtual–Real Transition Axis v0.4

## Safe Role Rotation and Fault Injection

**Status:** Experimental specification  
**Baseline:** VRTA v0.3  
**Runtime:** Python 3.11+ · Standard library only

### 1. Scope

v0.4 models an administrator-requested handover of one existing domain role, `virtual` or `real`, to a new holder of that same role. It does not rotate five-element roles or let load observations trigger a handover.

The reference model runs in one Python process. Fault injection simulates exceptions in a running process. Restart recovery, distributed coordination, cryptographic identity, and durable audit storage are out of scope.

**Normative terms.** MUST and MUST NOT indicate requirements.

### 2. Authority model

- A v0.4 axis MUST maintain at most one current credential per domain role. Initial and post-recovery assignment MUST require the administrative capability. No inherited issuance path exposed through the v0.4 API may create a second current credential or bypass the handover gate.
- The administrator MUST explicitly request rotation. A request identifies the rotation ID, role, expected current credential ID, new credential ID, and a nonblank reason. The old credential MUST match the current binding in the current generation. The new ID MUST NOT have been issued or reserved before on that axis.
- The axis MUST generate the new credential itself. A credential ID is not proof of authority. The local reference model MUST require the axis-issued credential object, or equivalent locally bound capability, in addition to the current role binding and generation.
- Deployment code MUST use the v0.4 interface for the v0.4 instance. Older classes may remain for regression tests, but their compatibility paths MUST NOT be exposed as alternate interfaces to that instance.

### 3. Handover protocol

| Phase | Old credential | New credential | Required behavior |
|---|---|---|---|
| Preflight | Unchanged | Unusable | Check administrator, mode, request, current binding, and new ID. |
| Cutting over | Revoked or blocked | Unusable | Close the role gate, permanently revoke the old credential, and stage the replacement. |
| Committed | Revoked | Current | After the completion record is accepted, publish the replacement and reopen the gate as one observable step. |
| Failed after cutover begins | Unusable | Unusable | Enter `zero_neutral`, invalidate the generation, and report failure. |

1. Preflight MUST reject unknown or wrong-role credentials, reused rotation IDs, unavailable audit, and requests in `zero_neutral`. Preflight rejection MUST NOT change the current binding, generation, operating mode, or restrictions. A rotation ID is consumed when cutover begins and cannot be retried on the same axis.
2. The axis MUST serialize the handover with authority checks and state-changing operations. Closing the role gate marks the start of cutover. A staged credential MUST NOT authorize operations or be returned to the caller before commit.
3. A normal commit MUST revoke only the outgoing credential. It MUST NOT change the authority generation, the other role's binding, evidence or receipt records, feedback state, degradation causes, or five-element restrictions. The replacement has exactly the original role's permissions and remains subject to all current checks.
4. After completion logging succeeds, publication MUST be a local commit with no intervening fallible callback. No successful return is allowed before publication. The reference model covers synchronous, serialized calls only and does not claim to cancel external work already in progress.

### 4. Failure and recovery

- Any handled failure after cutover begins, including an unconfirmed completion append, MUST prevent publication. The axis MUST discard the staged credential and enter emergency neutralization without depending on audit availability. It MUST invalidate prior domain and element credentials and prior-generation receipts. It MUST NOT reactivate the outgoing credential or retry automatically.
- If a completion append raises after writing, the record alone MUST NOT be treated as proof of publication. The authoritative outcome in the running process is the axis state.
- Low load MUST NOT exit `zero_neutral`. Recovery after a failed handover MUST be explicit and administrator-gated, require positive simulated safety verification and human approval, and require an available, internally consistent audit path. If the failure could not be logged, the axis MUST record a reconciliation event before allowing recovery. Failed reconciliation MUST leave the axis neutral.
- Recovery MUST preserve active five-element restrictions. It MUST NOT restore old bindings, staged credentials, or stale receipts. A later administrative assignment MUST issue fresh credentials. Simulated approval does not authenticate a human approver.

### 5. Audit and deterministic fault injection

The axis MUST record the cutover start and successful completion and SHOULD record rejected requests and failed handovers when audit is available. Records include the rotation ID, role, non-secret credential IDs, generation, phase, and outcome or reason code. A failure to append MUST NOT be reported as a successful audit write. The in-memory hash chain checks internal consistency only.

Test fixtures MUST be able to inject a controlled exception immediately after old-credential revocation and at completion logging. The completion-logging tests MUST cover both interruption before append and an unconfirmed result after append. Fault injection is a local test facility, not a role-level API.

### 6. Release acceptance

| ID | Required test and expected result |
|---|---|
| ROT-01 | Authorized handover for each domain role. The old credential is rejected, the replacement is accepted for its original role, and the other role and generation are unchanged. |
| ROT-02 | Unauthorized, stale, wrong-role, duplicate-ID, unavailable-audit, and neutral-mode requests are rejected in preflight without mutating authority or mode. |
| ROT-03 | Observe the cutover boundary. Neither credential can authorize an operation before commit. Ordinary issuance cannot create a second current credential. |
| ROT-04 | Inject failure immediately after revocation. Both holders are blocked, the generation is invalidated, and low-load windows leave the axis neutral. |
| ROT-05 | Interrupt completion logging before append and after append but before confirmation. Neither case publishes the new credential or returns success. |
| ROT-06 | Deny recovery while audit is unavailable or reconciliation fails. Successful explicit recovery preserves restrictions and rejects stale role tokens, element tokens, and receipts. |
| ROT-07 | A new real holder still needs a valid receipt and cannot bypass analysis suspension. Rotation does not revalidate a stale receipt or clear an existing restriction. |
| ROT-08 | Feedback recovery leaves event-count degradation in place. Resetting the event-count window leaves feedback degradation in place. |

All applicable v0.1–v0.3 tests and the v0.4 acceptance tests MUST pass before release. The v0.3 CI baseline comprises 105 unit and regression tests plus a separate integration smoke test. These checks establish behavior in the tested model, not crash durability or production security.

> A handover may leave the role vacant for a moment. It must never leave the role with two valid holders.
