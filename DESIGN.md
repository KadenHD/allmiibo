---
name: Allmiibo Manager
description: A calm Windows explorer that keeps the device library at the center.
colors:
  graphite-canvas: "#0f1318"
  graphite-surface: "#151a20"
  graphite-raised: "#202832"
  graphite-control: "#222a33"
  graphite-control-hover: "#2a3540"
  graphite-tree: "#101419"
  graphite-border: "#34404b"
  text-primary: "#edf2f6"
  text-muted: "#99a4af"
  forest-import: "#176548"
  forest-import-hover: "#1f7a59"
  import-text: "#ffffff"
  mint-status: "#58d6a5"
  mint-connected-surface: "#18392f"
  mint-connected-text: "#79e1b8"
  blue-search: "#68a8ff"
  blue-link: "#82b8ff"
  blue-guide: "#17233a"
typography:
  display:
    fontFamily: '"Segoe UI Variable", "Segoe UI"'
    fontSize: "24px"
    fontWeight: 700
  brand:
    fontFamily: '"Segoe UI Variable", "Segoe UI"'
    fontSize: "22px"
    fontWeight: 700
  title:
    fontFamily: '"Segoe UI Variable", "Segoe UI"'
    fontSize: "14px"
    fontWeight: 650
  body:
    fontFamily: '"Segoe UI Variable", "Segoe UI"'
    fontSize: "13px"
  label:
    fontFamily: '"Segoe UI Variable", "Segoe UI"'
    fontSize: "13px"
    fontWeight: 600
rounded:
  menu: "5px"
  control: "7px"
  surface: "10px"
  chip: "11px"
  explorer: "12px"
spacing:
  toolbar: "4px"
  compact: "7px"
  control-y: "8px"
  surface: "10px"
  content: "14px"
  page-x: "24px"
components:
  button-import:
    backgroundColor: "{colors.forest-import}"
    textColor: "{colors.import-text}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  button-import-hover:
    backgroundColor: "{colors.forest-import-hover}"
    textColor: "{colors.import-text}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  button-secondary:
    backgroundColor: "{colors.graphite-control}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  connection-chip:
    backgroundColor: "{colors.graphite-raised}"
    textColor: "{colors.text-muted}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "4px 10px"
  connection-chip-connected:
    backgroundColor: "{colors.mint-connected-surface}"
    textColor: "{colors.mint-connected-text}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "4px 10px"
  guide-banner:
    backgroundColor: "{colors.blue-guide}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.surface}"
    padding: "10px 12px 10px 14px"
  explorer-panel:
    backgroundColor: "{colors.graphite-surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.explorer}"
---

# Design System: Allmiibo Manager

## Overview

**Creative North Star: "The Quiet Console"**

Allmiibo Manager is a device explorer, not a dashboard. The device is the
workspace and local files are inputs. The remote folder tree therefore owns the
visual hierarchy, while connection state, commands, and activity remain clear
without competing with it.

The visual world is a calm graphite utility with the density of Windows File
Explorer. Mint confirms device presence, forest green carries the single global
import action, and blue guides scanning or help. The stable story is: connect,
inspect, modify precisely, and confirm.

**Key characteristics:**

- The device is always presented as the source of truth.
- Controls are native, direct, and compact; the file area gets more space.
- One forest-green action leads the command bar.
- Technical states become clear confirmations or recovery instructions.
- The Bluetooth illustration is vector-based and subtly animated while scanning.

## Colors

The palette combines a low-saturation graphite foundation with three strict
semantic accents: forest green for import, mint for connection or success, and
blue for scanning and guidance.

### Primary

- **Import forest** (`forest-import`) identifies ZIP import and the primary retry.
- **Active forest** (`forest-import-hover`) marks hover without changing meaning.

### Secondary

- **Status mint** (`mint-status`) shows device presence and fills progress.
- **Connected mint** (`mint-connected-surface`, `mint-connected-text`) builds the
  positive connection chip.
- **Search blue** (`blue-search`) carries the Bluetooth scanning signal.
- **Link blue** (`blue-link`) distinguishes help, downloads, and expandable details.
- **Guide blue** (`blue-guide`) forms the Drive and firmware information banner.

### Neutrals

- Graphite canvas and surfaces create hierarchy without decorative shadows.
- Graphite controls distinguish resting, hover, tree, and border states.
- Primary and muted text tokens cover names, metadata, capacity, and subtitles.

### Named rules

**The Three Signals Rule.** Forest means import, mint means connected or
successful, and blue means scan, learn, or navigate. Never exchange these roles.

**The One Forest Action Rule.** A surface shows only one priority forest action.

## Typography

**Display font:** Segoe UI Variable with Segoe UI fallback

**Body font:** Segoe UI Variable with Segoe UI fallback

The Windows system stack keeps the application familiar and readable without
increasing package size. Hierarchy comes from size and weight, never from a
decorative second family.

- **Display** is reserved for the central connection status.
- **Brand** names the product in the persistent header.
- **Title** marks the library and compact sections.
- **Body** serves commands, file rows, instructions, and metadata.
- **Label** emphasizes the connection chip and primary action.

**The Native Voice Rule.** Keep the Segoe UI stack and reserve strong weights
for titles, the status chip, and the primary action.

## Layout

The default desktop canvas is 1080×720 px and remains usable down to 720×520 px.
A `page-x` margin frames the window. Major blocks use the `content` rhythm, while
internal surfaces use `surface` or `compact` spacing according to density.

The header aligns identity on the left and capacity plus connection state on the
right. After connection, the Drive/firmware guide, command bar, expandable tree,
and activity area form one column. The tree consumes available height and the
activity area stays anchored at the bottom.

At narrow widths, command labels remain visible as long as possible. A **More**
button immediately follows the last visible command and holds the remaining
actions instead of turning the whole interface into ambiguous icon-only controls.

**The Tree Owns the Space Rule.** After connection, vertical expansion belongs
to the remote folder tree first.

## Elevation and shape

The interface is flat by default. Tonal canvas, surface, control, and tree layers
create depth, supported by thin outlines around the explorer and commands. The
current interface defines no drop shadows.

**The Tonal Depth Rule.** Create hierarchy with surface contrast and thin
borders, never with accumulated shadows.

Shapes are softly technical: compact controls use `control`, banners use
`surface`, the short status capsule uses `chip`, and the dominant library panel
uses `explorer`. Radii stay restrained to preserve the Windows utility character.

## Components

### Buttons

- Primary import uses forest green and white text.
- Neutral commands move from `graphite-control` to
  `graphite-control-hover` while retaining a readable outline.
- Help actions have no background or border and use `blue-link`.
- Disabled controls remain visible but recede until connection or operation end.

### Connection chip

The neutral chip communicates waiting or disconnection. The connected variant
combines one status dot with the real device name; never add a duplicate badge.

### Library tree

The library is the signature component: dense rows, a compact selection column,
then Name, Type, and Size. The **amiibo** root remains visible, selectable as a
destination, and non-deletable. The header checkbox selects all deletable files
and folders and reflects none, partial, or complete selection. `fav`, `data`, and
their parents keep visible disabled checkboxes. Indentation and expansion belong
only to Name, so checkboxes stay aligned at every depth.

Drop handling and context menus select the visual target before acting. Clicking
empty space selects the **amiibo** root.

### Activity and progress

The bottom panel shows a persistent summary, temporary mint progress, and a
collapsible log. Deletion exposes targets and file/folder totals. Import separates
ZIP extraction from BLE synchronization. Long operations name the current folder
or stage and emit a heartbeat every five seconds until transfer progress begins.
Extreme paths are truncated in the compact status but remain available in the
tooltip and log. Progress mirrors to the Windows taskbar, final duration is
reported, and a subtle notification completes batch operations.

## Guidance

- **Do** let the folder tree occupy most connected-state space.
- **Do** show the destination before upload and keep proof in the activity log.
- **Do** retain full action labels while the toolbar can accommodate them.
- **Do** translate Bluetooth states into user instructions and keep raw
  diagnostics in Details.
- **Do** keep a visible disabled checkbox for `fav`, `data`, and their parents.
- **Do** preserve the connect, inspect, modify, confirm sequence.
- **Don't** expose internal paths, drive letters, or temporary files as user concepts.
- **Don't** multiply cards, badges, or accents around the folder tree.
- **Don't** use forest green for destructive or secondary actions.
- **Don't** replace every compact-mode label with an icon.
- **Don't** add decorative shadows to tonally distinct surfaces.
- **Don't** permit a rename or deletion that bypasses `fav` or `data` protection.
