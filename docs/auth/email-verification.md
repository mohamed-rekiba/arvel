# Email Verification

Many applications require users to verify their email address before using the app. arvel provides the
building blocks — a verified flag on the user, an event, and a route middleware — and lets you wire the
notification and routes to fit your app.

## Introduction

Verification state lives on the user as an `email_verified_at` timestamp. The `Authenticatable` base
gives you everything to read and change it:

```python
user.has_verified_email()          # True when email_verified_at is set (truthy)
await user.mark_email_as_verified()   # stamp it now + persist; fires EmailVerified once
await user.mark_email_as_unverified() # clear it (e.g. after an email change)
user.email_for_verification()      # the address a link should be sent to
```

The first transition to verified dispatches the `EmailVerified` event, so you can react (send a
welcome email, provision resources) with a listener — see [Events](../events.md).

## Protecting routes

Apply the **`verified`** middleware to any route that must not be reached by an unverified user. A
guest gets **401**; a signed-in but unverified user gets **403**:

```python
Route.get("/dashboard", dashboard).middleware(["auth", "verified"])
```

Because it runs after `auth`, always pair the two — `verified` reads the authenticated user the
`auth` middleware resolved.

## The verification flow

arvel doesn't prescribe how the link is delivered — you own the notification and routes, typically
built on a [signed URL](../urls.md) so the link is tamper-evident and expiring:

1. **Send the link.** After registration, mail the user a `temporary_signed_route(...)` pointing at
   your verify route, keyed to their id.
2. **Verify on click.** Protect the verify route with the `signed` middleware, then mark the user:

   ```python
   from arvel.http.middleware import ValidateSignature

   async def verify(request, user_id: int):
       user = await User.find(user_id)
       if user is None:
           abort(404)
       await user.mark_email_as_verified()
       return redirect("/dashboard")

   Route.get("/email/verify/{user_id}", verify, name="verification.verify") \
       .middleware(ValidateSignature)
   ```

3. **Resend.** Expose a small authenticated route that re-issues the signed link on demand.

Because the link is a signed URL, no verification token needs to be stored — the signature (and its
`expires`) is the proof.

## See also

- [URL Generation](../urls.md) — `temporary_signed_route()` for the verification link.
- [Authentication](authentication.md) — the `auth` middleware `verified` builds on.
- [Events](../events.md) — reacting to `EmailVerified`.
