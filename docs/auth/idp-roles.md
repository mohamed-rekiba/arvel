# Mapping IdP groups to roles

If you've used HashiCorp Vault with Keycloak, you already know this pattern. You don't re-create users
in Vault — you create **external groups** that mirror the IdP's groups, attach policies to them, and at
login Vault reads the token's group claim, matches the groups, and grants the matching policies. The
identity provider owns *who is in a group*; Vault owns *what a group can do*.

arvel works the same way, with one deliberate simplification: it already has a thing that "owns what a
group can do" — a [`Role`](authorization.md). So there is **no separate "IdP group" entity** to manage.
An IdP group is just an external *string* that gets **translated** into arvel roles at the door. That
keeps a single authorization vocabulary (`Role`/`Permission`) and mirrors exactly how the [identity
side](identities.md) translates a `sub` into a `User`: the IdP's vocabulary never enters arvel's model
— it's converted at the boundary.

This page covers the translation, wiring it into login, and the safety rules.

## The translation

`roles_for_claims` maps the **values** in a claim to arvel role names, using a mapping you control:

```python
from arvel.auth.claim_map import roles_for_claims

mapping = {
    "/eng/backend": "developer",
    "/ops":         "operator",
    "/leads":       ["developer", "team-lead"],   # one group → several roles
}

claims = {"groups": ["/eng/backend", "/ops"]}
roles_for_claims(claims, mapping)                 # {"developer", "operator"}
```

A claim value that isn't in your mapping grants **nothing** — there is no "group `admins` magically
becomes role `admins`" guessing. You decide every mapping explicitly.

### Source-agnostic

Keycloak might send access under `groups`, or `realm_access.roles`, or a client-roles path. Point
`claim_paths` at wherever your realm puts it (dotted paths are dug out of nested claims):

```python
claims = {"realm_access": {"roles": ["admins", "viewers"]}}
roles_for_claims(claims, {"admins": "admin", "viewers": "viewer"},
                 claim_paths=("realm_access.roles",))      # {"admin", "viewer"}
```

## Wiring it into login

After the [OIDC guard](sso-oidc.md) validates the token and the [user provider](identities.md)
resolves the `User`, translate the claims and attach the resulting roles to the user for this request:

```python
principal = await guard.verify(request)            # validated OIDC token → Principal
user = await users.resolve(principal)              # sub → User

roles = roles_for_claims(principal.claims, mapping) # {"developer", ...}
user.set_idp_roles(roles)                          # carried for this request — NOT persisted

await user.has_role("developer")                   # True (from the IdP)
await user.has_permission_to("posts.publish")      # True if the "developer" role grants it
```

`set_idp_roles` **unions** these roles with the user's persisted direct grants — it never replaces or
revokes them. A user who is a locally-assigned `editor` *and* arrives in the IdP's `/leads` group has
both sets of permissions.

## Common mistakes & gotchas

- **Expecting auto-mapping by name.** There's none, by design. An unmapped group value grants nothing
  — map it explicitly or it does nothing. (A coincidental name match across two systems you don't
  jointly control is exactly how privilege leaks happen.)
- **Thinking IdP roles are persisted.** They aren't. `set_idp_roles` carries them for the current
  request only; nothing is written to `model_has_roles`. That's *why* they can't collide with or
  overwrite local grants — they simply union at check time.
- **Forgetting the staleness window.** Because roles are resolved at login and carried in the
  session/token, removing someone from a Keycloak group takes effect on their **next login/refresh**,
  not instantly. Keep token TTLs short if fast revocation matters.
- **Mapping a group to a role that holds `*` or a broad `prefix.*`.** That hands the identity provider
  the ability to confer wide power. The claim→role map is a **privilege-escalation control surface** —
  vet which mapped roles carry [wildcards](authorization.md), and lean on short TTLs the broader the
  reachable grants.

## How it works

This is the Vault model applied to arvel: **resolve at login, carry, union — never persist.** At login
you translate the token's claim values to role names (`roles_for_claims`, source-agnostic, unknown →
nothing) and call `set_idp_roles`, which stashes the set on the user instance and flushes the
permission cache. From then on, `has_role` returns `True` for any carried role, and the effective
permission set unions the permissions of the carried roles (looked up by name in `role_has_permissions`)
with the user's persisted direct and via-role grants. Because membership is never written, there's
nothing to revoke and nothing to collide with — the IdP is the source of truth for *this token's*
lifetime, and the next login re-resolves from scratch.

## See also

- [Authorization: roles & permissions](authorization.md) — what the mapped roles actually grant.
- [Single sign-on (OIDC / Keycloak)](sso-oidc.md) — where the `groups` claim comes from.
- [Identities & account linking](identities.md) — the *identity* translation seam this mirrors.
