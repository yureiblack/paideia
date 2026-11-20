# 24. Maths notation

Date: 2026-11-19
Status: accepted

## Context

The 23 phases of the original roadmap built Paideia around lecture notes in
prose. Asked whether it could teach linear algebra, the honest answer was:
partly. It could organize the concepts and their order, but not the
mathematics itself. Phases 24 to 27 extend it to mathematics, starting with
linear algebra. This first one, and so this record, also sets out the plan
for all four.

### What a real textbook showed

The test used Interactive Linear Algebra, by Margalit and Rabinoff: an open
textbook of 455 pages, not committed here.

- **Text extraction keeps the prose and loses the maths.** The app's parser
  read all 455 pages in 2.4 seconds, and the prose came out clean. A 3 by 3
  matrix of halves came out as "0 6 8 1 2 0 0 0 1 2 0". λ² came out as
  "λ2". The brackets of matrices, which are drawn rather than written,
  became blank lines. None of this can be put back from the text.
- **The local model can read page images.** ministral-3:8b has vision.
  Three pages were turned into Markdown with LaTeX, at 110 dots per inch:
  - Matrices, fractions and derivations came out right.
  - Each page took 31 to 47 seconds on an Apple M3 Pro.
  - It slipped: it read one minus as a dot, dropped the outer brackets of
    det((…) − (…)), silently corrected the book's typo "characterestic",
    and kept running headers.
- **Maths pages can be told apart.** The PDF names its maths fonts
  (MathDesign-CH-*). But 423 of the 455 pages hold at least some maths, so
  reading every one of them with the model would take hours.
- **The page shows plain text, and the rules drop maths.** There was no
  maths rendering at all. Practice's plain-text rules refused `|` and `*`,
  so |A| and A* would have dropped an item.

## The plan for maths

| Phase | What it adds |
|---|---|
| 24 Maths notation | The page renders maths, the model writes it, the rules accept it. |
| 25 Reading maths from PDFs | The vision model transcribes maths pages; the backend checks each against the PDF's text layer. |
| 26 Computed exercises | Linear algebra exercises the backend writes, solves and marks, with worked solutions. |
| 27 Maths evaluation | A typeset linear algebra corpus, measured; the README and setup guide. |

Decisions that hold across the four phases:

- **Maths is stored as LaTeX between `\(` `\)` and `\[` `\]`, never `$`.**
  A dollar sign in an economics text is a price; these two pairs are never
  anything but maths.
- **The model transcribes, the backend checks.** Each page's transcription
  will be compared with the PDF's own text layer. A page that disagrees gets
  one retry, then keeps its text layer, and the document says which pages
  could not be read.
- **No PyTorch maths OCR.** Nougat, Marker and MinerU would bring gigabytes
  of dependencies, the reason fastembed was chosen over Sentence
  Transformers (record 05). Marker and MinerU are also GPL or AGPL.
- **Reading maths is never automatic.** At about half a minute a page, a
  chapter takes a quarter of an hour and a book several hours. The
  Materials tab will offer it with the page count and a time estimate, and
  run it only when the learner asks.
- **The model never does arithmetic in an exercise.** It will only choose
  which exercise types fit a concept, from a fixed catalogue. The backend
  will make the numbers, compute the answer in exact fractions, write the
  worked solution and mark the answer. Answers will be typed as numbers in
  cells; nothing typed is evaluated as code.
- **Exact arithmetic of the project's own, not sympy.** Worked solutions
  need every step, which sympy does not give, and it would be a new
  dependency.
- **Linear algebra first.** The catalogue is built so other topics can be
  added.
- **Still no chat tutor.** Explanations come from worked solutions and
  cited passages.

## What the prototype showed

The practice prompt was tried on passages from the textbook page above,
with its formulas written in LaTeX, and the raw answers were read:

- **Asked for `\(` `\)`, the model wrote Unicode instead:** λ², Iₙ, and a
  matrix as `[5 2; 2 1]`.
- **Asked for LaTeX between dollar signs, it wrote LaTeX,** in its JSON
  answers, every time.
- **Asked for `\(` `\)` in the same JSON answers, it still wrote dollar
  signs.**
- **Without the JSON constraint, it wrote `\(` `\)` cleanly.** Paideia
  constrains every answer to a schema (record 08), so that does not help.
- **JSON's escaping damaged the LaTeX in two ways:**
  - JSON reads `\b`, `\f`, `\n`, `\r` and `\t` as control characters, so
    `\begin` arrived as a backspace followed by "egin".
  - A matrix's row break `\\` arrived as a single backslash, which joins
    the rows.
- **Without being told not to, it made up a matrix and computed with it.**
  The final answer happened to be right; a step in its explanation was
  wrong. Told to use only the mathematics in the passages and not to
  calculate, it used the passage's own matrix.

## Decisions

### KaTeX, bundled, with trust off

The page typesets formulas with KaTeX 0.19.1 (MIT), pinned to that exact
version, its styles and fonts served with the page, not from a CDN. Its
options:

- **Trust is off,** so no formula can add a link, an image or HTML:
  `\href` shows as red text, not a link.
- **Sizes and macro expansion are limited.**
- **It writes MathML alongside,** which is what screen readers read.

A formula KaTeX cannot render is shown as its LaTeX source, marked, instead
of breaking the page. A displayed formula wider than its column scrolls on
its own instead of widening the page.

MathJax was the alternative. KaTeX renders synchronously and to a string,
so a formula is typeset in the same render as the text around it, and its
output can be tested in a simulated browser.

### One component, wherever text is shown

`MathsText` (web/src/components/maths-text.tsx) shows every passage and
everything the model wrote:
- search results;
- the source panel and the Materials tab's page text;
- summaries' overviews and key points;
- concept definitions on the concepts list, the knowledge map and the
  roadmap;
- roadmap stage descriptions;
- practice items, their answers and explanations.

Concept names, filenames and headings stay plain text.

The source panel marks a passage by its place in the page's text. A mark
that would start or end inside a formula is widened to take in the whole
formula, since half a formula cannot be typeset.

### Ask for dollars, store `\(` `\)`

The prototype settled it: the prompts ask for LaTeX between dollar signs,
which the model writes reliably, and the backend moves every formula to
`\(` `\)` or `\[` `\]` as it stores it (app/maths.py, `from_model`). The
stored convention is unchanged.

A `$` opens a formula only as Pandoc reads TeX maths: no space after the
opening one, no space before the closing one, and no digit after it. "$5 and
$10" stays money. One case is misread: two dollar signs with no spaces
between them, as in a shell's `$HOME$PATH`.

Inside formulas only, the backend repairs the damage JSON does:
- **A control character becomes a command again.** A backspace or a form
  feed always does, since neither is ever meant. A newline, carriage
  return or tab does only when the result is a command KaTeX knows, so a
  real line break stays one, but `\neq` comes back.
- **A single backslash before a space becomes a row break again,** inside
  an environment made of rows, such as a matrix. Elsewhere, `\ ` is
  LaTeX's own space and is left alone.

Five prompts get a v2, with one paragraph more:
- document_summary;
- combine_summaries;
- environment_summary;
- concept_extraction;
- practice_items.

The paragraph asks for maths between dollar signs and for it to be taken
from the passages, never worked out. The practice prompt adds: never make
up new matrices or numbers, and never calculate. Concept extraction adds
that a name is always words.

The first run in the app showed that the paragraph alone was not enough.
The concepts came back in LaTeX, but the summary came back with Unicode
maths: "det(A) ≠ 0", "A^T", "PDP^-1", and no formula at all. Asked again,
the same prompt gave 32 formulas, so the model's compliance varies from run
to run. Two changes, each tried on the same passages, made it reliable:

- **The model reads the notation it is asked to write.** The passages and
  notes in a prompt are shown with their formulas between dollar signs
  (`maths.for_model`), so the model copies what it reads. Storage and the
  page keep `\(` `\)`.
- **Each task ends with an example of what to write and what not to:**
  `$\det(A - \lambda I) = 0$`, never det(A - λI) = 0.

With both, the summary of the same lecture came back with 40 formulas and
no Unicode maths left; in the app, with 24.

### Every formula is checked

`maths.problem()` says why a text's formulas would not render, or would
render something no formula should:
- a formula not closed, closed but never opened, or opened inside another;
- unbalanced braces, or `\left` and `\right`;
- an unknown environment, or an `\end` that does not match its `\begin`;
- a command KaTeX does not know;
- a bare `$` or `%` inside a formula (`%` starts a comment that hides the
  rest);
- a control character outside a formula, the remains of LaTeX written
  without dollar signs.

"Commands KaTeX knows" is a generated list, api/app/katex.json: every
command and environment named in KaTeX's own source that it renders without
calling it undefined. `pnpm katex:commands` writes it, and a web test fails
when it no longer matches the installed KaTeX. The backend checks formulas
against the same KaTeX the page renders them with.

Some commands KaTeX knows are refused:
- **commands that define commands,** such as `\def` and `\newcommand`: one
  formula could change what later ones mean, and none needs them;
- **`\show` and `\message`,** which write to the browser's console;
- **`\href`, `\url`, `\includegraphics` and `\html…`,** which need the
  trust the page does not give;
- **`\verb`,** whose text runs to a delimiter of its choosing, which can be
  the closing `\)`.

What happens to a text whose formula fails:
- **Practice items, concepts and summaries' key points are dropped,** like
  anything else that fails a check. A practice item records the reason, "a
  formula that would not render (…)".
- **A summary's overview cannot be dropped,** so a broken formula in it
  makes the whole answer malformed, and the model is asked again, as for
  any answer of the wrong form (record 08).

### Plain-text rules see only the prose

`maths.prose()` puts a placeholder in place of each formula while the
practice rules run:
- the formatting check (`|`, `*`, `#`);
- citation marks such as "(2)", which in a formula is maths;
- mentions of passages.

The length limits now count prose and LaTeX apart. Each formula counts as
one character of prose, and a field's formulas may take up to 300
characters of LaTeX (`maths.FORMULA_CHARS`). A 3 by 3 matrix of fractions
is about 90. The answer schemas give the model room for both, since Ollama
cuts an answer off at the schema's limit (record 14).

A concept's name and aliases never hold maths. A concept is merged by the
words of its name (record 11), and LaTeX has no words to merge on:
- a name with a formula drops the concept;
- an alias with one is left out.

Definitions are repaired before they are tidied, since tidying collapses
whitespace, and a form feed (a damaged `\frac`) is whitespace.

### Search needed no change

Postgres's parser already splits words at backslashes. `\lambda` is indexed
as "lambda" and `\det` as "det", so typing words finds maths passages. A test
pins this. The structural words of LaTeX, such as "begin", "end" and
"pmatrix", are indexed too; phase 27 will measure whether that matters.

## Testing

- **The maths rules (pure):**
  - splitting text into prose and formulas;
  - dollar signs moved, money left alone;
  - the real model's damaged answers repaired;
  - newlines repaired only into real commands;
  - row breaks restored only inside rows;
  - every problem named, and well-formed maths accepted;
  - refused commands being ones KaTeX knows;
  - placeholders for prose;
  - sizes counted apart.
- **Practice, concepts and summaries:**
  - | and * inside a formula are maths, not formatting;
  - citation marks removed from prose only;
  - a broken formula drops an item, with its reason;
  - the prose limit counts a formula as one character;
  - definitions repaired before tidying;
  - names and aliases stay words;
  - a broken key point dropped from document and environment summaries;
  - a broken overview makes the answer malformed;
  - every prompt that carries passages or notes shows their formulas
    between dollar signs: summaries, the environment's summary, concepts,
    and practice, definition included;
  - LaTeX found by keyword search.
- **The page:**
  - inline and displayed formulas typeset, with MathML;
  - a matrix;
  - a broken formula shown as its source;
  - prices left exactly as they were;
  - no link, image or HTML from a formula;
  - the source panel's mark widened around a formula;
  - splitting matching the backend's;
  - katex.json matching the installed KaTeX.
- **Deliberate breaks.** 32 deliberate breaks were all caught, each by a
  test failing rather than by code that would not run:
  - each repair, each check and each refused command;
  - the prose-only rules;
  - the dropping of broken points and the strict overview;
  - names staying words;
  - each prompt's passages shown with dollar signs;
  - KaTeX's trust option;
  - the source fallback;
  - the source panel's widening;
  - the generated list.
- **The end-to-end journey** passed unchanged.

### In the running app, with the real model

The check ran on a stack of its own, with ministral-3:8b on an Apple M3
Pro. Its lecture, on eigenvalues, was written for the check, with its 46
formulas as LaTeX in the PDF's text, standing in for what phase 25 will
read:
- determinants, with a 2 by 2 matrix;
- eigenvalues and eigenvectors;
- the characteristic polynomial;
- eigenspaces;
- diagonalization.

- **Time:** reading took 2 seconds, and the model's work 3 minutes 34
  seconds.
- **Concepts:** 12 proposed, 12 kept. Every definition was in LaTeX, and
  every name was words.
- **The summary:** 24 formulas, the matrix among them, no Unicode maths
  left, nothing dropped.
- **Practice:** 39 of 48 items kept, for 12 concepts. None was dropped for
  its maths. The four generations asked again to find out why showed the
  old reasons: three explanations mentioning "the passages", and one
  `*always*` in Markdown emphasis.
- **In the browser:** every page that shows text typeset its formulas:
  - the Summary tab (36);
  - a citation opened in its page, the mark around 12 formulas;
  - the knowledge map, the roadmap and search (46 each);
  - a practice session of ten items, answered;
  - no formula was shown as source, no LaTeX was left as text, and there
    was no console error;
  - on a phone, in the dark theme, the page stayed 390 pixels wide, with
    the matrix within its column.
- **A lecture in prose:** the CPU scheduling lecture of the benchmark's
  corpus came back with formulas only where it has maths. Those were the
  exponential average that predicts the next CPU burst, and the
  `(n - 1)` of round robin's longest wait. Everything else stayed prose.

## Consequences

- **Existing material is written again, once.** A new prompt version, like
  a new model, means existing summaries, concepts and practice are written
  again the next time they are asked for. Nothing old is overwritten
  (record 09).
- **Only the stored form renders.** Text written before this phase,
  including a model's Unicode maths such as λ², shows as it was. Passages
  from PDFs hold no LaTeX until phase 25 reads it.
- **A dropped item costs a model call that produced nothing.** That is
  the price of never showing a broken formula.
- **Practice items mix notations.** An answer may typeset
  `\(\det(A - \lambda I) = 0\)` while its question writes "a matrix A" and
  "λ" as plain text. It reads correctly, but not evenly.
- **The model may still quote maths wrongly.** The checks make sure a
  formula renders, not that it is right. Phase 25 will try a rule that
  maths in an answer must come from its passages.
