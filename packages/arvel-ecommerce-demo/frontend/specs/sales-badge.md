---
name: SalesBadge
description: Discount percentage badge overlaid on product card images.
token_source: docs/ux/DESIGN.md
component: src/components/storefront/SalesBadge.vue
---

# SalesBadge

Small pill badge showing a discount percentage. Appears in the top-start corner of product card images.

## Props

| Prop       | Type     | Required | Description                                 |
| ---------- | -------- | -------- | ------------------------------------------- |
| `discount` | `number` | yes      | Integer percentage (e.g. 25 renders "-25%") |

## Tokens

| Usage      | Token                    |
| ---------- | ------------------------ |
| Background | `--color-discount-badge` |
| Text       | `white`                  |

## Variants

| Variant | State  | Notes                                         |
| ------- | ------ | --------------------------------------------- |
| default | always | Single variant — color is fixed by convention |

## Accessibility

- Rendered as `<span>` (decorative; screen readers skip it)
- No role or aria needed (pricing text in parent provides context)

## Spec

```
┌──────────────┐
│  -25%        │  ← bg-discount-badge, white text, pill shape
└──────────────┘
```
