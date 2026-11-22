# 26. Reading maths from PDFs

Date: 2026-11-21
Status: accepted

## Context

Record 24 made maths written as LaTeX render, and found the problem this
phase solves: a PDF's text layer keeps the prose but loses the maths. A 3 by
3 matrix of halves comes out as a row of numbers, λ² as "λ2", and the
brackets drawn around a matrix as nothing at all. The local model,
ministral-3:8b, can read a page's image and write it out with its maths in
LaTeX, but it makes mistakes. Record 24 settled the outline: the model reads
maths pages, the backend checks each one against the PDF's own text, and
reading is never automatic.

This phase makes that work. A document's maths reaches its passages as
LaTeX, so summaries, concepts, practice and search all see real formulas.

## What the prototype showed

The prototype used Interactive Linear Algebra again (455 pages, not
committed), on 11 pages chosen from light, medium and heavy maths.

- **Which pages hold maths.** The PDF names its maths fonts. 386 of the 455
  pages set at least 10 characters in them. A textbook is maths on nearly
  every page.
- **Time.** A page took 35 to 55 seconds on an Apple M3 Pro, 46 on average.
  The whole book would take six to seven hours.
- **A sharper image does not help.** The model scales every image to the
  same budget: a page used 1,662 tokens at 110 and at 150 dots per inch, and
  a page read again at 150 came back with the same mistake.
- **The mistakes are real.** On 11 pages:
  - a worked example replaced by "The answer is", its matrix and cofactor
    expansion gone;
  - a plus sign lost from a matrix row;
  - a wrong matrix;
  - the zeros of a diagonal matrix, and some ∗ entries, left out;
  - a digit in an exponent changed, perhaps a typo of the book's corrected;
  - a word dropped;
  - `\mathbb{R}^m` written outside a formula;
  - the second half of a page beginning "Here is the transcription of the
    provided textbook page".
- **Counting characters finds them.** Reduced to their digits, letters and
  operators, a faithful transcription and the text layer have the same
  counts, once the layer's quirks are understood. Every mistake above
  changed a count.
- **Halves do help.** Read again as two halves, each seen larger, a page
  that failed often passed. After one such retry, 7 of 10 pages were
  accepted, and the other 3 still had real mistakes.
- **Quoting maths can be checked too.** Summaries and practice items written
  from accepted pages had 114 formulas. 105 were in the passages as written.
  The rest were harmless symbols, an equation of the model's own, a correct
  restatement in other notation, a simplification that dropped factors of
  (−1)³⁺¹, and changed equations.

## Decisions

### Offered for a range of pages, never automatic

Reading costs about a minute a page, so the Materials tab offers it from a
document's menu. The offer shows:
- how many pages set maths;
- a range of pages, the whole document by default;
- how many pages in that range are still to read;
- how long that should take.

The estimate is the median time of the last 50 pages this machine read,
or 65 seconds before it has read any. The roadmap asked for an offer per
document. A range was added because a textbook takes hours, and a learner
reads it chapter by chapter.

### Maths pages are found by the fonts the PDF names

A page holds maths when it sets at least 10 characters in a maths font:
- TeX's own fonts;
- any font with "Math" in its name;
- STIX and XITS, MathTime and MTPro, and Symbol.

Fewer than 10 is a stray symbol in prose, not worth a minute of the model.
Finding them takes 2.4 seconds for 455 pages, so it is done when the offer
opens, not stored.

A PDF that draws its maths as pictures, as a scan does, sets no maths font
and has no text layer to check against. Its maths is not offered.

### Each page is read whole, then once more in two halves

A page that fails its check is read again, cut in two at the gap between
blocks of text nearest its middle. Each half is drawn at 150 dots per inch,
where the whole page is drawn at 110. A page that fails again keeps the
PDF's own text, and the reason is kept with it.

The model is called without the JSON format other calls use. Record 24
found that LaTeX inside JSON strings came back damaged. A new provider
method, `transcribe`, sends the image with the prompt and returns plain
text. Its retries and error messages are shared with `generate_structured`.

### A page is checked by what it shows, not by its LaTeX

`app/transcription.py` makes the model's Markdown into page text:
- headings become heading blocks;
- emphasis, quotes and rules are taken out of the prose;
- each list item becomes a paragraph, as in the text layer;
- a first sentence of the model's own is dropped, from each half of a page
  read in halves;
- the running header is dropped;
- formulas move to the stored form.

A page is unusable if any LaTeX is left outside a formula, or if any formula
would not render.

The page is then compared with the text layer. Both are reduced to the
digits, letters and operators they show (`maths.shown`):
- a formula counts as the characters it draws;
- `\lambda` counts as λ, `\neq` as ≠, `\frac{1}{2}` as 1 and 2;
- `\det` counts as its three letters.

The rules:
- **Digits and operators must match exactly.** A changed sign or a lost
  entry changes the maths.
- **Letters may differ by 1%, and at least 3.** The model drops a word now
  and then, or corrects a typo of the book's, and that changes no maths.
- **The running header and footer are left out of both:**
  - They are the lines in the top and bottom 7% of the page, the band the
    parser already uses.
  - Only surplus copies are dropped from the transcription. A section
    heading can read exactly like the running header.
- **Figure labels are optional.** Short text, 60 characters at most, inside
  a large drawing or picture (at least 15% of the page wide and 8% high)
  may be left out. Longer text there is a framed box, and must be there.

What only looks different in a text layer is read as what it is:
- an equals sign under a separate stroke is ≠;
- the star operator is `*`, and `\cdots` is three dots;
- big operators in the extension fonts are left out, since a summation
  sign reads "X";
- lowercase letters in a symbol font laid out as TeX's are left out, since
  that layout puts symbols in their places, and a square root reads "p";
- a run of minus signs ending in an arrow is one long arrow, as drawn over
  a row operation;
- matrix cells holding only a dash or a bar are a rule the book draws;
- a hyphen inside a word, or at the end of a line, is not a minus.

### Kept per version of the file, put in place by reading the document again

Each page read is a row of `page_transcriptions`, for the document's
current file (its SHA-256), the model and the prompt version. An accepted
row keeps the page's new text and its paragraphs; a rejected one keeps the
reason.

The reading's last step puts the document back in the queue to be read.
Reading it uses every accepted page in place of its text layer, and the
chain that follows redoes only what changed, as any change does (record
17). Unchanged pages keep their passages and embeddings. A later reprocess
keeps the maths. A new version of the file is never read with another
version's pages, and its maths is offered again.

### One step per page: progress, cancelling and carrying on

A reading is three jobs, chained as an upload's are:
1. Reading the pages, on the model lane. This job has one step per page and
   then the step that puts the pages in place.
2. Reading the document.
3. Everything derived from it.

One update record follows them all. Its first step, "Reading the maths",
counts the pages read and the pages that keep the PDF's own text as they go.

Because each page is a step:
- the job shows its progress;
- cancelling stops it between pages;
- cancelling it cancels the two jobs waiting on it.

So a cancelled reading changes nothing. The pages it read are kept, and the
next reading uses them without asking the model again. If the model cannot
be reached, the job is tried again later, as any job is (record 21), with
the model's own reason ("Is Ollama running?") instead of a general one.

### Passages are never cut inside a formula

The chunker splits a paragraph longer than 1,200 characters at sentence
ends, or at the last space that fits. With LaTeX in the page text, "= 0. \]"
ends a sentence inside a formula. Both cuts now skip formulas. The one
exception is a single formula longer than the limit.

### The model may quote maths, never work it out

Record 24 checked that a formula renders, not that it is right. Now maths
in anything the model writes must come from what it was given (sources).
`maths.unquoted(text, sources)` looks each formula up by what it shows:
- A formula with a digit or an operator must show exactly what some stretch
  of the sources shows, spacing and layout aside.
- A formula of symbols alone, like `v_i` or `(i, j)`, needs only symbols
  the sources show.

It compares what formulas show, not their LaTeX, because a document read
from its text layer has its maths as prose. A summary quoting "n − 1" as
`\(n - 1\)` quotes it correctly.

Where it applies:

| Written | Sources | What happens to maths not found |
|---|---|---|
| A document's summary | Its passages | A key point is dropped; the overview is asked for again |
| The environment's summary | The documents' summaries, without their citation numbers | As above |
| Concepts | The passages given | The concept is dropped |
| Practice items | The passages given | The item is dropped, with its reason |

Wrong options of a multiple-choice item, and a statement meant to be false,
are exempt: they are written to be wrong.

`sources` is a required argument everywhere the rule applies, so no caller
can skip it by leaving it out.

Replayed over the prototype's 114 formulas, the rule flags exactly the 7
that were made up, worked out, changed or restated, and passes the harmless
symbols.

## Testing

- **The page, pure:**
  - Markdown made into page text and blocks;
  - every mistake the prototype found refused;
  - every quirk of the text layer read as what it is, long labelled arrows
    included;
  - a sentence of the model's own dropped, from either half;
  - letters within 1% tolerated, more refused;
  - figure labels optional;
  - order not seen, pinned as a known limit.
- **The PDF:**
  - maths found by font and only above the threshold;
  - the running header set apart;
  - a figure's labels optional and a framed box not;
  - a square root in a symbol font, and a summation sign in an extension
    font, left out;
  - page images, whole and in halves;
  - the cut between lines.
- **The reading, end to end through the API, with a scripted model:**
  - the offer and its estimate;
  - a faithful page put in place in its page and passages;
  - a page that disagrees twice keeps its text, with the reason;
  - a page that passes on its halves;
  - a reprocess keeps the maths;
  - a new version starts again;
  - pages read already, pages without maths and pages outside the document
    are refused;
  - cancelling changes nothing;
  - a reading carries on from pages read before;
  - a page is never read twice;
  - the model unreachable is reported in its own words.
- **Quoting:**
  - `shown` and `unquoted`;
  - the rule in document and environment summaries, concepts and practice;
  - wrong options and false statements exempt.
  - Seven tests from record 24 had a scripted model write maths their
    documents did not contain. They were given documents that show it.
- **The chunker:** a long paragraph is never cut inside a formula.
- **The page:** the offer, the range and its estimate, pages already read,
  the reasons a page keeps its text, and an error.
- **The end-to-end journey** gained a step. It uploads a lecture with a
  formula in a maths font, reads its maths from the menu, and checks that
  the page's text now shows the formula typeset.
- **Deliberate breaks.** 32 were made in the new code. The first run caught
  28. The 4 it missed were gaps in the tests, not the code:
  - letters allowed at 10%;
  - a cut inside a formula;
  - a page read twice;
  - one break that never ran, as its pattern was stale.

  Tests were added for each. Four more breaks were made for the fixes the
  live check led to. All 36 are caught.

### In the running app, with the real model

The check ran on a stack of its own, with ministral-3:8b on an Apple M3
Pro. The document was 16 pages of the same textbook: the prototype's 11 and
some of their neighbours, all of them maths.

- **Before reading the maths:** the document was read as usual. Its summary
  failed: Ollama stopped the model for repeating itself, on the text
  layer's flattened matrices.
- **Cancelling:** a reading started through the API was cancelled after its
  second page, and stopped after the third, the page in hand. The update
  and the two jobs waiting were cancelled; the pages and the document were
  as before, and no page showed as read. The three pages read were used by
  the next reading without the model.
- **The offer** counted those three pages at full time, "about 21
  minutes". It now counts them as taking no time.
- **Reading from the page:** 9 of 16 pages were accepted, 6 at the first
  attempt and 3 in halves. The model took 24 to 141 seconds a page, 86 at
  the median. The Mac slept with its lid closed; the times leave that out.
- **Why 7 were refused.** Each was read again and its Markdown kept:
  - A square root in a symbol font reads "p", and a long arrow over a row
    operation reads as minus signs. Both were added to the check.
  - One half of a page began with a sentence of the model's own. That
    sentence is now dropped from each half, not only from the start.
  - With those fixes, 10 of the 16 pages pass.
  - The other 6 are real differences:
    - a minus read as a dot, and a phrase of the model's own;
    - the book's own typo corrected, its 3 + √2 written 3 + 2√2;
    - arrows written as implications, and lines left out;
    - row operations written with ← instead of =;
    - arrows the book draws as pictures.
- **What changed:** the document was read again, with 34 new passages, 2
  kept and 30 removed. Its summary was written this time. The environment's
  summary had a formula in each of its 5 key points. 3 of the 8 concepts had
  one in their definitions.
- **The quote rule:** two key points were dropped.
  - One restated "the sum of the squares of the entries" as
    `||A\hat{x} - b||^2`.
  - The other had a damaged formula, record 24's rule.
- **Practice:** for the first stage's 8 concepts, 21 of 32 items were kept.
  - 2 were dropped for maths not in their passages: a made-up `t = 2`, and
    a `2 \times 2` its passages wrote otherwise.
  - The rest were dropped for the old reasons.
- **In the browser:**
  - Search for the characteristic polynomial found a passage with 5
    typeset formulas, and "Show in page" marked them across a page break,
    with no LaTeX left as text. The next page, not read, still shows the
    text layer's flattened matrices.
  - The Summary tab typeset 33 formulas, and a practice item its own.
  - On a phone in the dark theme, the offer fit the 390 pixels.
  - There were no console errors.

## Consequences

- **Order is not checked.** Counting characters cannot see a matrix whose
  columns were put in a different order, or two numbers swapped. On one
  prototype page the model put a matrix's swapped columns back in order.
  That page also failed for another reason, but a page could pass with
  such a mistake.
- **A quirk the check does not know rejects a good page.** The page then
  keeps the PDF's own text, which is what it had before, and the document
  says why. Other PDFs will have quirks this textbook did not.
- **Reading a textbook takes hours.** That is why it is offered for a range
  and never done unasked.
- **Figure labels may leave the text.** A transcription that leaves out a
  figure's labels replaces a page whose text layer had them, so search no
  longer finds them on that page.
- **A correct restatement is refused.** A summary that writes
  ‖b − Ax̂‖² for "the sum of the squares of the entries of b − Ax̂" loses
  that key point. Quoting is what the rule can check.
- **An overview with maths not in its sources is asked for again.** If it
  keeps coming back with such maths, the summary fails and can be tried
  again.
- **A new version, or a new model or prompt, starts again.** A new version
  of the file is never read with another version's pages, so its maths is
  offered again. A different model or prompt version reads the pages
  afresh. Pages its predecessor accepted stay in use until it does.
