---
name: ProductCard
description: Storefront product card with image, name, price, discount badge, wishlist, and add-to-cart.
token_source: docs/ux/DESIGN.md
component: src/components/storefront/ProductCard.vue
---

# ProductCard

Primary building block for product grids on the storefront. Displays product image with interactive
overlays (discount badge, wishlist button) and a hover-revealed "Add to Cart" CTA.

## Props

| Prop      | Type      | Required | Description                    |
| --------- | --------- | -------- | ------------------------------ |
| `product` | `Product` | yes      | Full storefront product object |

The discount badge and struck-through price render only when the product's
`original_price` is set and greater than `price` — there is no client-side
sale override.

## Tokens

| Usage                      | Token                    |
| -------------------------- | ------------------------ |
| Image placeholder bg       | `--color-app-bg-sunken`  |
| Image placeholder text     | `--color-fg-faint`       |
| Product name text          | `--color-fg`             |
| Price text                 | `--color-fg`             |
| Original price (strike)    | `--color-fg-muted`       |
| "Add to Cart" button bg    | `--color-cart-cta`       |
| "Add to Cart" button hover | `--color-cart-cta-hover` |

## Behavior

- Card lifts and its border picks up `--color-primary-300` on hover (soft elevation)
- Image scales on `group-hover` (subtle zoom)
- "Add to Cart" slides up and fades in on `group-hover`
- Unauthenticated "Add to Cart" redirects to `/login`
- Clicking the card navigates to `/products/{slug}`
- Discount badge appears when `discountPct > 0`

## Spec

```
┌─────────────────────────┐
│  [-25%]          [♡]   │  ← badge (top-start) / wishlist (top-end)
│                         │
│   [product image]       │  ← aspect-square, object-cover
│                         │
├─────────────────────────┤
│  Product Name           │  ← fg text, sm, medium
│  $29.99  ~~$39.99~~     │  ← fg bold / fg-muted strike-through
├─────────────────────────┤
│  [  Add to Cart  ]      │  ← cart-cta bg, appears on hover
└─────────────────────────┘
```
