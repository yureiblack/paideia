# 29. Reading figures, tables and scans

Date: 2026-11-23
Status: accepted; changed by [31](31-one-reading.md): figures read with the document, shown as their pictures, and what is written in them a source, their descriptions in no passage

## Context

A PDF's text layer keeps a figure's words and nothing of what it draws.

- A plot leaves its tick labels in a heap, and a flowchart its box names in
  no order. A table keeps its cells, but column by column, its rows lost.
- A scanned page, a photograph of a board or a screenshot keeps nothing at
  all. Record 03 left these out of scope: such a document was read with no
  text, and the page said it might be a scan.

The learner who asked for this phase put it plainly: being able to read
pictures, diagrams and screenshots matters more than reading slides. A slide
deck exported as a PDF is a PDF already.

This phase reads them in two ways:

- **Tesseract**, an OCR program, for pages that are pictures of text. It is
  fast and makes nothing up: it reads what is there or misses it.
- **The local vision model** (record 26) for figures and drawn tables. It
  can say what a figure shows, and it makes real mistakes.

It also fixes four faults in record 26's check that the same tests found.

## What the prototype showed

The prototype used chapter 2 of a data mining textbook (77 pages, not
committed), with its plots, tables, diagrams, a flowchart and a map, and
two chapters of a linear algebra textbook.

- **OCR.** Pages drawn as pictures, as a scanner makes them, were read in
  about a second each:
  - prose: 99.6 to 100% of words right;
  - a page of maths: 97%, its subscripts lost (pij read as "pis"), so maths
    still needs the model;
  - tables: 91 to 97%, losing rotated column names and white text on dark
    cells.
- **The figures' own text.** The model copied labels and table cells almost
  without fault. Figure 2.2, four tables of about a hundred cells, came back
  with every cell right but one word ("Marited"). The text layer had those
  cells too, column by column; the model gave the rows.
- **The descriptions** had a wrong detail in about half the figures:
  - a point placed at x = 4 instead of 3;
  - a grid of 3 by 7 plots called 3 by 9, its rows mislabelled;
  - the gaps marked on a plot read as points;
  - a benzene ring's atoms "alternating" black and white.
- **A check on numbers alone** caught one of those, the 3 by 9. A misplaced
  number passes, because it is somewhere in the figure.
- **Finding figures.** The drawing detector of record 26 missed a figure of
  thin lines; found by its caption, all twelve were found.
- **Record 26's check** refused five of eight maths pages. One refusal was
  right: the model rewrote 3∗3 as 3² and added a calculation of its own.
  The other four were faults in the check (below).

## Decisions

### Scans and pictures: read by Tesseract, by themselves

A page with fewer than 20 characters of text and a picture over half of it
is read by Tesseract when the document is read, through PyMuPDF, which
returns what it read in the same form as a PDF's own text. The parser
handles the page as any other. It takes about a second a page, so it is not
offered: it simply happens.

- `documents.pages_ocr` counts the pages read this way, and the page says
  how many, so the learner knows which text a program read.
- Tesseract is a program of its own (docs/setup.md). Without it, or with the
  `OCR` setting off, a scanned page keeps no text, as before.
- Its language is a setting (`OCR_LANGUAGE`, English by default), as is the
  resolution it reads at (300 dpi).

### Pictures are uploaded and stored as one-page PDFs

An upload may be a PDF, a PNG or a JPEG, told apart by the bytes it begins
with, never by its name. A picture is made into a one-page PDF as it arrives:

- turned upright as the camera recorded it (its EXIF orientation);
- set on a page as wide as A4, never taller than a PDF page may be;
- written without a fresh file id, so the same picture always makes the
  same PDF, and a picture uploaded twice is found to be a duplicate.

The PDF is what is stored and fingerprinted. Everything after the upload
reads PDFs only, as before. The page is a picture, so Tesseract reads it.

### Figures are found by their captions first

A caption is a block that begins "Figure 2.1.", "Fig. 3:", "Table 4 -" and
the like: the number followed by punctuation, so "Figure 2.15 shows" begins
a paragraph about a figure and is no caption.

- **What is drawn** is found as record 26 found it: drawing clusters and
  pictures at least 15% of the page wide and 8% high, joined when they
  touch. A picture covering most of its page is the page itself, scanned,
  unless the document is one page: an uploaded picture.
- **A framed box of text** is a drawing mostly filled by a paragraph, and
  is no figure. A paragraph is 25 words or more, most of them words: a
  table's cells and a sequence of letters are not one, however long.
- **Each drawing goes to a caption.** By convention a figure's caption is
  set below it and a table's above it. Each drawing goes to the caption on
  that side that it overlaps most, with no paragraph or other caption
  between them; then the drawings beside it in the same row. A caption with
  nothing on its own side may then take what is on the other.
- **A figure of thin lines** (record 26's detector found no cluster large
  enough) is found from its caption alone: whatever is drawn or written
  between the text above and the caption.
- **Captions and cells.** PyMuPDF can set a table's cells in the same block
  as its caption. A caption's lines are those in the caption's own type
  size; a caption continued on a line of its own joins it only in that size.
- **The figure** takes in its labels: short blocks within it, beside it, or
  just above it, such as a row of plot titles.

On the data mining chapter all 29 figures and drawn tables were found, each
with its caption; on the two linear algebra chapters, all 20, and one
uncaptioned drawing. Finding them takes under a second for a document.

### Reading a figure: four parts, checked part by part

The figure is drawn with its caption at 200 dpi and given to the model with
the prompt `figure_reading/v1`. Its answer comes in four parts, each named
in capitals on a line of its own:

- **KIND**: plot, chart, diagram, flowchart, table, map, photograph…
- **TEXT**: every label, number and title written in the figure, one per
  line, as written.
- **TABLE**: any table in Markdown, every cell as written.
- **DESCRIPTION**: what it shows, in three to six sentences.

The parts are treated differently, because the prototype showed they
deserve different trust.

- **What it says is written in the figure** (text and tables) is compared
  with the figure's own text: the PDF's text inside it, its caption, and
  Tesseract's reading of its picture. A few words may differ, two or 5%,
  whichever is more, as OCR misreads and the model mends a typo. A long
  word joined in the picture and set apart in the PDF ("new_value", "new
  value") counts as found.
- **Every number it gives**, in any part, must be one of the figure's own.
  A number the figure does not show is made up: a coordinate guessed, a
  grid miscounted, a range of years the axis only abbreviates.
- **The description cannot be checked further.** It is kept, shown and
  searched, always as the model's (below).

A reading that disagrees is asked for once more at the retry temperature,
which gives a different answer; if that disagrees too, the figure keeps the
PDF's text and the reason is shown. A part named bare must be in capitals,
since a figure of kind "table" writes that word under KIND.

The model does not always put a table under TABLE. For a figure of four
tables it repeated the four parts for each, and wrote each table under TEXT:
its header cells as lines of their own, a rule, then its rows between bars.
Rows between bars are read as a table wherever they are, and the lines just
before them as its header when there are as many as the first row has cells
(or one fewer, under a header with an empty corner, when the rows are named
in their first cell). A table written one cell to a line, with no bars,
stays a list of what is written: checked all the same, shown as a line.

### A figure is a passage of its own, and never the source of anything else

When the document is read again, each figure read takes its place in its
page as one paragraph: its caption, what is written in it, and "Described
by the model:" with its description. The chunker makes it a passage of its
own (with any headings just before it), and the passage records which
figure it is.

- **Search finds it**, and a result shows the figure's picture.
- **The reader** shows the picture in its place in the page, its caption,
  its text, its tables as tables, and the description under a label saying
  it is the model's, to be checked against the picture.
- **Nothing is written from it.** Summaries and concept extraction read the
  passages that are not figures, so neither does anything built on them:
  the environment summary, the knowledge map, the roadmap, practice. A
  model's description is never a source.
- **Nothing of the PDF's text is lost.** A text-layer block inside the
  figure gives way to the reading only where the reading repeats it, word
  for word and number for number; the caption always does. The first
  calibration showed why: the model read a distance matrix as "p1, p2, p3,
  p4" and left out its numbers, and they would have gone from the page.
  Tick labels the model skipped stay too.
- On a page whose maths was read, which keeps no places on the page, the
  figure takes the place of its caption's paragraph, or else goes at the
  page's end.

Stated limit: a table read from a figure serves search and reading, not yet
practice, since its passage carries the description too.

### Offered for a range of pages, kept per version, one step per figure

As for maths (record 26), and by the same machinery:

- The document's page has a Figures tab, reached from the Materials menu
  ("Read the figures"). It offers a range of pages, says how many figures
  and how long, and lists the figures that kept the PDF's text and why.
- The estimate is the median of the last 50 figures read, or 20 seconds
  before any has been.
- A reading is a job on the model lane, one step per figure; it shows its
  progress and stops between figures when cancelled. Each step carries its
  figure's place and caption, so a textbook's figures are not found again
  for every step.
- Readings are kept per version of the file (`figure_readings`), by the
  figure's page and place, the model and the prompt. A cancelled reading
  carries on from the figures it read; a new version starts again.
- The last step puts the document back in the queue to be read; the chain
  after it redoes only what changed (record 17). Summaries do not change,
  since they never read figures.

### Four faults in record 26's check, fixed

The same chapter's maths pages showed them. Each refused a faithful page:

- **The margin band.** The check set apart the lines in the top and bottom
  7% of a page as the running header and footer, and dropped them from the
  transcription only when they matched exactly. A book with no running
  header has its first or last line there; the model wrote it with LaTeX,
  it no longer matched, and it counted as added. Those lines are now
  optional: the transcription may have them or not.
- **Tables in Markdown.** Each dash of a table's separator row counted as a
  minus sign. A table now becomes one paragraph per row, its separator row
  dropped, a bar inside a formula (|x − y|) never taken for a cell's edge.
- **Equation numbers and footnote marks.** "(2.1)" at the end of a line,
  and a star or dagger after a word ("Divergence∗"), change no maths and
  are optional. A star after a single letter is maths (x∗) and is not.
- **Subscripts written as HTML.** The model wrote L<sub>1</sub>; the angle
  brackets counted as operators. The tags are dropped, their text kept.

And one improvement the live check led to: a figure's labels are optional in
a transcription wherever the figure finder puts them, not only inside the
drawing. A plot's tick labels sit beside its axes, outside the drawing, and
were required; a page whose model skipped them was refused for their digits.

On the chapter's five refused pages, the four fixes accept four; the one
real misreading is still refused.

## Testing

- **Finding figures** (a PDF built in code, laid out as a textbook sets its
  figures): a figure with its labels and caption, the two parts of one
  figure, a table's caption above it, a figure of thin lines found by its
  caption, and no figure for a paragraph about one, a framed box or a
  scanned page, except a one-page picture.
- **Reading a figure, pure:** the four parts however their names are set; a
  bare part name in capitals only; tables as rows with their titles; the
  caption written again left out; numbers compared as values; a made-up
  number refused in any part; a few words tolerated, more refused; a
  picture with no text checked for numbers only; the passage marking the
  description as the model's.
- **Placing a figure in its page:** in place of its caption and the labels
  it repeats; text it leaves out kept; on a page whose maths was read, at
  its caption's paragraph, or else at the end.
- **The chunker:** a figure a passage of its own, with the headings before
  it.
- **The API, end to end with a scripted model:** the offer with captions
  and estimate; a faithful reading in place in its page; the figure a
  passage of its own, found by search and left out of the summary's
  passages; its picture served; a made-up number asked again, then the page
  keeps its text with the reason; a second answer accepted; a table read as
  rows; figures read already, documents not read and pages outside the
  document refused; a reprocess keeps the figures.
- **OCR and pictures:** a scanned page read, and not read with OCR off; a
  page of text with a picture on it is no scan; a PNG and a sideways JPEG
  uploaded, stored as PDFs and read upright; the same picture twice is the
  same file; a GIF and a broken PNG refused.
- **The maths check's four fixes**, each with the page that showed it.
- **Tables under TEXT** (the live check's finding): header cells set as
  lines, rules, an empty corner.
- **Labels beside a drawing** are optional in a transcription.
- **The page:** the Figures tab and its offer, a figure drawn in place with
  its picture, tables and marked description, a search result for a
  figure, and pictures accepted by the upload.
- **The end-to-end journey** gained a step: a lecture with a captioned
  chart has its figures read from the Materials menu, and the page shows
  the figure and its description; a photograph of a board note is uploaded
  and its text read.
- **Deliberate breaks.** 35 were made in the new code. The first run caught
  26 of 32, and one never ran, its pattern stale. The five it missed were
  gaps in the tests: short scraps of words found in the joined text, a
  refused reading put in place by a later reading of the document, a
  figure's picture served from another version of the file, asking again
  ignored by the provider (which had no test of transcription at all), and
  the count of pages read by OCR not stored. Tests were added for each.
  Three more breaks were made for the live check's fixes. All 35 are
  caught.

### In the running app, with the real model

The check ran on a stack of its own, with ministral-3:8b and Tesseract on
an Apple M3 Pro. Four files were made from the data mining chapter: pages 4
to 20 (eight figures and drawn tables), pages 49 to 62 (its maths), pages 21
to 23 drawn as pictures (a scan), and page 36 as a screenshot (a PNG).

- **The scan and the screenshot** were read as they arrived. Tesseract read
  the scan's three pages at 99.8, 100 and 99.8% of the words, and the
  screenshot at 96.8%, missing only its flowchart's labels. The scan's
  summary was written from what it read; before this phase it would have
  had no text to summarise.
- **The figures of pages 4 to 20,** read from the Figures tab: all eight
  accepted, seven at the first asking and one, the figure with a DNA
  sequence, at the second. A figure took 11 to 63 seconds, 19 at the
  median. Search found them, with their pictures, and the summaries and
  concepts were written as before, from the other passages.
- **Tables written under TEXT.** The page showed the four tables of Figure
  2.2 as one long line of cells, bars and rules: the model had written them
  under TEXT. They are now read as tables wherever they are written (above),
  and read again, the figure showed four tables, every cell right.
- **The screenshot as a figure.** A one-page picture is offered as a figure.
  Its nine labels were read exactly; its description put the flowchart's
  steps in the wrong order, which the cropped figure in calibration had
  right. That is the description the reader is told to check against the
  picture, and nothing is written from it.
- **The maths of pages 49 to 62:** 8 of 14 pages accepted. The four pages
  the faults had refused were all accepted, and the one real misreading
  (3∗3 written as 3²) still refused. Of the others, two had LaTeX outside a
  formula and one a digit added; one, of four distance tables, added 59
  digits. The last, a plot, missed digits that turned out to be its tick
  labels, set beside the axes and so required: a figure's labels are now
  optional wherever the figure finder puts them. Read again, its digits
  agreed, and it was refused on 11 letters, three more than allowed.
- **In the browser:** the reader, the Figures tab, a search for a figure,
  and a phone in dark mode, with no error in the console and no failed
  request.

## Consequences

- A scanned document, a photograph or a screenshot is now read, where it
  used to arrive empty. Its text is a program's reading, and the page says
  so.
- Figures and drawn tables can be searched and read in place, with what is
  written in them checked and the rest marked as the model's.
- The model's descriptions are never a source: no summary point, concept,
  map link, stage or practice item rests on one. The cost is that a table
  read from a figure does not yet feed practice.
- Tesseract is a new system dependency, installed apart from Python, in CI
  too. Pillow, already installed with the embedding packages, is now named
  as a requirement of the app's own.
- Reading figures costs a quarter of a minute each, on demand. A textbook's
  few hundred figures take an hour or two, read chapter by chapter.
- Records 03 (OCR out of scope) and 26 (the margin band, tables, equation
  numbers and HTML in the check) are changed in those respects by this one.
