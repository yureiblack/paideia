# 30. Maths evaluation

Date: 2026-11-24
Status: accepted

## Context

Records 24 to 29 taught Paideia maths:
- it renders and checks LaTeX (24);
- the local vision model reads a PDF's maths pages, and each reading is
  checked against the PDF's own text layer before it replaces the page
  (26);
- the backend writes, solves and marks linear algebra exercises (27);
- figures, tables and scans are read too (29).

What was measured until now was eleven pages of one linear algebra textbook,
read while the check was being designed. Nobody knew how often the model
reads a formula right, which notation it gets wrong, how often the check
catches a misreading, whether reading the maths helps search find it, or
what practice it leads to.

This phase measures all of that. The roadmap asked for a linear algebra
corpus. The project's owner widened it to every area of maths, saying to
"make sure to test all different types of mathematical notations as well
including the sigmas, deltas, set notations, etc along with linear algebra
matrices".

## Decisions

### Lectures written in the form the model writes, typeset by TeX

Ten lectures were written for the benchmark (`docs/evaluation/maths/corpus/`):
- three of linear algebra (systems and row reduction; matrices, inverses
  and determinants; vector spaces, eigenvalues and orthogonality);
- single-variable calculus, multivariable calculus and differential
  equations;
- probability and statistics;
- sets, logic and proof;
- series and complex numbers;
- numerical methods.

Every worked number in them was checked by hand.

Each is written in the very form the model is asked to write a page in:
Markdown, with its maths in LaTeX between dollar signs. The benchmark
converts each to LaTeX and typesets it with Tectonic, a self-contained TeX
engine, as most textbooks are typeset: Computer Modern, A4, a running header
and page numbers. The app then reads the PDF as it reads any upload.

Each paragraph, formula and list item gets a label in the LaTeX. TeX writes
the page each label lands on, and no paragraph is allowed to break across
pages, so every block is on exactly one page. What the source says on a page
is therefore that page's perfect reading, its truth.

Typesetting is deterministic: the same source always makes the same PDF,
byte for byte. Tectonic is needed only to run the benchmark, never by the
app, and not in CI.

Rejected:
- **PyMuPDF's HTML layout, as in record 20:** it cannot typeset maths.
- **matplotlib's maths text:** a TeX look-alike, but not the PDFs textbooks
  are.
- **Committing the PDFs:** the corpus stays text, as record 20's does.

### Every kind of notation named, and each shown at least five times

`api/evaluation/notation.py` names 41 kinds of notation, each recognised in
a formula's LaTeX by a pattern. Among them:
- Greek letters, with sigmas and deltas counted apart;
- sums, products, integrals, big unions and limits;
- fractions, roots, binomials, primes, ∂, ∇ and accents;
- matrices, determinant bars, augmented matrices, transposes and norms;
- set relations, set operations, sets written out, number sets and logic;
- cases, aligned derivations, congruences, probability and complex numbers.

A test fails if the corpus shows any kind in fewer than five formulas. The
first draft fell short on eight kinds, and examples were added. Reading
accuracy is reported for every kind.

### The check is given perfect readings, then planted mistakes

The check (record 26) compares a reading with the PDF's text layer, so a
perfect reading should pass it. Each page's truth is checked first. A
refusal there is a quirk of the check: a way a correct page would keep its
text layer in any textbook typeset the same way.

The model makes too few mistakes on clean pages to say how well the check
catches each kind. So mistakes are planted. A page's truth gets exactly one
change in one place, of one of 22 kinds (`api/evaluation/maths_planted.py`):
- a sign flipped, a digit changed, a letter or a Greek letter changed;
- Δ read as δ;
- a superscript, a subscript, a prime, a root or an accent dropped;
- a fraction turned upside down;
- Σ read as Π, or ∫ as Σ;
- the bounds of a sum swapped;
- ∂ read as d;
- ∈ read as ∉, ∪ as ∩, ∀ as ∃, ≤ as ≥;
- a matrix entry left out, or two entries swapped;
- a word or a whole formula left out.

Up to three of each kind are planted on each page whose truth the check
accepts, chosen at random but the same on every run. No model is needed, and
the whole set takes seconds.

### Every page read both ways, and the readings kept

The model reads every page whole, and in two halves, each seen larger. The
app reads the halves only after the whole reading fails its check. The
benchmark reads both on every page, so that both attempts are measured
everywhere, and works out from them what the app would have kept.

Every answer is kept in `docs/evaluation/maths/readings.json` with the
SHA-256 of the image the model saw, the model and the prompt version. At
temperature 0 the same image gets the same answer, so a run asks the model
only for images it has no answer for. A change to the check, the comparison
or the report is measured again in minutes, without the model. That is how
every fix below was measured before and after.

### A reading is compared with the truth formula by formula

Both the reading and the truth are made page text as the app stores it.
Each becomes one stream of prose words and maths tokens, in reading order,
with the formulas' boundaries forgotten. That way a formula the model moved
to a line of its own, split in two, or wrote "det" beside, still counts.

Presentation is set aside first (`api/evaluation/maths_compare.py`):
- spacing, sizes and `\left` `\right`;
- the bracket style of a matrix, and an augmented matrix's bar;
- `\dfrac` for `\frac`;
- font commands;
- braces around one token;
- commas, and a percent sign;
- the `&` and `\\` that line a derivation up;
- other spellings of one symbol.

Determinant bars are not set aside: they mean something brackets do not.
The two streams are aligned, and a formula is right when every one of its
tokens is matched, in order.

The comparison is strict about form. Pascal's rule with its two terms
swapped, `\operatorname{tr}(A)` for `\operatorname{tr} A`, and a vector
written as a column instead of `(3, 1)` all count as wrong. The report lists
every formula counted wrong, so a reader can tell these from misreadings.

### Search is asked of three versions of the same lectures

There are 48 questions (`docs/evaluation/maths/questions.json`):
- ten name their topic;
- ten describe it in other words;
- twenty ask for a formula;
- eight type the maths itself as words, as a learner types into a search
  box ("nabla f dot u").

Each names its answer by a quote of the lecture's prose, never its maths, so
the quote finds its passage in every version. They are asked of the lectures
read three ways:
- as the PDF's text layer has them;
- with the model's readings in place where the check accepted them;
- with perfect readings in place.

Each version is asked by the four methods of record 20. This answers record
24's open question: whether indexing LaTeX's commands, such as `begin` and
`pmatrix`, matters.

### Practice is judged against what each lecture teaches

With `--practice`, the app extracts the concepts of the lectures as it has
read them. It then chooses computed exercises for each, as record 27
designed: the model picks, and a pick stands only if the concept's passages
use its words. Each exercise offered is judged against the types its lecture
teaches (`docs/evaluation/maths/exercise-labels.json`). The catalogue is
linear algebra, so an exercise offered for a calculus or statistics concept
is a misfire. The exercises' arithmetic was measured in record 27, a
thousand seeds per type against numpy, and is not measured again.

### Two real textbooks, read but not committed

The corpus is clean TeX, so two real, openly licensed books were read too:
- 20 pages of the eigenvalues chapter of *Interactive Linear Algebra*
  (Margalit and Rabinoff), typeset with pdfTeX in MathDesign fonts;
- 20 pages of section 5.2, The Definite Integral, of OpenStax *Calculus
  Volume 1*, which is not made with TeX: Prince, in STIX fonts.

Neither book nor its readings is committed, as decided in record 24. Their
numbers are in this record only.

### Checked in a second pass, not by an independent person

The truth of every page is the source itself, so the formulas needed no
labels. The search questions did. As in record 20, they were rechecked in a
second pass: a reviewer with no access to the author's reasoning read every
question against the lectures, and each point it raised was then checked
before anything changed. As a result:
- three questions in other words were reworded, because they copied their
  evidence;
- one question was made more specific;
- two alternative answering passages were added;
- two quotes were moved before their formula.

`questions.json` and the report say this was not an independent human
review.

### No number typed by hand, and every fix measured before and after

`scripts/evaluate_maths.py` writes `docs/evaluation/maths/results.json` and
the tables between markers in `docs/evaluation/maths-benchmark.md`. The
check's fixes below were each measured against main's check. That is the
same code run with the fixes set aside, on the same kept readings.

## What it found

The figures here are from the final run on an Apple M3 Pro. The report has
every table, and `results.json` every page.

### The check refused a perfect reading on 8 of 20 pages

Five faults, each of which refuses correct pages in any textbook typeset the
same way:

- **A line break inside a formula was read as damage.** `maths.from_model`
  repairs what JSON's escaping does to LaTeX, and reads a line break
  followed by "e" as the command `\ne`. Page text was made before a
  displayed formula's lines were joined, so a model writing
  `$$` on one line and `e^x = …` on the next had its page stored with
  `≠^x`. Lines beginning "u" became ν, and "i" became ∋. This is a bug in
  record 26's code, not only in its check: an accepted page would have kept
  the wrong symbol.
- **"The $n$-th term"** counted its hyphen as a minus, since the formula
  ends just before it. "A $p$-series" did too.
- **A hat was a letter.** TeX's text layer writes x̂ as "ˆ" and x, and "ˆ"
  is a Unicode letter. Pages with ten or more hats went over the letters'
  slack.
- **LaTeX's ∉** is a slash set over ∈, and the layer writes it as "/∈".
- **A congruence's "(mod n)"** is set in words, which `\pmod` was not
  counted as drawing.

With the fixes below, all 20 perfect readings pass.

### The check never saw most of the notation it was meant to guard

The check counted digits and operators exactly, and letters within a 1%
slack. It did not count primes, roots, sums, integrals, ∂, ∇, logic symbols
or accents. Greek letters fell in the slack with Latin ones. On the same 452
planted mistakes (the 12 pages main's check passes), caught before and
after the fixes:

| Mistake | Before | After |
|---|---|---|
| A sign flipped, a digit changed, a formula left out | 106 of 106 | 106 of 106 |
| A Greek letter changed, Δ read as δ | 0 of 31 | 31 of 31 |
| A prime, a root or an accent dropped | 0 of 27 | 26 of 27 |
| Σ read as Π, ∫ as Σ; ∂ read as d | 0 of 25 | 25 of 25 |
| A relation, set relation or logic symbol changed | 30 of 32 | 32 of 32 |
| A matrix entry left out | 21 of 24 | 24 of 24 |
| A superscript or a subscript dropped | 43 of 69 | 44 of 69 |
| A word left out | 6 of 36 | 4 of 36 |
| A Latin letter changed, a fraction upside down, bounds swapped, entries swapped | 0 of 102 | 0 of 102 |
| All | 206 (46%) | 292 (65%) |

Over all 20 pages, the fixed check catches 505 of 784 planted mistakes.

- **The accent it still misses is `\overline`.** TeX draws an overline as a
  rule, which leaves no character.
- **The scripts it misses are letters,** such as the T of Aᵀ. A Latin
  letter changed anywhere stays within the slack the prose needs.
- **A fraction turned upside down, swapped bounds and swapped matrix
  entries leave the same characters.** Counting cannot see them, as record
  26 said of order.
- **Two dropped words were caught before only by accident.** Their pages
  had an extra "letter" from another quirk, TeX's increment sign ∆, which
  pushed the count over the slack. One dropped word stays within the slack
  by design.

### The model reads nine formulas in ten from a whole page, and almost all in halves

| Read | Formulas right | Pages with every formula right |
|---|---|---|
| The whole page | 775 of 860 (90.1%) | 6 of 20 |
| In two halves | 821 of 831 (98.8%) | 12 of 19 |

- **Most whole-page mistakes are on three pages.** 65 of the 85 wrong
  formulas are on three pages the model wrote in plain Unicode text instead
  of LaTeX (ℝⁿ, uᵀv, P(A ∩ B)). The check refused all three.
- **By kind of notation,** read whole, norms and inner products (50%),
  aligned derivations, augmented matrices, determinant bars and set
  operations were read least well. Read in halves, every kind but three is
  right at least 93% of the time; the three are ∂ (7 of 9), aligned
  derivations (4 of 5) and congruences (5 of 6).
- **One half-page reading was unusable:** it had LaTeX outside a formula.

### What the app keeps

The app reads a page whole, and in halves only if the whole reading fails
its check:

| | Main's check | With the fixes |
|---|---|---|
| Pages kept read | 9 of 20 (4 whole, 5 in halves) | 14 of 20 (7 and 7) |
| Formulas right on those pages | 354 of 357 | 590 of 594 (99.3%) |
| Pages with a formula that differs from the page | 2 | 3 |
| Model time per page, median | 103 s | 83 s |

- **Only one kept page has real misreadings.** On the numerical methods
  lecture's first page, a repeating decimal's bar (1.41‾6) and the
  absolute-value bars around a fraction were dropped. TeX draws the first
  as a rule, and the check does not compare bars, so it cannot see them.
- **The other two differ in form, not in maths:** Pascal's rule with its
  two terms swapped, and `tr(A)` for `tr A`.
- **The check refused 16 of the model's 21 wrong readings.**
- **It refused 4 of its 18 readings whose formulas were all right.** Three
  had a sentence the model made up, and one wrote the word "in" as ∈. Each
  changes the page, so refusing them is right.

Two more findings come from the kept readings.

**Halves first is faster on the corpus, slower on real books.** Whole
readings failed their check on 13 of the corpus's 20 pages, so most pages
cost both attempts. Worked out from the kept readings, reading halves first
would keep the same 14 pages, as accurately (589 formulas of 594 right), at
a median of 60 s a page instead of 83 s. On the two textbooks below, the
whole reading passes more often than the halves, and halves first would be
slower: 40 minutes instead of 33 for 20 pages of one, 24 instead of 20 for
the other. Record 26's order, whole first, stays.

**A cut before a formula invites a sentence of the model's own.** Three of
the six pages that kept their text layer had halves with every formula
right. Each was refused for a sentence the model added where the cut fell
just before a displayed formula: "The indicator function of a set A is
defined as:". Cutting elsewhere, or a prompt that names the case, could
keep those pages. Either needs a new prompt version, or new halves, read
again and measured.

### Reading the maths hardly changes search

The app's search, MRR@10, over the 48 questions:

| Lectures as | All | Formula questions | Maths typed as words |
|---|---|---|---|
| The PDF's text layer | 0.869 | 0.917 | 0.656 |
| With the model's readings | 0.836 | 0.917 | 0.601 |
| With perfect readings | 0.891 | 0.942 | 0.708 |

- **The differences are a few questions.** Between the text layer and the
  model's readings, the right passage moves for 10 of 48 questions, 3 up
  and 7 down. The changes come from where passages begin and end once
  their text changes.
- **Record 24's question:** passages with read maths are indexed under
  their LaTeX commands. With perfect readings, the most frequent are `\frac`
  (162), `\mathbf` (142) and `\begin` (52). Search is at its best with
  perfect readings, the version whose passages hold the most LaTeX, and
  maths typed as words ("nabla f dot u") is found a little more often there
  than in the PDF's own text. The commands in the index do no harm
  measurable here, so the index stays as it is.

### Time

| Step | Time |
|---|---|
| Parse a page | 9 ms |
| Find which pages hold maths | 9 ms a page |
| Render a page for the model | 33 ms |
| Read the text layer and check a reading | 28 ms |
| The model's reading of a page, median | 83 s |
| A 400-page textbook, at that rate | about 9 hours |
| Read the 20 pages again with readings in place, and embed | 4 s |

Everything but the model takes milliseconds. Record 26 estimated 65 s a page
from one textbook; this corpus, denser in maths, takes 83 s.

### Two real textbooks

The books have no truth to compare with, so their readings were judged in a
second pass. A fresh reviewer, without the check's verdicts, compared every
attempt with the page's image, zoomed in where the maths was small. Each
attempt was judged right or wrong in its maths, with presentation ignored as
above.

**OpenStax *Calculus*, section 5.2, 20 pages (Prince, STIX fonts).** The
reviewer found the maths right in 20 of 39 attempts (one whole reading was
unusable). Read whole, the model mostly got integration limits and
coefficients wrong on the exercise pages. In halves, it invented formulas
and lead-in sentences. Against the reviewer's verdicts:

| | Main's check | With the fixes |
|---|---|---|
| Right readings accepted | 9 of 20 | 17 of 20 |
| Wrong readings refused | 16 of 19 | 16 of 19 |
| Pages kept read | 8 of 20 | 13 of 20 |
| Kept pages with wrong maths | 3 | 3 |

- **The three wrong pages kept are the corpus's blind spots:** |60| read as
  60, and a repeating decimal's bar lost (1.6‾ read as 1.66). The third
  writes 0 + i[2/n] as 0 + 2i/n, the same value.
- **Three of the fixes were found on this book.** The first fixed check
  kept fewer of its pages than main's (6). The book draws every radical as
  lines and sets a big integral in pieces; the model wrote "x-axis" as
  `x\text{-axis}` inside formulas, counting a minus; and it marked figures
  with Markdown placeholders, `![Figure 5.20](image_url)`, whose numbers
  counted as digits (22 in the books' readings).

**Interactive Linear Algebra, eigenvalues, 20 pages (pdfTeX, MathDesign
fonts).** The reviewer found the maths right in 21 of 39 attempts (one
half-page reading was unusable). Many of the wrong ones differ only in an
arrow: the book's long arrow ⟶, often labelled, written as ⟹ or as words.
Counting those, and three other small slips, as right gives 29. On two
pages the model corrected the book's misprints, writing 3 + 2√2 where the
page prints 3 + √2. The reviewer counted those as wrong, since a reading
must say what the page says.

| | Main's check | With the fixes |
|---|---|---|
| Right readings accepted | 7 of 21 | 14 of 21 |
| Wrong readings refused | 16 of 18 | 16 of 18 |
| Pages kept read | 6 of 20 | 11 of 20 |
| Kept pages with wrong maths | 1 | 1 |

- **The one wrong page kept, by both checks, is the corrected misprint.**
  The reading has one 2 more than the page, and the page has a figure
  label "2", which a reading may write or leave out, so the count
  balances. An optional character can hide a difference that happens to
  match it.
- **The seven right readings still refused all add text the page does not
  have:** sentences of the model's own, descriptions of figures or
  placeholders for them ("(Diagram 1)"), and in one case 9 KB of "| | |".
- **Two fixes were found on this book:** a hyphen after a number or after a
  bracket, "the 1-eigenspace" and "the (3 + √2)-eigenspace", was counted as
  a minus in the PDF's text but not in the reading.

Across the two books, the fixes kept 24 pages read instead of 14, with
the same 4 pages of wrong maths among them. A page took the model a median
of 49 s on *Interactive Linear Algebra* and 41 s on *Calculus*, both
attempts counted when needed.

### Practice

The model extracted 97 concepts from the ten lectures, as the app had read
them, and was asked to choose computed exercises for each.

- **26 concepts were offered an exercise, all of them linear algebra.** No
  concept of calculus, probability, sets or series got one. Record 27's
  rule, that a pick stands only if the concept's passages use its words,
  held across subjects. Where no passage used any type's words, the model
  was not asked at all.
- **33 of the 35 exercises are of a type their lecture teaches.** The two
  others are arguable, and the labels were not changed after the fact:
  - a reduced row echelon form exercise for "Matrix inverse", which
    lecture 02 does compute by row reducing [A | I];
  - a determinant exercise for "Characteristic equation", which is
    det(A − λI).
- **10 of the 12 types the lectures teach were offered somewhere.** Never
  offered: rank in the linear systems lecture, and a determinant in the
  multivariable lecture.

The exercises' own arithmetic was measured in record 27.

## The check, fixed

Each fix is in record 26's code, and each was measured before and after on
the kept readings:

- **Line breaks:** page text joins each formula's lines before
  `maths.from_model` repairs JSON's damage (`app/transcription.py`).
- **Word hyphens:** a hyphen joins words when it comes right after a formula
  and before a word ("the $n$-th"), inside `\text{…}` in a formula, or
  after a number or a bracket in a PDF's text ("the 1-eigenspace", "the
  (3 + √2)-eigenspace", found on *Interactive Linear Algebra*). A TeX text
  layer's minus is "−", never "-".
- **TeX's forms:** "/∈" is ∉, ∆ is Δ, `\pmod` and `\bmod` show "mod".
- **Accents are never letters,** in the layer or in a reading.
- **The symbols a reading must keep:** with `symbols=True`, `maths.shown`
  also shows primes, roots, ∑ ∏ ∫ ∮, ∂, ∇, ∀ ∃ ¬ ∧ ∨, ∅, ≪ ≫, and the
  accents hat, bar, dot, double dot, tilde, check, breve and vector arrow.
  The check compares them as operators. The rule that the model may only
  quote maths (record 26) keeps the old reduction, because a passage's
  stored text keeps a PDF's fonts as they were: a summation as "X".
- **Greek letters are counted on their own,** exactly, outside the prose's
  slack.
- **TeX's extension fonts** set big operators and radicals where letters
  would be. In a page's layer they are now read as the symbols they draw:
  "X" and "P" as ∑, "Z" and "R" as ∫, and so on. "[" and the backslash are
  not mapped: in the same font they are also big brackets, which the first
  try took for ∪ and ∩, refusing four perfect readings. The symbol font's
  "p" is a root.
- **A symbol the page's layer never records is not compared.** OpenStax's
  *Calculus* draws every radical as lines, and sets a big integral in two
  pieces, ⌠ over ⌡ (read as one ∫). Without this rule, the fixes would have
  refused four of its correct pages.
- **A picture's placeholder is not text.** Page text drops Markdown images,
  `![Figure 5.20](image_url)`, which the model writes where a figure is.

## Testing

- **The benchmark's own tests** (`api/tests/test_maths_evaluation.py`) run
  in CI without typesetting anything:
  - the lectures are well formed, every formula renders, and the corpus
    shows every kind of notation at least five times;
  - the questions hold, and broken ones are reported;
  - the comparison sets presentation aside and counts every real change,
    each kind of change named;
  - each kind of planted mistake makes exactly the change it names, the
    same way on every run;
  - kept readings are reused, not asked for again;
  - the scoring decides what the app keeps;
  - the report rewrites only its marked tables.

  One more test typesets a lecture twice and checks that the two PDFs are
  identical. It runs only where Tectonic is installed.
- **The check's fixes** each have tests in `test_transcription.py`,
  `test_maths.py` and `test_page_maths.py`. The layers in them are written
  as TeX's fonts leave them: a prime "′", a hat "ˆ", "/∈", "(mod n)", ⌠
  and ⌡. One test pins a known limit: a variable's letter changed still
  passes.
- **32 deliberate breaks** of the fixes and the benchmark's rules. Each
  undoes or bends one rule: a formula's lines no longer joined, Greek
  letters back within the slack, a big bracket read as ∪, kept readings
  that ignore the image, and so on. 30 were caught at first. The two
  missed had no test: the `\prime` command, where every test wrote an
  apostrophe, and a table whose closing marker is missing. Both were
  added, and all 32 are caught.
- **Every fix was measured before and after** on the kept readings. Main's
  check is the same code with the fixes set aside.

## Consequences

- **What the check still cannot see is now known.**
  - A variable's letter changed, since Latin letters keep the slack the
    prose needs.
  - Order: a fraction turned upside down, an integral's bounds swapped,
    two matrix entries swapped.
  - What TeX draws as a rule: an overline, such as a repeating decimal's
    bar.
  - Absolute-value bars and division slashes, which the check does not
    compare.
  - Any symbol a PDF draws as a picture: on OpenStax's pages, a dropped root
    passes.

  - A difference that a page's optional characters, its figure labels,
    happen to balance.

  The misreadings on the pages the app kept, in the corpus and in the two
  books, were all of these kinds.
- **Whole first stays.** Halves first is faster on clean typesetting and
  slower on real books, where whole readings pass more often.
- **A cut just before a formula makes the model write a lead-in sentence of
  its own.** The check refuses such a half, so the page keeps its text
  layer. A better place to cut, or a new prompt version, is the next thing
  to measure. Either needs the corpus read again.
- **The comparison is strict about form.** Its "wrong" includes equal maths
  written otherwise. The report lists every formula it counts wrong, so the
  two can be told apart.
- **The readings are part of the repository** (`readings.json`, about 120
  KB). The results are written with only the formulas read wrong. A new
  model or prompt version is measured by reading the 20 pages again: 60
  parts, about 40 minutes.
- **Tectonic is a tool of the benchmark only.** Its first run downloads
  about 40 MB of TeX packages. CI's tests do not need it.
- **The textbooks' numbers cannot be reproduced from the repository**,
  since neither book is committed. Their pages and editions are named here,
  and the scripts that read and scored them used the benchmark's own
  modules.
- **Search keeps LaTeX's commands in its index.** Reading the maths neither
  helps nor harms it measurably on this corpus.
- **Backend coverage falls,** because the benchmark's database and model
  steps run only locally, as record 20's do. The parts that decide its
  numbers (comparison, planting, scoring, report) are tested.

