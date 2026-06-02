---
name: StatCard
description: Admin dashboard KPI card with icon, label, value, and optional trend indicator.
token_source: docs/ux/DESIGN.md
component: src/components/admin/StatCard.vue
---

# StatCard

KPI summary card for the admin dashboard. Shows a metric with an icon and optional month-over-month trend.

## Props

| Prop    | Type                               | Required | Description                                           |
| ------- | ---------------------------------- | -------- | ----------------------------------------------------- |
| `label` | `string`                           | yes      | Metric name ("Total Revenue", "Orders", etc.)         |
| `value` | `string`                           | yes      | Formatted value ("$12,340", "1,204", etc.)            |
| `trend` | `number`                           | no       | MoM percentage change; positive = up, negative = down |
| `icon`  | `string`                           | yes      | Emoji or Unicode symbol for the icon cell             |
| `tone`  | `'amber' \| 'indigo' \| 'emerald'` | yes      | Palette for the icon cell                             |

## Tokens

| Usage               | Token                                                |
| ------------------- | ---------------------------------------------------- |
| Card background     | `--color-admin-surface`                              |
| Label text          | `--color-fg-muted`                                   |
| Value text          | `--color-fg`                                         |
| Trend up bg         | `--color-kpi-emerald-bg`                             |
| Trend up text       | `--color-kpi-emerald-fg`                             |
| Trend down bg       | `--color-danger` (at 10% opacity via `bg-danger/10`) |
| Trend down text     | `--color-danger`                                     |
| Icon cell — amber   | `--color-kpi-amber-bg` / `--color-kpi-amber-fg`      |
| Icon cell — indigo  | `--color-kpi-indigo-bg` / `--color-kpi-indigo-fg`    |
| Icon cell — emerald | `--color-kpi-emerald-bg` / `--color-kpi-emerald-fg`  |

## Spec

```
┌─────────────────────────────────────────────┐
│  Total Revenue                    [💰]       │  ← label / icon cell (tone-colored)
│  $12,340                                    │  ← value (bold, fg)
│  [+12%] vs last month                       │  ← trend badge (emerald) + muted caption
└─────────────────────────────────────────────┘
```
