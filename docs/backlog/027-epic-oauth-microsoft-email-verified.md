# Epic: Microsoft OAuth logins default to unverified email

## Summary
The account linker auto-attaches a provider identity to an existing local user
only when the email is verified — a deliberate guard against takeover via an
unproven email. The Microsoft provider broke that guard by defaulting
`email_verified` to true whenever any email was present, even though Entra omits
the claim and its email isn't guaranteed verified. Microsoft logins must default
to unverified so they can't auto-link by email.

**Module:** arvel-oauth · **Spec:** `docs/pipeline/specs/WI-arvel-027-oauth-microsoft-email-verified.md`

## Stories

### Story 1: Microsoft logins don't claim a verified email by default
**As a** developer using Microsoft/Entra social login, **I want** a login whose
userinfo omits `email_verified` to be treated as unverified, **so that** an
attacker can't link into another user's account by presenting a matching but
unproven email.

**Acceptance Criteria**:
- [ ] Given Microsoft userinfo without an `email_verified` claim, when identity is resolved, then `OAuthUser.email_verified` is `False`.
- [ ] Given an explicit `email_verified: true` claim, then `OAuthUser.email_verified` is `True`.
- [ ] Given an unverified Microsoft email matching an existing user, when linking, then a new user is created (synthetic `{provider_id}@microsoft.local`) rather than attaching to the existing row.

**Security Requirements**:
- [ ] The Microsoft default matches Google/OIDC and the `OAuthUser` default (unverified unless the upstream claim is explicitly true). A07/A01.

**Documentation Requirements**:
- [ ] `docs/site/docs/packages/oauth.md` documents the linker's email-verification contract and Microsoft's conservative default.

**Requirement Refs**: C1
**Priority**: Must · **Complexity**: Small · **Status**: Done
