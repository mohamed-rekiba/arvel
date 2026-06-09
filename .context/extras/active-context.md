# Active Context

## Current Focus

Driving the `kits/arvel-ecommerce-kit` demo to completion via the autonomous
review → implement → document → design loop. The kit stress-tests the Arvel
framework, so gaps it exposes are real framework/demo work.

## Key Decisions

- **Run kit tests via the workspace, not the `demo-*` containers.** The running
  Docker stack mounts a stale checkout (`/Users/.../temp/test/demo`), so its
  results are misleading. Correct command:
  `uv run --project kits/arvel-ecommerce-kit/backend pytest kits/arvel-ecommerce-kit/backend/tests/...`
- **A01 privilege-escalation guard belongs in the controller, mirroring
  `assign_role`'s `>=` convention.** Peer rank is allowed; acting on a user who
  outranks you raises `AuthorizationException`.
- **Don't fabricate UI data.** Backend returns `rating`/`rating_count` as `null`
  (no reviews feature). Frontend now hides the rating UI instead of faking
  `4.2`/`73`. Analytics/Settings render an honest "coming soon" instead of the
  translations table.
- **Defer the full Orval-only consolidation.** `lib/api.ts` is pinned by the
  `test_047` frontend-shell contract test (`listAdminRows(`, `getAdminUser(`,
  `runAdminUserAction(`, ...). Removing the dual layer requires rewriting that
  contract test — a dedicated iteration, not a surgical batch.
- **CHANGELOG.md is Release-Please-generated** (commit-linked) — never hand-edit.
- **`docs/` trees are mid-reorganization** (`docs_dir: docs/site`, plus untracked
  `docs/kits` and `docs/docs`). Avoid editing until the layout settles; no
  published doc claim is contradicted by this iteration.

## Changes This Iteration

Backend (`kits/arvel-ecommerce-kit/backend`):
- `app/http/controllers/_deps.py` — added `highest_role_level(user)`.
- `app/http/controllers/admin/users.py` — `_assert_outranks` guard wired into
  `destroy`, `force_destroy`, `suspend`, `unsuspend`, `restore` (OWASP A01).
- `pyproject.toml` — self-contained `[tool.pytest.ini_options]` (`asyncio_mode`,
  markers) so a standalone `arvel new --kit ecommerce` runs the async security
  tests correctly.
- `tests/unit/_framework_src.py` — new helper; `importlib.find_spec` resolves
  framework package sources, replacing brittle `parents[5]` in
  `test_054/055/056`.
- `tests/unit/test_057_authz_escalation_guard.py` — 6 new guard tests.
- Result: 356 unit tests pass, ruff clean.

Frontend (`kits/arvel-ecommerce-kit/frontend`):
- `pages/AdminListPage.vue` — "Show deleted" toggle now passes `trashed` and
  resets pagination.
- `pages/AdminPlaceholderPage.vue` + `router.ts` — Analytics/Settings/catch-all
  now use a `coming-soon` state; Translations passes `pageType: 'translations'`.
  Removed the stray `AdminUserDetailPage` redirect route.
- `components/storefront/ProductCard.vue`, `pages/StorefrontProductDetail.vue` —
  ratings render only when the backend supplies them (no more fake stars).
- `lib/api.ts` — removed dead `deactivateAdminUser` (posted to a nonexistent
  `/deactivate` route, zero references).
- `main.ts` — added `admin.placeholder.coming_soon` for en/ar/tr.
- `src/lib/i18n.test.ts`, `src/stores/cart.test.ts` — first Vitest tests
  (15 passing). Closes the "zero frontend tests" gap.
- Result: typecheck + lint + build clean, 15 vitest tests pass.

## Iteration 2 — Orval consolidation (admin user detail)

- `pages/AdminUserDetailPage.vue` is now fully Orval-driven. Removed the dead
  `void`-ed `lib/api.ts` handlers and migrated the one live call (force-delete)
  to `useAdminUsersForceDestroyApiAdminUsersUserIdForceDelete`, with toast +
  users-list invalidation + redirect to `/admin/users` on success.
- Deleted 8 now-dead hand-written admin-user helpers from `lib/api.ts`
  (`getAdminUser`, `assignAdminUserRole`, `revokeAdminUserRole`,
  `grantAdminUserPermission`, `revokeAdminUserPermission`, `runAdminUserAction`,
  `deleteAdminUser`, `forceDeleteAdminUser`). The Orval custom mutator and the
  auth/session/media helpers in `lib/api.ts` stay — they are not duplicates.
- Rewrote `test_047`'s user-detail test to assert Orval hook usage and the
  absence of the removed helpers.
- Added `admin.user.toast_force_deleted` / `force_delete_failed` (en/ar/tr).
- Verified: typecheck + lint + build clean, 15 vitest, 356 backend unit tests.

`listAdminRows` intentionally kept — it's a generic multi-resource admin fetch
used by `AdminDashboard` and `AdminListPage`, not a per-endpoint Orval duplicate.

## Iteration 3 — Test-endpoint hardening (security)

- `app/http/controllers/test.py` seed/refresh endpoints were allow-by-default
  (denied only `production`), so a reachable `development`/`staging` deployment
  exposed destructive reseed to anonymous callers. Switched to deny-by-default
  via `_guard_test_env()` with an allowlist of `{local, testing}`.
- `.env.example` is `APP_ENV=local` (local stack + tests keep working);
  `config/app.py` defaults to `production` when unset (denied). `make seed`
  uses the CLI, not these HTTP endpoints, so nothing else breaks.
- New `tests/unit/test_058_test_endpoints_guard.py` (10 tests) asserts the
  deny path for production/development/staging/unset and allow for local/testing.
- Result: 366 unit tests pass, ruff clean.

## Iteration 4 — Remove remaining fabricated UI data

- Admin dashboard StatCards dropped the hardcoded `:trend="12/8/5/3"` (no
  period-over-period data exists). `StatCard.trend` stays optional/reusable.
- Deleted the `FlashSale` "Deal of the Day" component: it invented 15-20%
  discounts (`price * 0.8/0.85`) and a countdown that reset every page load.
  No backend sale feature exists. Removed its usage in `StorefrontHome`, the
  component file, and the orphaned frontend `flash.*` i18n keys (en/ar/tr).
- `ProductCard` discount/strikethrough is now purely backend-driven: shows
  only when `product.original_price > product.price`. Removed the FlashSale-only
  `salePrice`/`originalPrice` override props and updated `specs/product-card.md`.
- Left backend `flash_sale.*` i18n catalogue keys + `test_042` alone — that's a
  forward-looking catalogue-completeness contract (pins `nav.analytics`/
  `nav.settings` placeholders too), separate from the frontend `flash.*` keys.
- Verified: typecheck + lint + build clean, 15 vitest, 366 backend unit tests.

## Iteration 5 — Design refresh (in progress)

User approved a full autonomous redesign (storefront + admin). The existing
design is already strong (OKLCH token system, violet/cyan framework brand, full
dark mode), so this is a cohesive refresh/polish — not a teardown. The framework
brand color stays.

Batch 1 (foundation, done): added Plus Jakarta Sans as the heading/display font
(Cairo trails for Arabic), refined the shadow scale to soft two-stop elevation
(light + dark), applied via token layer so it cascades app-wide. Verified build +
lint clean. The live docker stack at :8002 reflects it via Vite HMR.

Batch 2 (hero honesty, done): the wide home promo banner asserted a fake
"Get Up To 85% OFF on Big Billion Day" and the three `PromoBanners` carried
fabricated "Flat 10/15% OFF" eyebrows. No sale/discount backend feature exists,
so these were dishonest. Rewrote the banner copy to a single honest headline and
swapped the promo eyebrows to curation labels (Trending now / Fan favorites /
Editor's pick) across en/ar/tr; dropped the orphaned `home.big_sale_highlight`/
`home.big_sale_suffix` keys. Verified typecheck + lint + 15 vitest + build clean.

Next batches: product/listing polish, admin polish.

## Iteration 6 — Complete the A01 outrank guard (security)

Re-ran parallel review subagents. They confirmed the lifecycle mutators are
guarded but flagged that `assign_role`, `revoke_role`, `grant_permission`, and
`revoke_permission` skipped `_assert_outranks` — a level-80 actor that cleared
the actor-level/permission gate could still strip roles/perms from a level-100
target. Added `await _assert_outranks(actor, target)` to all four (after the
target + role/perm existence checks, before mutation). Added four blocking tests
to test_057 (target outranks actor → AuthorizationException). 370 backend unit
tests pass; ruff clean; users.py mypy-clean (the 19 mypy errors are pre-existing
in product_base/cart/services dependency files, untouched here).

## Iteration 7 — Hero honesty (frontend)

HeroBanner.vue hardcoded SAVE10 / 10% SALE / From $399.99 / strikethrough
$499.99 / 4.9 rating / 20% OFF, and the en/ar/tr `hero.subtitle` promised "free
shipping over $75" — all fabricated (no promo, sale, rating, or shipping feature
exists). Rewrote to honest editorial copy: kept the layout/blob/mockup, replaced
the title with "Tech that keeps up / with you", dropped the promo-code + price
lines, swapped the rating badge for a non-numeric "Curated picks" (verified
icon), and removed the price badge + discount pill. Pruned the dead hero keys
(sale_title, sale_accent, promo_hint, price_from, top_rated, discount) across
en/ar/tr and added hero.title_accent / hero.badge. Gates green.

## Iteration 8 — Real permission matrix (full-stack)

AdminPermissionsPage rendered a fake grant matrix: every role with level>=80 got
a ✓ on every permission, ignoring actual role_has_permissions. Made it real:
- Backend: RoleOut now carries `permissions: list[str]`; roles.index loads each
  role's `role.permissions.all()` (small fixed role set, N+1 is fine).
- Regenerated openapi.yaml + Orval client via `make api-generate` (stack was up).
  Note: openapi.yaml is gitignored, so the committed generated TS client had
  drifted from the live spec — regen (clean:true) also corrected that drift
  (dropped stale LoginRequest.remember, split storefront image sub-schemas).
- FE: matrix cell now checks `(role.permissions ?? []).includes(perm.name)`.
- Updated test_047 stale assertion (the removed dead `redirectTo` prop on
  /admin/login → assert the real `adminRedirect: true`). 370 backend + 15 vitest
  pass; lint/typecheck/build clean.

## Iteration 9 — Real dashboard aggregates (full-stack)

AdminDashboard summed only the first page (listAdminRows, no limit → backend's
default 50) for revenue/orders/customers/AOV/status breakdown — under-reports
once >50 orders exist. Added a DB-aggregated stats endpoint:
- Backend: OrderService.dashboard_stats (sum/count/COUNT(DISTINCT)/GROUP BY
  status, all soft-delete-scoped to live orders) + a 7-day revenue series
  (bounded window, bucketed in Python). New GET /api/admin/orders/stats
  (orders.view), DashboardStatsOut schema. Route ordered before /{order_id}.
- Regenerated Orval; AdminDashboard now uses useAdminOrdersStats... for KPIs +
  status, and useAdminOrdersIndex({limit:6}) for the recent-orders card only.
- RevenueBarChart now takes the server series instead of recomputing from a
  capped orders array.
- Verified live (superadmin token → 200) and with 2 new feature tests
  (test_admin_dashboard: orders.view enforcement + 7-point series shape),
  passing under the testcontainers harness. 370 unit + lint/typecheck/build green.

## Iteration 10 — Auth hydration + admin-access consistency (frontend)

Two real bugs:
- router.beforeEach and AdminLayout.onMounted called lib/api `loadCurrentUser()`,
  which fetched /api/auth/me but discarded the result — the Pinia store was never
  refreshed, so permissions stayed whatever localStorage held (stale grants
  survive a server-side role change until next login).
- router had its own hasAdminAccess() using broad prefixes (products./orders./
  users./roles.) while the store/nav use exact ADMIN_PERMISSIONS
  (products.view/orders.view/users.manage/roles.manage) — the guard and the nav
  could disagree about who's an admin.

Fix: both call sites now use auth.hydrate() (calls authMeApiAuthMeGet → persists
to the store) and the guard reuses auth.hasAdminAccess. Deleted the now-dead
lib/api auth block (loginUser, registerUser, fetchCurrentUser, loadCurrentUser,
MeResponse, AuthTokenResponse) — auth has gone through Orval store hooks for a
while. Updated test_047 (router + admin-shell + the two stale iteration-9
dashboard/auth-helper assertions that referenced removed code). 370 unit +
15 vitest + typecheck/lint/build green.

## Iteration 11 — Drop dead admin list helpers (frontend)

AdminListPage already read orders/users via the generated orval index hooks, but
onMounted still fired a lib/api `listAdminRows()` whose result was thrown away
(the comment literally said "Orval hooks handle actual data loading"). Removed
the dead onMounted + the orphaned `resource` computed, and deleted the now-unused
`listAdminRows`, `listAdminCatalog`, and `AdminListParams` from lib/api.ts.
Rewrote test_047's list-page contract to assert the real orval hooks and that
listAdminRows is gone. Gates green (16 contract tests, typecheck/lint/build).

## Iteration 12 — i18n the storefront listing/search copy (frontend)

StorefrontProducts and StorefrontSearch had hardcoded English in the template:
"{n} items", "Filter products…", "No products found", "Load more",
"{n} results for {q}", "Enter a search term above", "No products match your
search". Arabic/Turkish visitors saw English here. Added 7 keys (products.count,
products.filter_placeholder, products.none, products.load_more, search.count,
search.prompt, search.none) across en/ar/tr with {n}/{q} interpolation and wired
the templates. Gates green (typecheck/lint/15 vitest/build).

Note on product-card surface (deferred, not a bug): original_price, rating,
rating_count, is_new, is_bestseller are hardcoded None/False in
product_service/cart_service — they're spec'd (specs/product-card.md) but not yet
wired to data. They never render (guarded), so nothing fabricated. Wiring or
removing them is a design call, left for a human.

## Iteration 13 — Remove test-driven storefront prefetch (frontend)

StorefrontHome/Products/ProductDetail each fired a lib/api fetcher
(fetchProductList/fetchCategory/fetchProductBySlug) whose result was discarded —
the comment literally said "so the import is exercised; Orval query drives the
UI". The only thing keeping these alive was test_047 asserting the imports. Real
data already comes from the orval storefront hooks. Removed the dead calls +
imports, deleted the now-orphaned fetchProductList/fetchProductBySlug/
fetchCategory/searchProducts and ProductListResponse/StorefrontProduct types,
and rewrote the contract test to assert the orval hooks (and that the dead
fetchers are gone). 370 unit + 15 vitest + typecheck/lint/build green.

## Iteration 14 — Delete dead admin CRUD lib helpers (frontend)

Confirmed zero runtime + zero test consumers for createAdminCatalog,
updateAdminCatalog, deleteAdminCatalog, forceDeleteAdminCatalog,
getAdminCatalogRecord, getAdminOrder, updateAdminOrderStatus, and the
AdminCatalogResource type — catalog/order admin pages use the generated orval
mutation hooks. Removed them; kept AdminListResource (AdminListPage prop) and the
product-media helpers (AdminCatalogEditPage still uses those). No test changes
needed. typecheck/lint/build green.

## Iteration 15 — Delete dead cart/checkout lib helpers (frontend)

The cart store + StorefrontCart/Checkout/Account use generated orval hooks
(cartShow/cartItemsStore/Update/Destroy, checkoutApiCheckoutPost,
useAccountOrdersIndex…). The lib/api fetchCart/addCartItem/updateCartItem/
removeCartItem/checkout/fetchAccountOrders helpers + authorizedJson + the
CartResponse/CartItem/DetailResponse/OrderSummary types had no runtime consumers
— only test_047 propped them up. Removed them and rewrote the customer-pages
contract test to assert the real orval cart/checkout/account hooks. lib/api.ts is
now just the orval mutator (request), the json helper, session helpers, and the
product-media helpers. 370 unit + 15 vitest + typecheck/lint/build green.

Review backlog is clear of the actionable FE items found in this loop. Open,
deferred-to-human design calls remain noted above (product-card spec'd surface:
original_price/rating/is_new/is_bestseller wiring).

## Iteration 16 — Localize admin date/currency formatting (frontend)

Re-ran the parallel review. Triaged the 10 findings:
- #1 (admin trusts tampered localStorage): mitigated — `main.ts` awaits
  `auth.hydrate()` (the authoritative `/me`) before mount and overwrites stored
  perms; the store reads localStorage once at init, and the backend enforces 403.
  UI flash only, not exploitable.
- #2/#9 (cart snapshot vs live price): non-issue — cart shows live `product.price`
  and checkout charges live DB price (read at checkout); both match.
- #4 (KPIs mix soft-deleted orders): false positive — `Order.sum/count` apply the
  global soft-delete scope (verified in `arvel/database/query_mixin.py`).
- #3 (test reseed endpoints): accepted — `APP_ENV ∈ {local,testing}` gated, demo
  posture stands.
Real, in-theme fix shipped: `AdminListPage` and `AdminOrderDetailPage` hardcoded
`'en'` for `formatDate`/`formatCurrency` (and `pickLocalized` for the order-line
product name) while the rest of the app is locale-aware. Wired `currentLocale`
(`toSupportedLocale(locale.value)`) so admin dates/currency/product names follow
the chosen locale like the storefront. typecheck/lint/15 vitest/build + 16
contract tests green.

## Documentation audit (doc-agent pass)

Verified the doc surface before touching anything (accuracy-first, no fabrication):
- `make docs` green — link check "57 files, all resolve"; strict mkdocs build OK.
- Every `mkdocs.yml` nav page exists; kit README + published kit page accurate.
- All 4 component specs map to real components (`SalesBadge.vue` still exists;
  only `FlashSale` was removed and it never had a spec).
- STALE NOTE RETIRED: the "docs/ mid-reorg, avoid editing" caution is obsolete —
  `git status` shows `docs/` fully committed and clean. Site docs are editable.
- Undocumented in-flight code (not a doc deliverable): `AdminListPage.vue` +
  `AdminOrderDetailPage.vue` switched admin order date/currency from hardcoded
  `'en'` to the active locale (`toSupportedLocale(locale)`). Flag for the code loop.

No broken or stale published doc found — no doc rewrite was fabricated.

## Iteration 17 — Admin product PATCH returns 404, not 500 (backend)

`AdminProductsController.update` called `products.update(...)` directly. The
service raises `ProductNotFoundError` (a plain `Exception`, not an HTTP type) on a
missing product and does `uuid.UUID(product_id)` which throws `ValueError` on a
malformed id — both surfaced as 500s. `show`/`restore`/`publish` already guard
None → 404, and `categories`/`vendors` controllers fetch-then-guard. Mirrored that:
`update` now checks `products.admin_get(product_id, include_trashed=True)` (safe on
bad UUID and missing) and raises `NotFoundException` before mutating. Added
`test_update_missing_product_returns_404` to `test_admin_products.py`. 370 unit +
the targeted feature pair (missing→404, real update→200) green; ruff clean.

## Iteration 18 — Cart PATCH/DELETE on unknown item is 404, not silent 200 (backend)

`CartService.update_item`/`remove_item` wrapped the mutation in `if item is not
None:` and otherwise returned the cart unchanged with 200 — a stale/foreign item id
looked like success. `int(item_id)` also 500'd on a non-numeric id. Extracted
`_owned_item(cart_id, item_id)` that raises `NotFoundException` for a bad/foreign
id (mirrors the iteration-17 product fix). Added two feature tests
(update/remove unknown id → 404). Existing update/remove (→200) still pass; ruff
clean. Normal FE flows only touch items already in cart state, so no regression.

## Iteration 19 — Checkout self-loads the cart (frontend)

`StorefrontCheckout` rendered the review step purely from the in-memory cart store
and only called `requireStoredAccessToken()` on mount — it relied entirely on
boot-time `useCartStore().load()` ordering in `main.ts`. The sibling
`StorefrontCart` already self-loads (`void cart.load()` on mount). Added the same
to checkout so a direct load/refresh on `/checkout` populates the review reliably,
independent of boot order. typecheck/lint/15 vitest/build + 16 contract tests green.

Review triage recap (no code needed): #1 admin localStorage trust → mitigated by
boot `auth.hydrate()`; #2/#9 cart price → live price both sides; #4 KPIs → soft-delete
scoped; #3 test endpoints → APP_ENV-gated demo posture.

## Iteration 20 — Order line names snapshot in shopper's locale (backend)

`OrderService.checkout` froze each line's `product_name_snapshot` as
`published.name.get("en")` — Arabic/Turkish shoppers got English order history.
Threaded `locale` through `CheckoutController` (from `request.state.locale`,
Accept-Language) into `checkout(...)` and snapshot via
`TranslatableMixin.translate_dict(published.name or {}, locale)` (en fallback) —
same picker the storefront/cart use. Added a feature test (checkout with
Accept-Language: ar → order line name == Arabic catalog name) and updated the
stale source-text assertion in test_049 (was pinned to the old `name_data =`
line — exactly the #10 brittle-contract smell). 370 unit + targeted feature pair
(price snapshot, locale snapshot) green; ruff clean.

## Iteration 21 — Guard the /admin catch-all (frontend)

The `/admin/:pathMatch(.*)*` catch-all was a top-level sibling of the `/admin`
group, so it carried no `requiresAuth`/`requiresAdmin` meta — an unknown
`/admin/whatever` rendered the admin placeholder unguarded (and outside the admin
shell). Moved it to be the last child of the `/admin` group so it inherits the
guard and renders inside `AdminLayout`. Added a nesting assertion to test_047
(catch-all index falls after the group's `children: [`). Backend still serves the
SPA shell for it via the existing `/admin/{path:path}` web route. typecheck/lint/
build + 16 contract tests green.

## Iteration 22 — Fix broken self-service registration flow (frontend)

Fresh review (agent 5a1d597a) surfaced new items. Highest user-visible: the SPA's
`auth.register()` auto-called `login()`, but the framework rejects login while
`email_verified_at IS NULL` (auth_service.py:159 → 422 "Email not verified") and
register only queues a verification email. So every new storefront signup failed
at the auto-login step. Fixed honestly (keeps the framework's verify-email feature):
`register()` no longer auto-logs-in; `StorefrontAuth` now prefills the login email,
switches to the login tab, and shows an `auth.verify_sent` notice (added en/ar/tr).
The verify link (Mailpit in the demo) marks the user verified, then login works.
typecheck/lint/15 vitest/build + 16 contract tests green.

### Review backlog (iteration 22 findings, remaining)

- MED: `shipping_address: dict[str, Any]` accepts `{}`/garbage → typed model + 422. [done iter 25]
- MED: AdminUserDetailPage "Permissions" shows direct grants only, not effective
  (role-derived) perms — rename or expose effective set. [done iter 28]
- MED: force-delete button gated on `users.manage` but API needs role level 100 →
  non-superadmins get a 403 after clicking (need a level signal in MeOut). [done iter 27]
- MED #6: global 401 handler always routes to storefront `login`, even for /admin. [done iter 24]
- MED: `/account?order=...` shows "Order placed" with no verification. [done iter 26]
- LOW: WishlistButton is local-only (fake) [done iter 30 — now a real persisted guest wishlist];
  checkout delivery date hardcodes en-US [done iter 24];
  category parent_id allows self/cycle [done iter 29]; admin edit pages lack per-action gates [done iter 31].

Iteration-22 review backlog fully cleared (iters 23–31).

## Iteration 32 — Reject negative price/stock and malformed cart product id (backend)

Two contained input-validation fixes from the fresh review. MED: product
create/update accepted negative `price`/`stock_qty` via the API (UI used `min=0`
only) — added `Field(ge=0)` constraints to both payloads (422 on bad input). MED:
`add_item` called `uuid.UUID(product_id)` unguarded, so a non-UUID id 500'd —
now caught and raised as `NotFoundException` (404), matching `_owned_item`. Added
feature tests for both. 370 unit green; ruff clean.

### Review backlog (iteration 32 findings)

- HIGH: dashboard revenue/AOV/order-count include cancelled+pending orders
  (`order_service.dashboard_stats`), contradicting `best_sellers` (delivered-only).
- HIGH: cart/checkout UI totals use live `product.price` but checkout charges
  snapshot prices → mismatch after an admin price change (needs server totals on
  CartOut). Larger change; previously triaged as acceptable — revisit.
- MED: admin DELETE returns 204 for missing/ malformed ids (products/categories/
  vendors destroy) — should 404.
- MED: unpublished/removed cart line fails checkout as "Insufficient stock" not
  "item unavailable".
- MED: product create/update accepts negative price/stock via API (no Field bounds). [done iter 32]
- MED: coarse admin gate — `products.view` ⇒ full /admin shell (previously triaged).
- MED: malformed `product_id` on cart add → 500 (uuid.UUID ValueError unhandled). [done iter 32]
- MED: no admin UI for suspend/unsuspend or permission grant/revoke (APIs exist).
- LOW: post-checkout success banner never fires — checkout links to /account
  without `?order=` (the iter-26 banner is now dead code).
- LOW: "New Arrivals" not filtered to new; FeatureBadges assert unimplemented
  capabilities; media upload helpers bypass the 401 handler; test reseed has no
  auth even in local/testing (previously triaged as accepted).

## Iteration 23 — Serialize concurrent checkout (backend)

HIGH #1: checkout locked Product rows but not the cart, so two simultaneous
`POST /checkout` (or a double-click) could both read the same lines, create two
orders, and double-decrement stock. Added `CartService.lock_cart(user_id)`
(`SELECT … FOR UPDATE` on the cart row) and call it first in `OrderService.checkout`
(runs under the route's DB_TX). The second request blocks on the lock, then
re-reads the emptied cart and fails as EmptyCart (422). Added a feature test that
fires two checkouts via `asyncio.gather` and asserts exactly one 201 + one 422 and
a single order. 370 unit + targeted feature trio (concurrent, insufficient stock,
price snapshot) green; ruff clean.

## Iteration 24 — Admin 401 routing + checkout delivery-date locale (frontend)

Two small UX fixes. MED #6: the global 401 handler always pushed to the
storefront `login`, so an admin whose token expired lost the admin shell + the
post-login dashboard redirect — now routes to `admin-login` when the current
path is under `/admin`. LOW #9: checkout estimated-delivery date was hardcoded
`en-US` — now formats with the active locale like the rest of the page.
Committed `6931dee`, `3bccc96`. Frontend gates green.

## Iteration 25 — Type and validate the checkout shipping address (full-stack)

MED: `CheckoutPayload.shipping_address` was `dict[str, Any]` — checkout accepted
`{}` or any junk and persisted it, and the tests used an ad-hoc
`{line1, country_code}` shape that never matched what the UI writes/reads
(`{name, street, city, country}`). Added a `ShippingAddress` Pydantic model
(`extra="forbid"`, each field `min_length=1`, sane max lengths) and used it in
`CheckoutPayload`; controller passes `.model_dump()` to the service (storage
shape unchanged). Standardized all checkout test payloads on the canonical
shape. Regenerated `openapi.yaml` (gitignored) + the Orval client — the loose
`{ [key: string]: unknown }` is now a typed `ShippingAddress`. Added a feature
test asserting a missing-field address is a 422. 370 unit + 14 checkout feature
tests green; frontend typecheck/lint/vitest green; ruff clean.

Note: host `node_modules` was a partial install (missing transitive `dist`);
a `npm ci` into the (cleared) mount repaired it so `api:generate` runs locally.

## Iteration 26 — Account success banner only for owned orders (frontend)

MED: `/account` showed "Order placed" for any `?order=` value (`v-if="route.query.order"`),
so a hand-typed `/account?order=anything` faked a success state. Now resolves the
query param against the caller's loaded orders and only shows the banner when it
matches a real owned order. Typecheck/lint green.

## Iteration 27 — Gate force-delete on role level, not just permission (full-stack)

MED: the force-delete button was wrapped in `<PermissionGate permission="users.manage">`,
but `force_destroy` requires role level 100 (`require_role_level(..., 100)`). A
non-superadmin with `users.manage` (e.g. admin level 80) saw the button and got a
403 on click. Added `role_level` to `MeOut` (caller's highest role level via
`highest_role_level`), exposed `roleLevel`/`hasLevel(min)` on the auth store, and
gave `PermissionGate` an optional `minLevel` prop. Wrapped the force-delete button
in `<PermissionGate permission="users.manage" :min-level="100">` so only superadmins
see it. Regenerated the Orval client (only `meOut.ts` changed — pinned local orval
back to 8.15.0 to avoid a 132-file header churn from a stray 8.16.0). Added an
RBAC feature test asserting `/me` reports level 100 for super_admin, <100 for catalog.
370 unit green; ruff clean; frontend typecheck/lint/vitest green.

## Iteration 28 — Admin user detail shows effective permissions (backend)

MED: `_format_user` set both `permissions` and `direct_permissions` to the same
direct-only set, so the detail page's "Permissions" card showed a super_admin
(all perms via role, zero direct) as empty. Added an `effective` flag to
`_format_user`: detail responses (`get_user`, suspend/unsuspend/restore) now
resolve `get_all_permissions()` for `permissions`, while the N+1-sensitive list
keeps the cheap direct set (no per-user role expansion, no query-count regression).
`direct_permissions` still carries direct grants. Added an RBAC feature test
asserting super_admin's detail `permissions` includes `users.manage` and exceeds
`direct_permissions`. 370 unit green; ruff clean.

## Iteration 29 — Reject category self-parent and cycles (backend)

LOW: category `update` wrote `parent_id` unchecked, so a category could become its
own parent or form a cycle (breaks the tree, risks infinite walks). Added
`_assert_acyclic_parent`: rejects self-parenting and walks the proposed parent's
ancestor chain to catch cycles, raising `ValidationException` (422). `create` now
also rejects a non-existent parent. Added a feature test asserting self-parent is
a 422. 370 unit green; ruff clean.

## Iteration 30 — Real guest wishlist instead of a fake heart (frontend)

LOW: `WishlistButton` held per-instance `ref(false)` state — clicking toggled a
heart that reset on re-render and wasn't shared across cards (a fake affordance,
same class as the removed fake ratings). Replaced with a `useWishlistStore`
(Pinia) backed by localStorage: toggle/has/count, persists across navigation and
reloads, shared across all cards. Honest scope — guest-only, no account sync
(there's no backend wishlist). Added a vitest covering add/remove and rehydration.
Frontend typecheck/lint/vitest green (18 tests).

## Iteration 31 — Per-action gates on the admin catalog list (frontend)

LOW: the catalog list gated create/publish/delete but not Edit or Restore (both
hit `<resource>.update`), so a read-only support agent saw buttons that 403 on
click. Added an `updatePermission` computed and wrapped the Edit and Restore
buttons in `PermissionGate`. Order-detail (orders.update) and user-detail role/
grant/force-delete actions were already gated, so no change needed there. This
clears the iteration-22 review backlog. Frontend typecheck/lint/vitest green.

## Iteration 33 — Exclude cancelled orders from dashboard revenue (backend)

HIGH: `dashboard_stats` summed every order's `total` for revenue/AOV, while
`best_sellers` already counted delivered-only — so the KPIs disagreed and a
cancelled order (stock restored, row kept) still inflated earnings. Revenue and
AOV now sum over non-cancelled orders; `total_orders` stays the count of all
orders placed. Applied the same `status != "cancelled"` filter to the 7-day
revenue chart for consistency. New feature test
`test_cancelled_orders_excluded_from_revenue` places an order, asserts revenue
rises, cancels it, asserts revenue returns to baseline. Backend ruff clean;
dashboard + cart/checkout feature suites green (18 passed).

## Iteration 34 — Admin delete on unknown/malformed id is 404, not 204 (backend)

MED: `destroy`/`force_destroy` on products, vendors, and categories returned 204
even when the id didn't exist (or wasn't a UUID) — a silent no-op that hid typos
and broke REST semantics. Products blindly called `soft_delete`; vendors and
categories did `if found: delete` then 204 regardless. All three now guard with
the existing `admin_get`/`find` (both return None for missing *and* malformed
ids) and raise `NotFoundException`. Users already 404'd correctly (outrank guard
loads the target first) — no change. New tests: delete unknown product → 404,
malformed product id → 404, unknown category → 404. Backend ruff clean.

## Iteration 35 — Distinguish "unavailable" from "out of stock" at checkout (backend)

MED: checkout raised `InsufficientStockError` whenever a cart line's product
wasn't a visible catalog row — so unpublished/removed items reported "Insufficient
stock," which is wrong and confusing. Added `ProductUnavailableError`; the catalog
and locked-product lookups now raise it on `None` (gone from catalog / row
missing) and reserve `InsufficientStockError` for genuine low stock. The checkout
controller maps the new error to a 409 "A product in your cart is no longer
available." New test `test_checkout_fails_when_product_unpublished` unpublishes a
carted product and asserts the unavailable message; the existing out-of-stock
test still 409s. Backend ruff clean.

## Iteration 36 — Wire the post-checkout success banner (frontend)

LOW: iteration 26 made `StorefrontAccount` show a success banner only for an
order id in `?order=`, but the checkout confirmation's "View orders" link went to
`/account` with no query — so the banner was dead code. The link now carries
`{ path: '/account', query: { order: placedOrder.id } }` when an order was placed,
falling back to plain `/account` otherwise. Frontend typecheck + lint green.

## Iteration 37 — Cart shows charged (snapshot) prices, not live ones (full-stack)

HIGH: the cart/checkout UI multiplied the live `product.price` for line and cart
totals, but checkout charges `unit_price_snapshot` (price at add-time). After an
admin price change the displayed total disagreed with the charged total. Backend:
`CartItemOut` now exposes `unit_price` + `subtotal` (snapshot) and `CartOut`
exposes `total` (already computed server-side from snapshots); `_format_item`
populates them. Frontend: cart store `subtotal` reads `cart.total`; the cart page
and checkout review render `item.unit_price`/`item.subtotal` instead of
`product.price`. Regenerated the Orval client (also picked up the iter-32 `ge=0`
min on price/stock). Backend ruff + cart suite green (16); frontend
typecheck/lint/vitest(18)/build green. The live `product.price` still shows on
product cards/detail — only the cart reflects the locked-in price.

## Iteration 38 — Admin suspend/reinstate UI (frontend)

MED: the suspend/unsuspend APIs existed and were tested, but the user detail page
only showed a "Suspended" label with no way to act — admins had no UI to suspend
or reinstate. Wired the existing Orval `suspend`/`unsuspend` hooks into
`AdminUserDetailPage`: a `users.manage`-gated button in the header card that reads
"Reinstate" when `suspended_at` is set and "Suspend" otherwise, with optimistic
invalidation + toasts. Added en/ar/tr strings for the labels, toasts, and error.
Frontend typecheck/lint/vitest(18)/build green. Role assign/revoke and
force-delete were already wired; permission grant/revoke has no per-user API
(permissions derive from roles) so nothing to add there.

## Iteration 39 — Make is_new a real recency flag (backend)

LOW: `product_to_storefront` hardcoded `is_new=False`, so the "New" badge never
showed — a dead capability. It now derives from `created_at`: true within a
30-day window (`_NEW_WINDOW`), with a guard that treats a tz-naive `created_at`
as UTC so the subtraction never throws. `is_bestseller` stays honestly false —
the catalog view carries no order-count signal, and a fabricated badge violates
the no-fake-data rule; it waits for a real metric. New unit test
`test_059_is_new_window` covers recent → new, old → not new, and the naive-tz
path. `FeatureBadges` (1-click returns / app / 24-7) left as-is: generic
storefront marketing chrome, not data fabrication. Backend ruff clean; storefront
feature suite (11) + new unit tests green.

## Iteration 40 — Lock order row on cancel to stop double stock-restore (backend)

HIGH (fresh review): `update_status` read the order without a row lock, so two
concurrent cancels both passed the "not already cancelled" guard and each called
`_restore_stock_for_order`, double-crediting inventory. Now the order is fetched
`lock_for_update()` inside the request transaction; the second cancel blocks,
re-reads status as cancelled, and skips the restore. New integration test
`test_concurrent_cancel_restores_stock_once` places a qty-2 order and fires two
simultaneous cancels, asserting stock rises by exactly 2. Backend ruff clean.

## Iteration 41 — Catalog status enum, cart re-snapshot, force-delete UI gate

Three fresh-review fixes in one batch:
- MED: `add_item` now re-snapshots `unit_price_snapshot` to the current price when
  incrementing an existing line, so added units aren't billed at a stale first
  price (whole line moves to today's price). Test
  `test_duplicate_add_resnapshots_to_current_price`.
- MED: category/vendor `status` schemas now use `CatalogStatus =
  Literal["draft","published"]` instead of bare `str`, so a bad value is a 422 at
  the API, not a 500 from the DB. Regenerated Orval (status enum types). Test
  `test_create_category_rejects_invalid_status`.
- MED: admin catalog force-delete button now wrapped in `PermissionGate` with
  `:min-level="100"`, matching the backend `require_role_level(...,100)` so
  non-superadmins don't see an action that always 403s.
Backend ruff clean; frontend typecheck/lint/vitest(18)/build green.

## Iteration 42 — Reject malformed cursor; cap media upload size (backend)

Two hardening fixes:
- MED: `_list_published` no longer swallows `InvalidCursorError` and silently
  resets to page one — it now re-raises as `ValidationException` (422). Silent
  reset duplicated rows because the storefront appends pages. Updated the
  source-assertion unit test `test_storefront_list_rejects_malformed_cursor`
  (was pinning the old "fall back to page one" behavior) and added feature test
  `test_malformed_cursor_returns_422`.
- MED: product media upload now rejects files over `_MAX_IMAGE_BYTES` (5 MB)
  with a 400 before the body is read into storage, closing a memory-DoS gap.
  Test `test_upload_rejects_oversized_image`.
Backend ruff clean; targeted tests green.

## Iteration 43 — Manual catalog refresh uses unconditional helper (backend)

- MED: `ProductService.refresh_catalog` (admin "Refresh catalog" action) now
  calls `refresh_products_catalog_now()` instead of the lock-guarded
  `refresh_products_catalog()`. The locked variant returns `-1` when another
  process holds the Redis lock — a nonsensical `product_count: -1` for an admin
  who explicitly asked to refresh. The unconditional helper always runs;
  Postgres serializes concurrent `REFRESH ... CONCURRENTLY` on the same view.
  Updated source-assertion test `test_manual_refresh_uses_unconditional_helper`.
  The scheduler and write observers keep the lock-guarded variant (skipping a
  redundant refresh there is fine — the next tick catches up).

## Iteration 44 — Storefront filter searches the whole catalog (frontend)

- MED: `/products` filter box now hits the backend `/api/search` (which already
  existed, ORM full-text) instead of client-side filtering only the page
  already loaded. Below 2 chars (the backend minimum) it falls back to the
  normal paginated listing; at ≥2 chars it debounces 300 ms, drops stale
  responses via a sequence guard, and hides "Load more" (search returns a flat
  ranked set, not a cursor page). Skeleton/empty states track the active mode.
  Frontend typecheck/lint/vitest(18)/build green.

## Iteration 45 — Cart store errors go through i18n (frontend)

- LOW: extracted the vue-i18n instance into `lib/i18n-instance.ts` so non-setup
  code (Pinia stores) can translate via a `translate(key)` helper. `main.ts`
  now imports the shared instance and fills messages with `setLocaleMessage`
  instead of creating its own. Cart store fallback errors
  (`cart.error_load/add/update/remove`) now resolve through i18n with en/ar/tr
  keys, replacing the hardcoded English strings. Server `err.message` is still
  shown as-is, matching the admin-page pattern. typecheck/lint/vitest(18)/build green.

## Iteration 46 — Harden product media upload (backend)

- HIGH: media upload no longer reads the raw body unbounded. The old size check
  only fired when `file.size` was set (header-only); clients omitting
  Content-Length bypassed it and `attach_product_image` read the whole body into
  memory. Now the controller does `file.read(_MAX_IMAGE_BYTES + 1)` and rejects
  over-cap with 400; `attach_product_image(product, contents, filename)` takes
  pre-read bytes.
- MED: declared content-type is no longer trusted alone — `_sniff_image_type`
  checks magic bytes (JPEG/PNG/GIF/WebP) and rejects MIME-spoofed payloads.
  Aligned the allowed-types error message and upload-field description to include
  GIF. Tests: `test_upload_rejects_mime_spoofed_file`; updated `test_048` contract.

## Iteration 47 — Scope storefront search to category; gate short queries (frontend)

- MED: `/products` filter no longer leaks cross-category results. When a
  `?category=` is active, search results are scoped client-side by
  `category_slug`/`parent_category_slug` (both locale-resolved, same as the
  listing endpoint) — fixes the iteration-44 regression without a backend/Orval
  change.
- LOW: `StorefrontSearch.vue` no longer fires 1-char queries the backend 400s;
  gated on `MIN_QUERY_LENGTH = 2`, and the prompt/count states track it.
typecheck/lint/vitest(18)/build green.

## Iteration 48 — Cart PATCH re-snapshots price like add (backend)

- MED: `update_item` now re-snapshots `unit_price_snapshot` to the current
  catalog price, matching `add_item`. Before, a PATCH-based quantity change kept
  the stale first-add price, so checkout could charge an outdated amount after an
  admin price change. Test `test_update_quantity_resnapshots_to_current_price`.

## Iteration 49 — Graceful force-delete with dependent orders (full-stack)

- MED: force-deleting a sold product no longer 500s. `order_items.product_id`
  FK switched from `restrict_on_delete()` to `null_on_delete()` (the model and
  comments already assumed SET NULL); the line keeps `product_name` for history.
  `OrderItemOut.product_id` is now `str | None`, Orval regenerated to match.
- MED: force-deleting a user who has orders returns a clear 409 instead of a raw
  FK violation. `orders.user_id` is non-nullable with ON DELETE RESTRICT, so
  `UserService.force_delete` pre-checks `Order.with_trashed().count()` and raises
  `ConflictException`. Counts trashed orders too — soft-deleted rows still bind
  the FK.
- Tests: `test_force_delete_product_with_order_keeps_history`,
  `test_force_delete_user_with_orders_returns_409`. Frontend typecheck + ruff
  clean.

## Iteration 50 — Validate product category/vendor FK at the API (backend)

- MED: product create/update now verify `category_id`/`vendor_id` before the
  write. A missing-but-valid UUID used to hit the DB FK as an opaque 500; a
  non-UUID string used to ValueError on the cast (also 500). Both are now a
  clean 422 via `ProductService._resolve_category_id` / `_resolve_vendor_id`.
  Existence check is `with_trashed` to mirror the FK (a soft-deleted row still
  satisfies the constraint), matching the category-parent check.
- Tests: `test_create_product_rejects_unknown_category`,
  `test_create_product_rejects_malformed_category_id`,
  `test_update_product_rejects_unknown_vendor`.

## Iteration 51 — Translations endpoint needs both view grants (security)

- MED: `/api/admin/translations` returns product *and* category fields but was
  gated only on `categories.view`, leaking product translations to a
  category-only role. Now requires `products.view` AND `categories.view`.
- Test: `test_translations_requires_both_product_and_category_view` grants a
  customer only `categories.view` and asserts 403.

## Iteration 52 — Surface unavailable cart lines (full-stack)

- MED: a cart line whose product gets unpublished/soft-deleted/force-deleted
  used to render as a ghost — empty name, dead `/products/` link, qty steppers
  that 404, and a checkout button that always failed. Cart items now carry
  `available: bool` (`real_status == "visible"`, not mere presence, since the
  catalog view keeps hidden rows). Orval regenerated.
- Frontend: unavailable lines show a "No longer available — remove it to
  continue" row (no link), disabled qty steppers, and an enabled remove button.
  Store `itemCount`/`subtotal` count only available lines; `hasUnavailableItems`
  disables checkout with a notice. New i18n keys in en/ar/tr.
- Tests: backend `test_cart_line_marked_unavailable_after_unpublish`; frontend
  store getters cover available-only totals + `hasUnavailableItems`.

## Iteration 53 — Coalescing catalog refresh (backend)

- MED (was tracked): the scheduled/observer refresh used a plain lock-and-skip,
  so a write committing while another refresh held the lock had its refresh
  silently dropped — storefront stayed stale until the next 10-min tick.
  `refresh_products_catalog` now sets a dirty flag before contending for the
  lock and the holder drains it in a loop (clear-then-refresh), so every
  committed write is followed by a refresh that started after it. Returns -1
  only when another process holds the lock (it picks up the flag). Scheduler
  remains the backstop for the microscopic check-then-release window.
- Tests: `test_refresh_returns_minus_one_when_lock_held_but_marks_dirty`,
  `test_refresh_drains_a_write_that_lands_mid_refresh`. Full unit suite 375 pass;
  publish/soft-delete → storefront integration tests green.

## Iteration 54 — Block post-login open redirect (frontend, HIGH security)

- HIGH: `StorefrontAuth.vue` pushed `route.query.redirect` straight into
  `router.push` after login. `?redirect=//evil.test/phish` (or `https://...`,
  `/\evil`) bounced a freshly-authenticated user off-origin. New
  `lib/navigation.ts` `safeInternalPath()` allows only rooted same-origin paths
  and rejects protocol-relative / scheme / backslash variants; the login
  `redirectPath` now routes through it. Admin redirect is hardcoded, unaffected.
- Tests: `lib/navigation.test.ts` (6 cases). typecheck + lint clean.

## Iteration 55 — Bound customer order history (backend, MED)

- MED: `GET /api/account/orders` → `OrderService.list_orders` fetched every order
  a customer had ever placed (no limit), then re-queried items per order — a
  customer with a long history could force an unbounded scan + N+1. Added a
  shared `clamp_limit`/`clamp_offset` (`MAX_PAGE_LIMIT=100`) in `_deps.py`;
  `list_orders` now takes bounded `limit`/`offset` (default 50), and the account
  controller accepts + clamps `?limit`/`?offset`. Response shape unchanged.
- Test: `test_order_history_respects_limit` (2 orders, `?limit=1` → 1 row).
  Kit unit suite 375 pass; feature order-history tests green.

### r3 review backlog (in progress)
1. ~~HIGH: post-login open redirect~~ ✅ (iter 54)
2. ~~MED: checkout bypasses unavailable-item guard~~ — verified NOT a bug:
   `checkout` raises `ProductUnavailableError` → 409 for any non-visible line.
3. ~~MED: customer order history unbounded~~ ✅ (iter 55)
4. ~~MED: admin/storefront list endpoints accept unbounded `limit`~~ ✅ (iter 56)
5. MED: register name 255 vs DB column 120 → 500.
6. MED: category/vendor force-delete FK RESTRICT → 500.
7. MED: frontend admin route gate coarser than backend.
8. MED: client permissions go stale after admin change.

## Iteration 56 — Clamp page size on every list endpoint (backend, MED)

- MED: every admin list (`orders`, `vendors`, `users`, `categories`, `products`)
  and storefront list (`index`, by-category, `search`) plus `best_sellers`
  passed the client `?limit`/`?offset` straight to the query. `?limit=10000000`
  forced a full scan (and an N+1 on order rows). All now route through
  `clamp_limit`/`clamp_offset` (cap 100, floor 1; offset floor 0).
- Test: `test_060_pagination_clamp.py` (5 cases). Kit unit suite 380 pass.
5. MED: register name 255 vs DB column 120 → 500.
6. MED: category/vendor force-delete FK RESTRICT → 500.
7. MED: frontend admin route gate coarser than backend.
8. MED: client permissions go stale after admin change.

## Framework-convention remediation (review feedback, approved)

Reviewer: stop bypassing framework primitives (config layer, scopes, accessors,
FormRequest validation, arvel-image collection validation, starter structure).
Survey: subagent 39f3de81. Plan = 7 steps (config, media, scopes, guards,
validation, accessors/resources, seeding) before resuming r3 #5-#8.

- **iter 57 — config layer (done):** added `config/catalog.py`
  (`new_product_days`, `search_min_length`) and `config/pagination.py`
  (`max_limit`). `product_to_storefront` new-window, storefront search min
  length, and `clamp_limit` ceiling now read via `config(...)` at call time
  (not module import — registry is boot-populated). Dropped `_NEW_WINDOW`,
  `_MIN_QUERY_LENGTH`, `MAX_PAGE_LIMIT` constants. Unit 380 pass; storefront
  search feature tests green.

Two questions answered:
- "Top-selling electronics" is a decorative `home.big_sale_eyebrow` banner with
  no data binding; real best-sellers (`OrderService.best_sellers`) counts only
  delivered orders and there's **no order seeder** → always empty (iter rm7).
- Guards take a single `perm`; the arvel_permission trait already has
  `has_any_permission`/`has_all_permissions` — guard factory should accept a
  list (iter rm6).

- **iter 58 — media validation (done):** dropped the controller's hand-rolled
  `_MAX_IMAGE_BYTES`/`_ALLOWED_IMAGE_TYPES`/`_sniff_image_type`. Uploads now rely
  on the arvel-image collection (`config/image.py`) for size + MIME + content
  validation; controller maps `FileTooLargeError`/`InvalidMimeTypeError`/
  `ConversionFailedError` → 400 and reads a bounded body from
  `config("image.collections.images.max_size_bytes")`. Made config the single
  source: collection max set to 5 MiB (matches the previously-enforced limit).
  Spoofed `.jpg`/non-image still 400 (the framework's filename-extension MIME
  fallback passes the gate, then inline Pillow conversion fails). All 5 upload
  feature tests pass; unit 380 pass.

- **iter 59 — visible scope (done):** added `ProductCatalog.scope_visible`
  (method-style, like `Product.scope_published`). Replaced the duplicated
  `real_status == "visible"` query filters in product/cart/order/category
  services with `ProductCatalog.visible()` (entrypoint, chained, and inside a
  `where_has` callback). The scope is now the single place that pins the
  visibility predicate. Updated test_046/test_049 contracts to assert the scope
  instead of the raw filter. Unit 380 pass; storefront + cart/checkout feature
  suites 35 pass.

- **iter 60 — guard list/any-all (done):** `make_permission_guard` /
  `make_role_level_guard` now accept `str | Sequence[str]` with
  `match="all"|"any"`, delegating to the trait's `has_any_permission` /
  `has_all_permissions`. Collapsed the translations endpoint's two sequential
  `require_permission` calls into one list check. Framework guard tests +4
  (20 pass), mypy clean; kit unit 380 pass; rbac translations feature test
  still 403 for category-only role. (Answers reviewer Q2.)

- **iter 61 — FormRequest FK validation (done):** added
  `app/http/requests/product_request.py::validate_product_fks` using the
  framework `Validator` + `Rule.exists` for category/vendor existence; retired
  ProductService's imperative `_resolve_category_id`/`_resolve_vendor_id`
  (`.count()` lookups) and dropped the now-unused Category/Vendor imports. The
  service now trusts pre-validated, coerced FK ids.
  - **Why not auto-wired FormRequest:** the framework wrapper runs
    `validate_rules()` *before* `authorize()`, and the admin route group has no
    auth middleware — auto-wiring would run DB existence checks for
    unauthenticated callers. Kept the `require_permission` guard first in the
    controller and call `validate_product_fks` after it (OWASP A01/A07).
  - **Why str→UUID coercion stays in the request layer:** `Rule.exists` uses an
    untyped table clause, so a raw string trips Postgres `uuid = text`; binding
    a real `uuid.UUID` works. Blank/absent → `None` (nullable FK). Coercion is
    request-layer input parsing, not the existence check.
  - Verified: 6 FK feature tests pass (happy create/update, unknown→422,
    malformed→422, unauthorized→403 before validation). Unit +4 (384), mypy +
    pyright clean.

- **iter 62 — accessors (done):** moved the two *pure-derived* values to model
  `@accessor`s (same pattern as the framework's `RefreshToken.is_expired`):
  - `ProductCatalog.is_new` (from `created_at` + `catalog.new_product_days`);
    `product_to_storefront` now reads `product.is_new` and dropped the inline
    window math (and the now-unused `config`/`timedelta` imports).
  - `CartItem.subtotal` (snapshot price × qty); `_format_item` reads
    `item.subtotal`.
  - **Deliberately left in the serializer:** image urls / srcset and the cart
    line `available` flag. Those aren't intrinsic model state — image fields are
    presentation transforms of the eager-loaded media collection, and
    `available` is a cross-relation runtime check on the joined product's
    `real_status`. Forcing them into model accessors would couple the ORM to
    presentation/relation concerns (wrong abstraction).
  - **JsonResource:** not adopted. The kit already serializes through Pydantic
    response models (`*Out.model_validate`) wired as FastAPI `response_model` —
    a valid framework pattern. A wholesale JsonResource rewrite changes no
    behavior, would churn every endpoint + the Orval-generated frontend, and
    risks regressions in a heavily-tested path. Flagging rather than forcing.
  - test_059 rewritten to exercise the accessors directly (via `property.fget`,
    no DB). Unit 387 pass; mypy + pyright clean. Storefront + cart feature
    suites re-running to confirm end-to-end.
- **iter 63 — order seeder + best-sellers answer (R7, done):** the admin
  dashboard best-sellers list was empty because `best_sellers` only counts
  `status == "delivered"` orders and the kit seeded zero orders. Added
  `database/seeders/orders_seeder.py` (wired into `DatabaseSeeder` after
  `SampleUsersSeeder` — orders need both users and products): 4 delivered + 1
  pending order across the two sample customers, referencing real catalog
  products by slug. Idempotent — fixed order-id literals (`upsert` on `id`) and
  line items inserted only when the order has none yet. Reuses the existing
  seeder primitives (`self.db.upsert` + ORM lookups, same as `CatalogSeeder`)
  and backdates `created_at` so the dashboard's 7-day revenue series has data.
  - **"Top-selling electronics" was a red herring.** That storefront string is a
    static promo *eyebrow* (`home.big_sale_eyebrow`), not a data list — it's
    never "empty". The actual empty feature was the admin best-sellers card.
  - No seeder unit test: matches the kit convention (no seeder has one), and the
    best-sellers/dashboard SQL is already covered by `test_admin_dashboard.py`
    integration tests that build orders through the live checkout API. Lint +
    ruff clean; 387 unit tests green.
  - **Remaining (R7 closes the remediation set):** 4 MED review items still open
    — register-name length (255 vs DB 120 → 500), category/vendor force-delete FK
    RESTRICT → 500, frontend admin route gate coarser than backend, client
    permissions go stale after admin change.

## Blockers

None. All quality gates green.

## Next 3 Actions

1. Design phase: run `design-system-kit` against the storefront/admin using
   `deep-research` inspiration (large, standalone iteration).
2. Re-run the review subagents to confirm A01 + broken-contract + dual-layer
   findings are resolved and surface the next priority batch.
3. Consider migrating `AdminListPage`/`AdminDashboard` off `listAdminRows` to
   the generated index hooks if the review still flags the generic helper.
