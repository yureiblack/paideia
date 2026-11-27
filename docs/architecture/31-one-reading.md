# 31. One reading: maths and figures read with the document

Date: 2026-11-26
Status: accepted

## Context

Records 26 and 29 had the vision model read a document's maths and figures
only when asked: each had its own tab on the document's page, offering a
range of pages, how long it would take, and a button. A page of maths takes
about a minute, a figure a quarter of a minute, and a textbook hours, so
nothing was read unasked.

Using it on a data mining chapter, the project's owner found two things
wrong:

- **The page was confusing.** A figure read by the model was drawn as its
  picture, then its labels, its tables as the model read them and the
  model's description. Beside it stayed the PDF's text the reading did not
  repeat. A figure not read, or whose reading was refused, was its labels
  as loose lines and its tables as heaps of cells. Some tables were set out
  well and some badly, around the picture, and it was not clear whether
  they were the same table or different ones.
- **Two offers were one too many.** Asking for the maths and the figures
  apart, page range by page range, is work the learner should not have to
  do.

In their words: "Instead of showing the table read by the model as well as
the picture, just show the picture as it is more concrete and also, instead
of giving an option to scan through the maths and figures independently,
scan it all at once when scanning the entire pdf. You should still keep the
model to read the figures as it would help create summaries as well as
practice questions".

## Decisions

### The reader shows every figure as its picture

Every figure the finder of record 29 finds is drawn in its page as its
picture, with its caption, in place of all of its text there. That text is:

- the PDF's text inside it, its labels and cells, out of order;
- its caption;
- or, for a figure read, its passage: what the model read in it.

The text stays in the page for search, summaries and concepts. Only the
reader shows the picture instead. A figure needs no reading to be drawn, so
its picture is there as soon as the text is read.

- **Its text is gathered in one place.** When the document is read, each
  figure's blocks (those whose centre lies within the figure and its
  caption) are moved together, where the first of them was. The page
  records where that text begins and ends.
  - A page whose maths was read keeps no places on the page, and its text
    is the model's: it writes a table's rows out among the prose. There a
    figure's text is its caption's paragraph and the paragraphs on either
    side of it that say only what the figure's own text says, word for word
    and number for number, its LaTeX markup set aside. A caption the model
    set out of order ("Table 2.11. | L∞ distance matrix") is found by the
    figure's name. A paragraph with no word or number, such as a stray
    fence, is the figure's only between two that are.
  - A figure with no text at all is placed where its height puts it.
- **Its picture has an address of its own**, by the document, the figure's
  page and place, and the file's version:
  `/api/documents/{id}/figures/{key}/image?version={sha256}`. A new version
  is a new address, so a browser may keep each picture for good.
- **A one-page picture**, a photograph or a screenshot, is a figure too, so
  its page shows the picture. Its words, read by OCR, are still searched and
  summarised.

### What the model read is a source; its description is not

A figure's passage is its caption, then what is written in it, its labels
and its tables row by row. All of that was checked against the figure's own
text, and every number in it is the figure's. Summaries and concept
extraction now read figure passages like any other, so practice, the
knowledge map and the roadmap are built on them too.

The model's description of what a figure shows is in no passage. It is
still asked for and kept with the reading, and a number in it that the
figure does not show still refuses the reading, but nothing shows it, finds
it by search or is written from it. On the data mining chapter, 9 of 18
diagrams and plots had a misleading mistake in their description: an
invented arrow, a reversed scale, a misplaced point. No check of words and
numbers can find such mistakes, and a summary or a practice question built
on one would repeat it as the book's.

Record 29's stated limit, that a table read from a figure does not feed
practice, is lifted.

### Read with the document, in one chain

Adding a document, uploading a new version and reading one again now queue
this chain:

1. **The text**, read from the PDF's text layer, and by OCR where a page is
   a picture: the document can be read and searched at once, its figures
   already drawn as pictures.
2. **Its maths and its figures**, read by the vision model: one job, one
   step per page that sets maths in maths fonts and per figure, not read
   before for this version of the file, model and prompt. It shows its
   progress as one bar.
3. **The text again**, with what was read in place.
4. **Everything made from it**: its summary, concepts, the environment's
   summary, the knowledge map, the roadmap.

Steps 2 and 3 are left out when the file has nothing left to read. Reading
the document again reads only what was not read. The update record gains a
step for the maths and one for the figures when there are any, saying how
many were read, which pages and how many figures kept the PDF's text, and
how many were not read if the reading stopped. Why each kept the PDF's text
is stored with its reading, but no longer shown: the tabs that listed it are
gone, and in the reader the figure is its picture either way.

Why this order:

- **The text comes first**, so a textbook is readable and searchable in a
  minute rather than in hours.
- **The summary comes once, after everything**, so it is written from the
  maths and figures and not written twice. It waits for them.
- **What to read is found when the reading is asked for**, from the file,
  so the job knows its steps from the start. The upload's answer waits for
  it: 2.4 seconds for the 77-page data mining chapter (37 pages of maths,
  29 figures), 12 seconds for an 873-page calculus textbook. It runs off
  the server's event loop, so other requests are answered meanwhile.

### Cancelling the maths and figures skips them

Cancelling the model's job stops it before its next page or figure, as
before. Unlike other jobs, the chain after it goes on with what was read:
the text is read again with the pages and figures read so far, and the
summary is written. The update says how many were not read, as the reading
stopped. Reading the document again later reads the rest.

Cancelling the reading of the document itself still cancels everything
after it.

### The offers are gone

The Maths and Figures tabs, their items in the Materials menu, and the API's
`GET` and `POST /api/documents/{id}/maths` and `/figures` are removed. An
address that still names one of the tabs opens the text. Updates recorded
before this one still say "Read the maths of" and "Read the figures of".

## Testing

- **A table's reading that leaves out most of its numbers** keeps the
  PDF's text when the table is read with its upload: the check that a
  table's reading gives at least 80% of the numbers its PDF text sets,
  added to record 29's reading the day before.
- **Placing a figure in its page**, against hand-made pages:
  - a figure read takes the place of its caption and of the labels its
    reading repeats;
  - text it leaves out stays beside it, inside its place;
  - its passage never holds the description;
  - a figure not read gathers its own text, leaving out the paragraph
    beside it in the other column;
  - on a page whose maths was read, the caption's paragraph and, built
    from page 6 of the data mining chapter as the model wrote it out, each
    table's rows, a caption set out of order, a subscripted corner (L_1),
    and prose and a fence left out;
  - a figure with no text is placed by its height;
  - two figures on a page each have their own place.
- **The API, end to end, with a scripted model** that answers each figure
  by its picture:
  - every figure and maths page is read with the upload, then the text
    again, then the summary;
  - a document with neither is read as before;
  - every figure is a place for its picture, read or not, and its picture
    is served for its version only;
  - a figure's passage is found by search and read by the summary;
  - refused readings keep the PDF's text and the update says why;
  - reading the document again reads nothing twice;
  - a new version is read afresh;
  - cancelling the maths skips it, the chain goes on, and reading the
    document again reads what was left;
  - cancelling the document's reading cancels it all;
  - the model unreachable leaves the text readable, and says so in the
    model's own words.
- **The page:**
  - a figure is drawn as its picture alone, at its version's address, in
    place of its text, which is not shown;
  - a figure with no text is drawn where it stands;
  - the document's page has two tabs, and an old address opens the text;
  - the maths and figures being read show one bar, before the jobs after
    them in the chain;
  - the menu offers neither.
- **The end-to-end journey:**
  - a lecture's maths is read with its upload;
  - another lecture's figure is read with its upload and shown as its
    picture, its labels hidden;
  - what the model read in the figure is found by search;
  - a photograph of a board note is shown as itself and found by its words.

### In the running app, with the real model

The check ran on a stack of its own, with ministral-3:8b on an Apple M3 Pro,
on six pages of the data mining chapter: three pages of maths and eight
figures, among them Figure 2.15 and Tables 2.8 to 2.11, the page that showed
the problem.

- **The chain:** the text could be read 2 seconds after the upload, its
  figures already drawn as pictures. The model read the 3 pages and 8
  figures in 4 minutes 20 seconds, all accepted. The text was read again in
  2 seconds, and the summary, concepts, map and roadmap took 3 minutes 10
  seconds more: 7 minutes 40 seconds in all.
- **Sources:** no passage held a description. One of the summary's key
  points cited Figure 2.1, and the concept "Feature subset selection" was
  found in the flowchart of Figure 2.11.
- **The first page whose maths was read** showed each table as its picture
  and, below it, the table's rows again, as the model had written them out
  in the page's text. That led to the rule above. Read again, page 6 had no
  table row left outside its picture.
- **In the browser,** at 1280 and 390 pixels: the plot and the four tables
  as their pictures, the prose after them, two tabs, nothing scrolling
  sideways, no error in the console and no failed request.
- **Seen, not changed:** the picture of Figure 2.15 cuts its y axis's
  numbers at the left edge, as the finder draws the figure; and the model's
  transcription of the page begins and ends with a stray code fence.

## Consequences

- One upload reads everything. A lecture of a few pages with a few figures
  takes a few minutes more before its summary. A textbook takes hours, as
  record 26 measured, though it can be read and searched from the first
  minute. The machine works for all that time. Cancelling the maths and
  figures keeps what was read and lets the rest go on.
- A figure is the picture the book prints. Its words and its tables, read
  and checked, serve search, summaries, concepts and practice.
- The model's descriptions of figures are no longer seen or used at all.
  Asking for them costs time in every reading. Dropping them from the
  prompt is a new prompt version, which would read every figure again, so
  it is left for a measured change.
- A document read before this record keeps its pages as they were, its
  figures' passages with their descriptions, until it is read again.
  Reading it again from its menu reads its maths and figures, puts the
  pictures in place, and leaves the descriptions out.
- Records 26 and 29 are changed by this one in when they read (with the
  document, not when asked) and in what the reader shows. Record 29 is also
  changed in what is a source: what is written in a figure is, its
  description is not.
