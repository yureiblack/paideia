# 25. Interface design

Date: 2026-11-21
Status: accepted

## Context

By Phase 24 every tab worked, but the interface had grown one section at a
time, and a look at it at 1280 px wide, light and dark, showed it:

- Every tab was one long column of bordered cards of equal weight. The
  Overview was 2,055 px tall with 47 controls; the knowledge map 6,981 px
  with 41 full cards and 97 controls; the roadmap 6,447 px with every stage
  and concept open and 114 controls.
- Nothing said which part of a page mattered. Notes on how something was
  made ("written by the local model", "from Week 5.pdf") sat on every card.
- There was almost no colour: the red of Delete, the green of status
  badges, and one orange note. Dark mode followed the system and could not
  be chosen.
- The header showed four health indicators all the time.

The aim of this phase was an interface that reads calmly, with colour that
means something, a light and dark theme the learner chooses, and layouts
for phones and tablets as well as desktops. No API and no behaviour
changed: the phase moves, groups and restyles what was there.

## Designed first, in a design file

The interface was designed before it was built, in
[Pencil](https://pen.dev), and the file is kept with the code:
`design/paideia.pen`. It opens only in Pencil. It holds two passes:

1. **A first direction** (indigo on cool grey, rounded cards, a sidebar)
   with its tokens drawn in three palettes, light and dark. It is kept in
   the file as the alternative that was not chosen.
2. **Three editorial directions**, drawn side by side: a print broadsheet
   (newsprint, ink and orange; a serif for headlines and a monospace for
   labels), a Swiss grid (off-white, black and cobalt; a grotesque and
   large numerals) and an instrument panel (aluminium, black and orange;
   counters and switches). Broadsheet was chosen. Paideia is mostly reading
   and citing, and print has conventions for both: an index, a table of
   contents, footnotes, a margin for notes.

Broadsheet is drawn in full: a sheet of components, the nine desktop
screens light and dark, every loading, empty and error state, the forms,
the menus and popovers, ten phone screens, a tablet screen, and a sheet of
the rules for each width. The design was audited once for anything that
looked like a template (repeated labels, boxes inside boxes, numbers
nobody needs) before any code was written.

## Decisions

### Three colours, as variables

The palette has three roles: a newsprint paper, an ink, and one orange.
The rest are tints of the first two: a darker paper for bands and marked
passages, two lighter inks for secondary text and labels, and a hairline
rule. They are CSS variables in `app/globals.css`, named for their role
(`paper`, `ink-2`, `rule`, `accent`), and Tailwind's colours point at
them. No component names a colour or carries a `dark:` variant: a theme is
a change of the variables' values and nothing else.

| Role | Light | Dark |
|---|---|---|
| paper | `#F3EFE6` | `#111110` |
| paper-2 | `#E9E3D6` | `#1B1A17` |
| ink | `#14130F` | `#EDE7DA` |
| ink-2 | `#4A463D` | `#B5AE9F` |
| ink-3 | `#68635A` | `#938D80` |
| rule | ink at 15% | ink at 18% |
| accent | `#E84800` | `#FF5A14` |

Every text and background pairing meets WCAG AA in both themes; the lowest
is `ink-3` on `paper-2` (4.66:1 light, 5.27:1 dark). The orange never
carries small text on paper, where it would fall short. It fills, marks
and underlines, with ink on top of it (4.74:1). The orange square marks
something on its own ("missed on its last answer", a failed job), so it
needs 3:1 against the paper. The international orange first drawn,
`#FF4F00`, gave 2.87:1, so the light theme uses `#E84800` (3.42:1 on
`paper`, 3.07:1 on `paper-2`).

### Auto, light or dark

The masthead offers Auto, Light and Dark. The choice is kept in the
browser's storage; Auto follows the system, and changes when the system
does while the page is open. A small script in the page's `<head>` sets
`data-theme` on `<html>` before the first paint, so a dark page never
flashes light; without JavaScript the system's theme still applies,
through the media query. Tailwind's dark variant follows the attribute, not
the media query.

Rejected: a cookie read by the server, because every page is rendered in
the browser from the API and the server would need state only for this;
and a theme library, one more dependency for about forty lines.

### Type does the work

Three faces, served with the page by `next/font`: Instrument Serif for
headlines, names and numbers; Instrument Sans for reading; JetBrains Mono
for labels, references and figures. Labels are uppercase by CSS, never by
typing, so the words in the page (which tests, screen readers and copied
text see) are written as before. Headlines say a page's point in a
sentence ("Five concepts due today, sixteen new to start.", "Ten stages.
You are on the second."), with numbers in words up to twenty.

### Rules instead of boxes, marks instead of badges

Structure comes from hairline rules and space: no cards, no rounded
corners, no shadows. Coloured badges and icons became typographic marks,
always beside words or explained in a legend: `○` new, `◐` learning,
`◷` due, `●` strong, and the orange square when something needs
attention; `←` builds on, `→` leads to, `⊂` part of, `⊃` parts, `~`
related; `✓` and `✕`; `[+]` for anything that opens in place; section
numbers like `03 /`. Hover is an instant swap: an ink button turns orange,
an underline thickens and turns orange. The keyboard focus ring is orange.

### One frame for every width

An environment's name, its Edit and Delete, its contents and its
background work are one block that takes three shapes:

- from 1,100 px, a column beside the page, the contents as a numbered
  list;
- from 700 px, a header above the page, the contents as a row that scrolls
  sideways when it must;
- below 700 px, a header with a Contents button that opens the contents as
  a full-screen sheet.

It is one navigation with the same link names as before (the numbers are
hidden from screen readers), and the environment's name is the page's one
`h1`. Editing opens the form in place of the name. Deleting is confirmed in
place, in the page's own words, instead of the browser's dialog. The
masthead holds the wordmark, the date, the theme, and the system's health
as one line ("All systems ok", or the first problem with the orange
square) that opens the four checks with the server's reasons.

### Each page, one point and one action

- **Overview:** the headline, the figures between two ink rules, today's
  plan as a numbered list (only the first session's button is an ink
  block), then the stages around you, recent material and background work
  beside a margin with the summary and the map.
- **Materials:** a ruled list of documents with Read text and one menu
  (Summarize, Upload a new version, Try again, Delete). The latest update
  is one line until "What changed" opens it; while it runs, its steps show.
- **Search:** the query set large; scoring on or off; each result numbered
  with its relevance as five squares; the passage opens in its page, marked
  by an orange bar.
- **Knowledge map:** the concepts as a book's index, by letter, each with
  its state and how many relationships it has, beside the entry for the
  one picked: its definition and references, then its relationships in
  rows. On a phone the index and the entry are two views.
- **Roadmap:** a table of contents. The stage you are on is open; any other
  opens in place, or from a link to it.
- **Summary:** the overview as the lede, the key points numbered with their
  references, and a column of sources, documents left out and how it was
  written.
- **Practice:** what is due today as the headline with Start practice;
  concept performance beside the sessions; the stages as a table. A session
  is set as an exam paper, with the marking in the margin.

### What waits behind [+]

How something was made waits behind a `[+]`: how the plan is made, how
relationships are found, how the order is made, how the summary was
written, how practice works. Anything in progress or wrong is never
hidden: a running update shows its steps, a graph or roadmap that is not up
to date says why, and the list of documents whose concepts failed opens by
itself.

### What was merged

Nothing was removed. Three things were folded together:

- Practice's "Needs attention" and "Recently strong" lists repeated notes
  that concept performance already shows, concept by concept. They are now
  only there.
- The Overview's "due for review" figure became its headline.
- The Overview's roadmap shows the stage you are on and the ones either
  side, with how many more there are, instead of every stage.

## Testing

- **Component tests:** 47 pass, 6 of them new, for the theme: Auto by
  default, a choice applied and remembered, a remembered choice shown,
  Auto following a change of the system's theme, a chosen theme not
  following it, and the phone's one button stepping through the three.
- **The end-to-end journey** (record 22) passes. It needed two changes, both
  the new "What changed" click; every role and name it finds was kept.
- **Every page at three widths and both themes** (1280, 834 and 390 px),
  screenshotted against a copy of the development database: no page error,
  and no page wider than the screen. This check found the contents row
  widening the tablet layout by 28 px; it now scrolls instead.
- **Contrast** was checked by a script over every text and background
  pairing of the tokens, in both themes.
- Lint, the type checker and the production build pass.

## Consequences

- The design file is the interface's source: a change to the interface is
  drawn there first. It opens only in Pencil, and it is 3.5 MB.
- Two places differ from the drawings on purpose. The phone keeps the
  Overview's sections open instead of folded behind `[+]`. The phone's
  Contents button sits in the environment's header rather than the
  masthead, which on a phone shows the theme as one button.
- The contents do not show how many concepts are due beside Practice, as
  the drawings do: it would add a request to every page.
- The fonts are fetched when the app is built, as Geist was.
- The screenshots and demo in the README show the interface before this
  phase.
- The maths phases planned in record 24 move by one: reading maths from
  PDFs is phase 26, computed exercises 27, the maths evaluation 28.
