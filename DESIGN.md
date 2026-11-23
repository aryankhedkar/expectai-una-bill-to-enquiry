# Design

This file is the source of truth for how the app looks. It mirrors the tokens at the top of `app/static/style.css`, and if the two drift apart, the CSS wins until this file is updated.

## The idea

The product reads a paper bill and annotates it, so I made the page warm paper with blue-black ink and used ExpectAI's blue as the reviewer's pen. The pen marks three things, which are whatever needs the owner, whatever is selected, and the one action that moves the bill on, and nothing else on the page is coloured.

I designed it with two scenes in mind. One is a bakery owner reading their bill on a laptop at the counter in daylight, and the other is an interviewer looking at the same screen in a bright meeting room. Both call for a light page that feels like paper and reads well at arm's length.

## Colour

I kept the palette restrained, so tinted neutrals carry the page and the pen stays under a tenth of any screen.

| Role | Value | Use |
| --- | --- | --- |
| paper | `oklch(0.972 0.009 85)` | the page |
| paper-sunken | `oklch(0.948 0.011 85)` | asides, drop zone, hover |
| sheet | `oklch(0.992 0.004 85)` | the bill and the covering letter, in an off-white that stops short of pure white |
| ink | `oklch(0.24 0.028 268)` | text, blue-black |
| ink-muted | `oklch(0.44 0.02 268)` | secondary text, labels and eyebrows |
| ink-faint | `oklch(0.52 0.015 268)` | meta, timestamps; still 4.5:1 on paper |
| line | `oklch(0.885 0.012 85)` | rules |
| pen | `#1930ff` | ExpectAI blue, for whatever needs the owner, selection, the primary action, focus and the walkthrough ring |
| danger | `oklch(0.5 0.16 30)` | a failed check, a failed or rejected bill |

I left green out altogether, and a passed check is set in quiet ink, because passing is the normal case and should not compete with the one thing on the page that needs attention.

## Type

Newsreader, a serif, is for the moments when someone is reading, which means page titles, stage names, the questions put to the owner, the covering letter and the chapters of the design page. It is set at weight 400 throughout, so size carries the hierarchy.

Geist is the typeface ExpectAI uses, and I use it for the rest of the interface, including body text, buttons, figures, labels and eyebrows. Labels and eyebrows are set in the same family as the text around them, in sentence case at 13px in the muted ink colour, so the page reads in one voice and each label sits quietly above the thing it names.

Geist Mono is kept for values that are code-like, which are file names, hashes, meter numbers and timestamps, because those are read one character at a time and are easier to compare in fixed widths.

Headings are left as plain type, so nothing in a heading is underlined or marked with a band, and that includes the word "approved" in the title on the home page, which sits in the same ink as the rest of the line.

All three typefaces are bundled in `app/static/fonts/`, so the app makes no font requests and works offline.

## Layout

Rows and rules carry the content, and the only two objects that sit on a sheet of their own are the bill and the covering letter, because each of them is a document in its own right. Each page uses the same content width, so the wordmark and the content share an edge.

Status is written inline after a small dot, and the eight stages sit in a ruled strip, with the finished stages in ink, the current one in pen and the rest faint.

## Components

### Buttons

The primary button is solid pen with sheet-coloured text and a 6px radius, and it is kept for the one action that moves the bill on. A secondary button has a 1px ink border and a ghost button is muted text, and a disabled button keeps its colour at 40% opacity so it still reads as the same control.

### Queries

A question to the owner sits in a ruled box with a pen query mark beside it. The question is set in the serif, and below it are three answers, which let the owner confirm the value, correct it, or say they are not sure.

### Highlight

When the owner selects a value, its line on the bill gets a pen-tinted band behind it, the way a reviewer would mark a line on a paper bill. Bands like this belong to the bill, which is why nothing in a heading carries one.

### Walkthrough

The walkthrough at `/walkthrough` takes a visitor through one bill in beats, in the way a product demo does. For each beat a scrim dims the page, and one region of the real interface stays lit inside a ring in pen blue, which carries the pen's selection role over to the tour. A caption card sits beside the lit region and explains what that part of the page is doing, with Back and Next to move between beats, and the arrow keys do the same. The beats run the misread_mpan sample through the app's own code, so the lit regions are the real interface and the numbers in them come from the product.

## Motion

Transitions change colour and borders only, over 160ms with an ease-out curve. Nothing moves on hover and nothing animates when a page loads, and when reduced motion is turned on the transitions are switched off.

## Banned here

I keep a short list of things out of this interface, which covers pills and chips for status, cards laid out in a grid, gradient avatars, lift or scale on hover, glass and backdrop blur, side-stripe borders, gradient text, pure white or pure black, and em dashes in the copy.
