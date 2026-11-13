---
name: "CheckStock"
description: "A quiet industrial ledger for visible, consistent inventory."
colors:
  forest: "#173c32"
  forest-hover: "#214d40"
  lime: "#d9e8a0"
  paper: "#f6f5f0"
  white: "#ffffff"
  ink: "#22352e"
  muted: "#68736b"
  line: "#e3e6dd"
  available: "#27664e"
  error: "#a53e2f"
  reserved: "#8a5d14"
typography:
  headline:
    fontFamily: "Onest, sans-serif"
    fontSize: "31px"
    fontWeight: 650
    letterSpacing: "-1.1px"
  title:
    fontFamily: "Onest, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    letterSpacing: "-0.4px"
  body:
    fontFamily: "Onest, sans-serif"
    fontSize: "14px"
    fontWeight: 400
  table:
    fontFamily: "Onest, sans-serif"
    fontSize: "12px"
  label:
    fontFamily: "Onest, sans-serif"
    fontSize: "10px"
    fontWeight: 500
  metric:
    fontFamily: "Onest, sans-serif"
    fontSize: "29px"
    fontWeight: 600
    letterSpacing: "-0.7px"
rounded:
  badge: "5px"
  control: "8px"
  panel: "12px"
  dialog: "16px"
spacing:
  compact: "8px"
  control: "16px"
  panel: "20px"
  card: "24px"
  workspace: "42px"
components:
  button-primary:
    backgroundColor: "{colors.forest}"
    textColor: "{colors.white}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
    height: "42px"
  button-primary-hover:
    backgroundColor: "{colors.forest-hover}"
  button-secondary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  panel:
    backgroundColor: "{colors.white}"
    rounded: "{rounded.panel}"
  nav-active:
    backgroundColor: "{colors.lime}"
    textColor: "{colors.forest}"
    rounded: "{rounded.control}"
    padding: "13px 15px"
---

# Design System: CheckStock

## Overview

**Creative North Star: "Quiet Industrial Ledger"**

A calm, practical workspace for a warehouse manager reading quantities throughout the day. Warm paper surrounds white working surfaces; forest navigation anchors the tool, while lime marks the current destination. Compact type and consistent alignment give operational information priority.

**Key Characteristics:**
- Dense, legible working surfaces.
- Restrained color with explicit status labels.
- Geometric SVG icons and tabular quantities.

## Colors

### Primary
Forest anchors navigation and primary actions; forest-hover provides action feedback. Lime identifies the active destination and small brand accents.

### Secondary
Available green marks sendable quantities. Reserved amber distinguishes held units. Error red identifies failures and unavailable states. Status badges combine text with tinted backgrounds rather than relying on color alone.

### Neutral
Paper is the workspace, white is the working surface, ink carries information, muted carries supporting context, and line separates records.

**The Status Has Words Rule.** Pair status color with a readable label or quantity context.

## Typography

Locally bundled Onest variable serves both headings and working text, including Cyrillic. Headline and metric roles are compact and moderately heavy; section titles remain subordinate. Tables use the table role, with smaller labels for headings and SKU codes. Quantities use tabular numerals and align right in tables. Paragraph copy uses a relaxed line height (1.6).

## Layout

Desktop uses a fixed navigation rail (236px), a top bar (76px), workspace gutters (42px), and a centered main area capped at (1600px). At (1150px) the rail narrows to (210px) and gutters to (25px). At (800px) navigation becomes a sticky icon bar, gutters become (20px), summaries form two columns, and transit sections stack. At (420px) gutters become (15px) and heading actions wrap. Wide tables scroll inside their own container, preserving the record structure.

## Elevation & Depth

Tonal layers and thin separators provide everyday depth. Resting panels have no shadow. A primary action gains a soft shadow on hover; dialogs and success notifications float above the workspace. Dialog backdrops dim and blur the page. One restrained entrance animation moves content upward (7px over 0.4s); reduced-motion preferences disable transitions and animation.

**The Flat Workspace Rule.** Reserve floating depth for temporary overlays and action feedback.

## Shapes

Rounded panels frame records; smaller corners distinguish controls and compact status badges. Dialogs use the largest radius. Geometric line icons share a restrained stroke (1.7px) and rounded caps. Use the token radii rather than introducing a second corner vocabulary.

## Components

- **Buttons:** forest primary, bordered white secondary, and pale red danger. Standard actions have a minimum height (42px), compact actions (31px). Hover changes the surface; visible keyboard focus uses a green outline (3px with 3px offset). Disabled controls reduce opacity.
- **Inputs:** native selects and text fields use quiet borders, subtly warm surfaces, and rounded corners. Dialog fields have a minimum height (44px); supporting copy explains constraints. Errors appear inline in a pale red block.
- **Navigation:** persistent forest rail with muted light labels; lime fills the active item. Mobile preserves the same SVG symbols in an icon bar.
- **Panels and badges:** white panels use fine borders and clipped corners. Small tinted badges carry readable state labels. Warehouse cards share this surface language with internal padding (24px).
- **Inventory ledger:** one product identity spans its warehouse rows. Keep quantities aligned and stock, availability, and reservations in separate columns.
- **Transit strip:** three adjacent cells separate FF transfers, FBO, and FBS. A muted green surface connects the cells; on mobile they become a vertical stack.
- **Dialogs and feedback:** one focused dialog contains each mutation; success notifications announce the result. Preserve the visual difference between errors and success feedback.

## Do's and Don'ts

- Do keep quantities tabular and right-aligned in working tables.
- Do preserve readable status labels alongside color.
- Do retain local Onest and the shared SVG icon vocabulary.
- Don't mix transit quantities into the physical-stock ledger.
- Don't use floating card shadows for ordinary resting panels.
- Don't remove table columns to fit a narrow viewport; keep contained horizontal scrolling.
