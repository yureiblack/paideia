# 28. A refined interface: reading first, and a way in

Date: 2026-11-22
Status: accepted

## Context

Record 25 gave Paideia its look: newsprint, ink and one orange, a serif for
headlines, a monospace for labels, structure from rules instead of boxes.
Used for a while, the interface showed four problems:

- **Reading was tiring.** The serif carried whole sentences: a summary's
  opening in 44 px display type, a concept's definition at 28 px, every
  standfirst in italics. Dates, sizes and intervals were set as 10 px
  uppercase monospace ("EVERY 1 DAY · NEXT 13 NOV"). Search results ran to
  about 130 characters a line.
- **Everything showed at once.** The Overview had a headline, four figure
  tiles, today's plan and five more sections of equal weight. The contents
  were seven equal rows, with Edit and Delete under the environment's name.
- **There was no way in.** A first visit met an empty list. Nothing said
  what an environment is, what happens after an upload, or where to start.
  Home listed environments with figures but could not say where you had
  left off.
- **A document could not be read on its own.** Its text, summary and maths
  opened as folds inside a row of the Materials table.

The aim was to keep the identity and change who does which job: the serif
names things, the sans carries every sentence, the monospace only labels.
Each page should show one thing first and fold the rest. Nothing the
interface could do before was to be lost.

## Designed first, again

The refinement was drawn in Pencil before it was built, in the same design
file as record 25. The file now holds only the final interface, in five
rows:

- **Foundations:** the type roles and the six rules for every page, the
  components, the three widths, and an audit against the twelve questions
  of the brief.
- **Desktop:** sixteen screens, light and dark.
- **Tablet and phone:** a tablet screen, twelve phone screens, six in dark.
- **States:** empty states and notes, loading and error, forms, menus and
  popovers, light and dark.

The earlier passes of record 25 (the first direction, its palettes, the
editorial directions and the first Broadsheet screens) were deleted from
it, and its variables were reduced to the eleven Broadsheet tokens, light
and dark.

From this phase on, the design file is kept outside the repository: it is
the designer's working file, and `design/` is ignored. Record 25 says it is
kept with the code; that no longer holds. Its versions up to this phase
remain in the repository's history. What it decided is written here and in
record 25, and built in `web/`.

## Decisions

### One job for each face

| Role | Face and size | Used for |
|---|---|---|
| Headline | Instrument Serif 44–76, two lines at most | Page headlines |
| Title | Instrument Serif 24–40 | Documents, stages, concepts, plan items |
| Lead | Instrument Sans 20–22 | A summary's or a definition's opening sentence |
| Reading | Instrument Sans 18, line 1.7, at most 640 px | Document text, summary points, passages |
| Interface | Instrument Sans 15–16 | Explanations, options, forms, notes |
| Detail | Instrument Sans 13, the second ink | Dates, sizes, intervals, sources |
| Label | JetBrains Mono 11, capitals | Kickers, folios, buttons, counts, status words |

No label is smaller than 11 px. The orange marks things and is never the
colour of small text: at 3.4:1 on the paper it passes for a mark, not for
words. The environment's own description keeps the italic standfirst; every
other sentence is in the sans.

### Contents in three parts

The contents are grouped by what they are for: the **Overview**, where a
visit starts; the **Library**, what the material says (Materials, Summary,
Knowledge map, Search); and **Learn**, what to do with it (Roadmap,
Practice). The numbers stay, as folios, and follow the new order: Summary
is now 03, Search 05, Roadmap 06. Edit and Delete move behind a ••• menu
beside the environment's name, still one click away. Under the name, one
line says how many documents and concepts there are. The masthead gains a
link to the guide.

### Home starts where you left off

Home opens on the environment opened last in this browser, or else the one
changed last. It shows the first session of that environment's plan, with
its reason and its Start. Beside it is the document read last, at the page
where reading stopped. The index of environments follows, one line of
status each: today's plan, and the documents or how many are still being
read. New environment becomes a secondary action.

With no environment yet, Home welcomes instead. It says what Paideia does
in one sentence, shows the five steps (organise, add, build, learn,
return), offers one action, Create your first environment, and links to
the guide.

### A guide, and notes once per place

The guide (`/guide`, from the masthead) explains the five steps. Each sits
beside an excerpt of the interface drawn with the same type. The excerpts
are pictures: hidden from assistive technology, which hears the step's own
words, and nothing in them can be pressed.

Six places explain themselves the first time they are opened: a new
environment, the first upload, the summary, the knowledge map, the roadmap
and practice. A note sits beside what it explains, marked by an orange
rule like a note in a printed book. It blocks nothing, and Got it puts it
away for good. The guide counts the notes put away and can show them
again. What is put away, the environment opened last and the page read
last are kept in the browser's storage. They are conveniences, not data:
without storage they last for the visit.

### Each page shows one thing first

- **Overview:** today's plan. The four figure tiles become one line under
  the headline. The roadmap, recent material, summary and map sections
  become one index, "In this environment", with one line each, grouped as
  the contents are. Activity is folded to its last line. An environment
  with no documents opens on "Start with a PDF.", with an upload band and
  what follows on its own.
- **Materials:** adding and opening documents. Read leads to the
  document's own page; while a document is being read, its row shows the
  steps of the chain (reading, summary, concepts, map, roadmap) and where
  it is.
- **Document (new):** reading. Its text, its summary and its maths are
  three tabs of one page, at most 640 px wide, with page folios and an
  index of pages. The contents rail stays hidden until Show contents. A
  breadcrumb leads back. The page read last is remembered for Home.
- **Summary, knowledge map, search, roadmap, practice:** the same rules.
  The summary's opening is a lead in the sans, the map's definitions are
  in the sans, search results are held to about 660 px, roadmap sources
  are written out in full, practice details are in the sans.

### Empty says what comes

Every empty place says, in one sentence, what will appear there, offers
the one action that makes it appear, and adds a hint only when it helps.
A search that finds nothing says so plainly and suggests what to try.

## Testing

- **Components:** 93 tests (62 before), among them new ones for:
  - the browser's memory: notes put away and shown again, the last
    environment and page, unreadable values ignored;
  - the note;
  - the grouped contents: groups, numbers, a document's page counted as
    Materials;
  - Home: the welcome, Continue from the environment opened last or changed
    last, Keep reading;
  - the document page: tabs, breadcrumb, pages as regions;
  - Materials, the summary and search.
- **The end-to-end journey** keeps its fourteen steps and checks the new
  way through:
  - it starts at the welcome and creates the first environment from it;
  - the new environment opens on "Start with a PDF." with its note;
  - the overview's index says "2 documents, all read.";
  - a document's maths is offered on its own page, opened from the
    Materials menu, and its formula is typeset there;
  - on that page the contents stay hidden until Show contents.

  It passed in 40 seconds.
- **Every page in a browser:** Home, the overview, Materials, a document
  (text, summary, maths), the summary, the map, search, the roadmap,
  practice and the guide were opened at 1280 px light; five of them in
  dark, and five at 390 px with the contents sheet. There were no console
  errors and no failed requests. Every page was checked against its
  drawing.
- **Contrast:** the orange is no longer the colour of any text. The
  numbers in an exercise's wrong cells, which were orange, are now in ink,
  struck through in orange.

## Consequences

- **The order of the contents changed.** Anyone used to Search at 03 finds
  it at 05; the numbers follow the groups.
- **Reading happens on its own page.** Materials no longer opens a
  document's text, summary or maths inside the table; its menu leads to
  the document's page instead.
- **Some things are remembered per browser:** the notes put away, the
  environment opened last and the page read last. Another browser starts
  afresh, and clearing site data shows the notes again.
- **The README's screenshots show the interface of record 25.** They are
  taken with the real model on a stack of their own (docs/demo.md) and are
  to be redone separately.
- **Not drawn from the design:** the session's "← Practice" link (Stop here
  remains), "03 / 10" in a session (it stays "3 of 10"), and a time
  estimate on Practice, for which there is no data.
