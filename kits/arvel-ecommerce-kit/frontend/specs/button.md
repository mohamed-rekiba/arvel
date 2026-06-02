---
name: Button
description: Primary action button with brand, accent, ghost, and danger variants.
token_source: docs/ux/DESIGN.md
component: src/components/ui/Button.vue
---

# Button

Base interactive element. Used across storefront and admin for primary actions, secondary nav,
destructive operations, and ghost/link-style calls-to-action.

## Props

| Prop       | Type                                           | Required | Default     | Description      |
| ---------- | ---------------------------------------------- | -------- | ----------- | ---------------- |
| `variant`  | `'primary' \| 'accent' \| 'ghost' \| 'danger'` | no       | `'primary'` | Visual style     |
| `size`     | `'sm' \| 'md' \| 'lg'`                         | no       | `'md'`      | Size scale       |
| `disabled` | `boolean`                                      | no       | `false`     | Disabled state   |
| `type`     | `'button' \| 'submit' \| 'reset'`              | no       | `'button'`  | HTML button type |

## Tokens

| Variant | Background         | Text            | Hover bg                 |
| ------- | ------------------ | --------------- | ------------------------ |
| primary | `--color-brand`    | `white`         | `--color-brand-hover`    |
| accent  | `--color-cart-cta` | `white`         | `--color-cart-cta-hover` |
| ghost   | `transparent`      | `--color-brand` | `--color-brand-softest`  |
| danger  | `--color-danger`   | `white`         | darker danger            |

## Sizes

| Size | Padding       | Font                      |
| ---- | ------------- | ------------------------- |
| sm   | `px-3 py-1.5` | `text-sm`                 |
| md   | `px-4 py-2.5` | `text-sm font-semibold`   |
| lg   | `px-6 py-3`   | `text-base font-semibold` |

## Spec

```
[  Primary Button  ]  ← brand bg, white text
[  Accent Button   ]  ← cart-cta bg, white text
[  Ghost Button    ]  ← transparent, brand text, brand-softest on hover
[  Danger Button   ]  ← danger bg, white text
```
