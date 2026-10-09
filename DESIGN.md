# Fifth Wheel design reference

## Brand

- The product UI is branded **Fifth Wheel**; the mark represents a coupling plate with a kingpin keyhole.
- `Wordmark` pairs the mark with the Fifth Wheel name and is used on Login and the broker app shell.
- The repository/README and FastAPI title remain KingOfFreight; the frontend package remains `kingoffreight-frontend`.
- Customer texts and emails use the configured broker name/company, not the Fifth Wheel brand.

## Theme

- Dark is the default; light is the alternate theme.
- The selected theme is stored in `localStorage` as `fw-theme`.
- `index.html` sets `data-theme` before the app loads to prevent a theme flash; `ThemeToggle` changes it in-app.

## Tokens

Values are RGB tokens from `frontend/src/styles.css`, shown here as hex.

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` | `#F7F8FA` | `#0B1220` | App canvas |
| `surface` | `#FFFFFF` | `#121A2B` | Cards and controls |
| `surface-2` | `#F1F3F7` | `#172136` | Secondary surfaces |
| `surface-3` | `#E6EAF1` | `#1E2A42` | Raised/selected surfaces |
| `line` | `#E2E6EE` | `#1F2A40` | Borders and dividers |
| `line-strong` | `#CDD3DE` | `#2C3A56` | Emphasized borders |
| `fg` | `#0F172A` | `#E8ECF4` | Primary text |
| `fg-2` | `#334155` | `#C3CAD8` | Secondary text |
| `muted` | `#5B6577` | `#8A94A8` | Supporting text/icons |
| `subtle` | `#667085` | `#8090A6` | Lowest-emphasis readable text |
| `accent` | `#F5B83D` | `#F5B83D` | Gold accent |
| `accent-hover` | `#E8A524` | `#FFC757` | Accent hover |
| `accent-ink` | `#8A5A00` | `#F5B83D` | Text on tinted accent |
| `on-accent` | `#0F172A` | `#0B1220` | Text on solid accent |
| `hero` | `#0B1220` | `#0B1220` | Login hero surface |
| `hero-fg` | `#E8ECF4` | `#E8ECF4` | Text on hero surface |
| `scrim` | `#0F172A` | `#03060C` | Modal backdrop |
| `st-booked` | `#4C8DFF` | `#4C8DFF` | Booked status indicator |
| `st-picked` | `#8B7CFF` | `#8B7CFF` | Picked-up indicator |
| `st-transit` | `#2DD4BF` | `#2DD4BF` | In-transit indicator |
| `st-delayed` | `#FF6B57` | `#FF6B57` | Delayed indicator |
| `st-delivered` | `#3DDC97` | `#3DDC97` | Delivered indicator |
| `st-booked-ink` | `#1F5FD6` | `#74A6FF` | Booked status text |
| `st-picked-ink` | `#5B45E0` | `#A69BFF` | Picked-up status text |
| `st-transit-ink` | `#0A7268` | `#2DD4BF` | In-transit status text |
| `st-delayed-ink` | `#C2382A` | `#FF6B57` | Delayed status text |
| `st-delivered-ink` | `#157548` | `#3DDC97` | Delivered status text |
| `warn` | `#F5A524` | `#F5A524` | Attention indicator |
| `warn-ink` | `#8A5300` | `#F5A524` | Attention text |
| `on-warn` | `#0F172A` | `#0B1220` | Text on solid warning |
| `danger` | `#C42B3A` | `#FF5A5F` | Error/danger indicator |
| `danger-ink` | `#C42B3A` | `#FF5A5F` | Danger text |
| `on-danger` | `#FFFFFF` | `#0B1220` | Text on solid danger |
| `ok` | `#3DDC97` | `#3DDC97` | Success indicator |
| `ok-ink` | `#157548` | `#3DDC97` | Success text |

## Status colors

Status hues and matching `*-ink` variants identify booked, picked up, in transit, delayed, and delivered states. Pair each status color with a visible label or dot; do not use color alone.

## Typography

- Inter Variable is the app font.
- Use `tabular-nums` for IDs, money, counts, and times where displayed.
- Text is at least 11px.

## Gold rule

Gold is reserved for a page/modal/footer's primary action (at most one per card), active navigation and its count, focus rings, PageHeading eyebrows, and the logo. The Status selected-load highlight and tracking hero ring are approved highlights; do not use gold as generic secondary or informational styling.

## Components

- `Button` / `buttonClass`: shared variants and responsive sizes for actions.
- `ButtonVariant`, `ButtonSize`, `BadgeTone`: shared control and badge types.
- `fieldClass`: shared input/select/textarea base styles.
- `Input`: text-entry control.
- `Select`: native select control.
- `Textarea`: multiline text-entry control.
- `Field`: label, hint, and validation-message wrapper.
- `Card`: bordered surface container.
- `Badge`: compact status/tone label.
- `Tabs`: roving-focus tabs with Left/Right arrow navigation.
- `Skeleton`: aria-hidden loading placeholder with motion-safe pulse.
- `Modal`: dialog with focus trap/restoration, Escape dismissal, and mobile sheet layout.
- `ToastProvider`: polite live region; success uses `status`, errors use `alert`, and items auto-dismiss.
- `ListDetail`: split list/detail at 1280px and a detail sheet below that width.
- `ListRow`: selectable list item with Up/Down arrow navigation.
- `ListRowSkeleton`: placeholder rows while lists load.
- `EmptyState`: icon, title, description, and optional action for empty views.
- `ErrorState`: inline error with optional retry action.
- `StatusBadge` / `FlagBadge`: labeled load status and carrier flag indicators.
- `PageHeading`: eyebrow, title, description, and optional page action.

## Layout

- The sidebar is shown at `md` and wider; mobile navigation is shown below `md`.
- List/detail uses a split layout at 1280px and a sheet below 1280px.
- Status and TruckStop selection uses `?load=`; Inbox selection uses `?item=`.

## Patterns

- Customer updates follow compose → exact preview → Approve & Send.
- Use skeleton placeholders while data loads, inline retry errors for failed views, and toasts for action feedback.

## Accessibility

- Keep text contrast at WCAG AA and retain the visible focus ring.
- Shared small buttons, tabs, and toast dismissal are 44px minimum on touch layouts; reduced-motion preferences are honored while spinners continue.
- Tabs use Left/Right arrows; list rows use Up/Down arrows.
- Escape closes dialogs and alerts; dialogs trap and restore focus.
- The first focus stop is the Skip to content link, which moves focus to main.
