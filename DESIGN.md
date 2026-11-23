# Design

The source of truth for how the app looks. It mirrors the tokens at the top of `app/static/style.css`; if the two drift, the CSS wins until this file is updated.

## The idea

The product reads a paper bill and annotates it. So the page is warm paper, the text is blue-black ink, and ExpectAI's blue is the reviewer's pen. The pen marks three things only: what needs the owner, what is selected, and the one action that moves the bill on. Nothing else is coloured.

The scene it was designed for: a bakery owner reading their bill on a laptop at the counter in daylight, and an interviewer looking at the same screen in a bright meeting room. Both call for a light, paper-like page that reads well at arm's length.

## Colour

Restrained: tinted neutrals carry the page, and the pen stays under a tenth of any screen.

| Role | Value | Use |
| --- | --- | --- |
| paper | `oklch(0.972 0.009 85)` | the page |
| paper-sunken | `oklch(0.948 0.011 85)` | asides, drop zone, hover |
| sheet | `oklch(0.992 0.004 85)` | the bill and the covering letter, never pure white |
| ink | `oklch(0.24 0.028 268)` | text, blue-black |
| ink-muted | `oklch(0.44 0.02 268)` | secondary text |
| ink-faint | `oklch(0.52 0.015 268)` | meta, timestamps; still 4.5:1 on paper |
| line | `oklch(0.885 0.012 85)` | rules |
| pen | `#1930ff` | ExpectAI blue: needs the owner, selection, primary action, focus |
| danger | `oklch(0.5 0.16 30)` | a failed check, a failed or rejected bill |

There is no green. A passed check is quiet ink, because passing is the normal case and should not compete with the one thing that needs attention.

## Type

- **Newsreader**, a serif, for reading moments: page titles, stage names, questions put to the owner, the covering letter, design chapters. Weight 400; size carries the hierarchy.
- **Geist**, ExpectAI's own typeface, for the interface: body, buttons, labels and figures.
- **Geist Mono** for meta: stage numbers, hashes, timestamps, check results. Labels are 11px capitals at 0.08em tracking.

All three are bundled in `app/static/fonts/`, so the app makes no font requests and works offline.

## Layout

- Rows and rules carry the content. The bill is the only object that sits on its own sheet; the covering letter is the only other sheet, because it is a letter.
- One content width for every page, so the wordmark and the content share an edge.
- Status is inline text after a small dot. There are no pills.
- The eight stages are a ruled strip: done in ink, the current stage in pen, the rest faint.

## Components

- **Buttons.** Primary is solid pen with sheet-coloured text and a 6px radius. Secondary is a 1px ink border. Ghost is muted text. Disabled keeps its colour at 40% opacity.
- **Queries.** A question to the owner sits in a ruled box with a pen query mark, the question set in the serif, and three answers: confirm, correct, or not sure.
- **Highlight.** Selecting a value marks its line on the bill with a pen-tinted band, as a reviewer would underline it.

## Motion

Colour and border changes only, 160ms, ease-out. Nothing moves on hover. No page-load animation. Reduced motion turns transitions off.

## Banned here

Pills and chips for status, cards in a grid, gradient avatars, lift or scale on hover, glass and backdrop blur, side-stripe borders, gradient text, pure white or black, em dashes in copy.
