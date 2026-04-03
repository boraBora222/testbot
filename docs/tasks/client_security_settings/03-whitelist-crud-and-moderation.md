# Task: Whitelist CRUD and Moderation

- Objective: Implement the full whitelist lifecycle for clients and managers, including CRUD rules, moderation states, and admin actions.
- Owner: Dev
- Dependencies: `01-domain-models-and-validation.md`, [Client security settings specification](../../specifications/client_security_settings.md)
- Success Criteria:
  - Client endpoints exist for list, create, rename, and delete of whitelist addresses.
  - New whitelist entries always start in `pending`.
  - Admin flows support approve and reject, with a required reason on reject.
  - The 5-address cap for `pending + active` is enforced consistently.
  - Rejected addresses cannot be resubmitted through UI or API.

## Steps

1. Implement the client whitelist read and create flows.
```text
- Add `GET /api/profile/whitelist` for the current user's whitelist entries.
- Add `POST /api/profile/whitelist` to create a new `pending` address.
- Normalize address identity per network before uniqueness checks.
```

2. Implement limited client-side edits.
```text
- Add `PUT /api/profile/whitelist/{id}` for `label` updates only.
- Keep address value and network immutable after submission.
- Reject updates that attempt to bypass moderation semantics.
```

3. Implement safe deletion rules.
```text
- Add `DELETE /api/profile/whitelist/{id}` with the rule that an address cannot be deleted
  when it is used by an active order.
- Keep delete semantics explicit instead of silently detaching historical order references.
```

4. Implement admin moderation surfaces.
```text
- Add a pending-address moderation page in `web/routers/users.py`.
- Add approve and reject actions for whitelist entries.
- Require a rejection reason and persist moderator identity and decision timestamp.
```

5. Enforce lifecycle constraints across all entry points.
```text
- Enforce the maximum of 5 addresses in `pending` and `active` combined.
- Reject duplicate active/pending entries for the same normalized address.
- Reject re-submission of a previously rejected address for the same user and network.
- Keep the state machine limited to `pending`, `active`, and `rejected`.
```

## Validation

- Confirm section `5.1` client whitelist endpoints and section `5.2` admin moderation routes are fully covered.
- Confirm moderation metadata is sufficient for admin accountability and later order linkage.
- Confirm no flow allows the user to turn manual address entry into a whitelist bypass.
