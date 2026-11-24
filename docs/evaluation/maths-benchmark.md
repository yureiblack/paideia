# Maths benchmark

This measures how well Paideia reads the maths in a PDF, how often its check
catches a misreading, whether reading the maths helps search find it, and
what practice it offers on it. It runs offline, on ten lectures written for
it, and every number below is written by the benchmark itself,
`scripts/evaluate_maths.py`. None is typed by hand. The design is explained
in decision record 30.

## Reproducing it

From the repository root, with the services running (`docker compose up -d`),
the virtual environment active and Tectonic installed
(`brew install tectonic`):

```
python scripts/evaluate_maths.py                # a few minutes, no model needed
python scripts/evaluate_maths.py --read         # also reads new pages with the local model
python scripts/evaluate_maths.py --practice     # also extracts concepts and chooses exercises
```

The model's readings of every page are kept in
[`maths/readings.json`](maths/readings.json), with the SHA-256 of the image
the model saw, the model and the prompt version. A run without `--read`
scores those readings again with the current code, so a change to the check
is measured in seconds; `--read` asks the local model only for pages it has
not read, about forty seconds a part. Each run rebuilds its own database, the
development database's name with `_maths_eval` appended, so development and
test data are never touched. It writes every number, page by page, to
[`maths/results.json`](maths/results.json), and rewrites the tables below.

The model's times depend on the machine. Its readings do not change between
runs: it reads at temperature 0, and a kept reading is reused for the same
image.

## The run

<!-- maths:run -->
| | |
|---|---|
| Run | 2026-11-24T08:06:43+00:00 |
| Commit | 0b50224 with uncommitted changes |
| Inputs fingerprint | f700cb03eb92 |
| Machine | Apple M3 Pro, 18 GB, macOS-26.5.2-arm64-arm-64bit-Mach-O |
| Model | ministral-3:8b, prompt page_transcription/v1 |
| Typesetting | Tectonic 0.17.0 |
| Corpus | 10 lectures, 20 pages, 860 formulas, 8650 words |
| Questions reviewed | 2026-11-24, in a second pass separate from writing them: every question and its evidence rechecked against the lectures by a reviewer given no access to the author's reasoning, its findings then reconciled one by one; four questions reworded, two alternative passages and two steadier quotes added. Not an independent human review. |
<!-- /maths:run -->

## Findings

<!-- maths:findings -->
- The check accepted the perfect reading of 20 of 20 pages.
- Read whole, the model got 775 of 860 formulas right (90.1%), and every formula on 6 of 20 pages.
- Read in halves, the model got 821 of 831 formulas right (98.8%), and every formula on 12 of 19 pages.
- The app would keep the model's reading of 14 of 20 pages, and 590 of their 594 formulas are right; the check let a differing formula through on 3 of them.
- Of the model's 21 wrong readings the check refused 16; of its 18 right readings it refused 4.
- Planted mistakes: 505 of 784 caught (64%).
- Always caught: a sign flipped (+ and −); a digit changed; a greek letter changed; δ read as δ, or δ as δ; a prime dropped (f′ read as f); a square root dropped; a big operator changed (σ for ∫, π for σ); ∂ read as d; a set relation reversed (∈ and ∉, ⊆ and ⊇); a set operation changed (∪ and ∩); a quantifier or connective changed (∀ and ∃, ∧ and ∨); a relation changed (≤ and ≥, ≠ read as =); a matrix entry left out; a displayed formula left out.
- Never caught: a variable's letter changed; a fraction turned upside down; a sum's or integral's bounds swapped; two matrix entries swapped.
- The notation read least well, whole page: norms and inner products 50%; aligned derivations 60%; augmented matrices 67%; determinant bars 67%; set operations (∪, ∩, ∖, ∅, complement) 69%.
- The app's search, MRR@10: 0.869 on the text layer, 0.836 with the model's readings, 0.891 with perfect readings; for maths typed as words 0.656, 0.601 and 0.708.
- A page took the model 83.3 s (median, both attempts when needed): about 9.3 hours for a 400-page textbook.
- Practice: 26 of 97 concepts were offered a computed exercise; 33 of 35 exercises were of a type their lecture teaches.
<!-- /maths:findings -->

## The corpus

Ten lectures, written for the benchmark in
[`maths/corpus/`](maths/corpus/): three of linear algebra (systems and row
reduction; matrices, inverses and determinants; vector spaces, eigenvalues
and orthogonality), then single-variable calculus, multivariable calculus,
differential equations, probability and statistics, sets, logic and proof,
series and complex numbers, and numerical methods. Every worked number in
them was checked.

Each is written in the very form the model is asked to write a page in:
Markdown, with its maths in LaTeX between dollar signs. The benchmark
typesets each with TeX, as most textbooks are, in Computer Modern, A4, with
a running header and page numbers, and the app reads the PDF exactly as it
reads an upload. Each paragraph and formula is labelled in the LaTeX, and
TeX records the page each label lands on, so what the source says on a page
is that page's perfect reading.

The lectures were written to show every kind of notation at least five
times. The kinds are named in `api/evaluation/notation.py`, and a test fails
if the corpus falls short of one.

## The check on perfect readings

The check (decision record 26) compares a reading with the PDF's own text
layer, character by character. A perfect reading should pass. One that does
not shows a quirk of the check: a way a correct page would be refused, and
keep its text layer, in any textbook typeset the same way.

<!-- maths:truth -->
20 of 20 perfect readings accepted.

| Lecture | Page | Why the check refused the perfect reading |
|---|---|---|
| | | none |
<!-- /maths:truth -->

## Planted mistakes

The model makes few mistakes on cleanly typeset pages, too few to say how
well the check catches each kind. So mistakes are planted: each page's
perfect reading gets exactly one change, of one kind, in one place, and the
check is asked whether the result agrees with the page. The kinds are in
`api/evaluation/maths_planted.py`. Some can never be seen by a check that
counts characters: a fraction turned upside down, two bounds swapped and two
entries swapped all leave the same characters on the page.

<!-- maths:planted -->
Planted in the 20 pages whose perfect reading the check accepts, up to 3 of each kind per page.

| Mistake | Planted | Caught | Share caught | A mistake it let through |
|---|---|---|---|---|
| A sign flipped (+ and −) | 60 | 60 | 100% |  |
| A digit changed | 60 | 60 | 100% |  |
| A variable's letter changed | 60 | 0 | 0% | `R_i \to cR_i` → `R_j \to cR_i` |
| A Greek letter changed | 41 | 41 | 100% |  |
| Δ read as δ, or δ as Δ | 14 | 14 | 100% |  |
| A superscript dropped | 57 | 33 | 58% | `(AB)^{-1} = B^{-1} A^{-1}, \qquad (A^{T})^{-1} = (A^{-1})^{T` → `(AB)^{-1} = B^{-1} A^{-1}, \qquad (A)^{-1} = (A^{-1})^{T}` |
| A subscript dropped | 60 | 38 | 63% | `(s_1, s_2, \ldots, s_n)` → `(s_1, s_2, \ldots, s)` |
| A prime dropped (f′ read as f) | 20 | 20 | 100% |  |
| A square root dropped | 16 | 16 | 100% |  |
| An accent dropped (hat, bar, dot, arrow) | 20 | 14 | 70% | `\|z\| = \sqrt{a^2 + b^2} = \sqrt{z \overline{z}}` → `\|z\| = \sqrt{a^2 + b^2} = \sqrt{z z}` |
| A fraction turned upside down | 51 | 0 | 0% | `\frac{1}{2}` → `\frac{2}{1}` |
| A big operator changed (Σ for ∫, Π for Σ) | 39 | 39 | 100% |  |
| A sum's or integral's bounds swapped | 35 | 0 | 0% | `(AB)_{ij} = \sum_{k=1}^{n} a_{ik} b_{kj} = a_{i1} b_{1j} + a` → `(AB)_{ij} = \sum_{n}^{k=1} a_{ik} b_{kj} = a_{i1} b_{1j} + a` |
| ∂ read as d | 6 | 6 | 100% |  |
| A set relation reversed (∈ and ∉, ⊆ and ⊇) | 14 | 14 | 100% |  |
| A set operation changed (∪ and ∩) | 6 | 6 | 100% |  |
| A quantifier or connective changed (∀ and ∃, ∧ and ∨) | 11 | 11 | 100% |  |
| A relation changed (≤ and ≥, ≠ read as =) | 41 | 41 | 100% |  |
| A matrix entry left out | 30 | 30 | 100% |  |
| Two matrix entries swapped | 25 | 0 | 0% | `\left[\begin{array}{ccc\|c} 1 & -2 & 1 & 0 \\ 0 & 2 & -8 & 8 ` → `\left[\begin{array}{ccc\|c} 1 & -2 & 1 & 0 \\ 2 & 0 & -8 & 8 ` |
| A word of the prose left out | 60 | 4 | 7% | `undone` → `` |
| A displayed formula left out | 58 | 58 | 100% |  |
<!-- /maths:planted -->

## The model's readings

Every page is read both ways the app reads it: whole, and in two halves,
each seen larger. Each reading is made page text as the app makes it, and
compared with the page's truth. A formula is read right when every one of
its tokens is there, in order, once presentation is set aside: spacing,
bracket sizes, the bracket style of a matrix, `\dfrac` for `\frac`, font
commands, braces around one token, commas, and other spellings of one symbol.
Everything else counts: signs, digits, letters, Greek letters, operators,
accents, primes, scripts, roots, fractions and matrix cells. The comparison
is in `api/evaluation/maths_compare.py`.

<!-- maths:reading -->
| Attempt | Pages usable | Formulas right | Pages with every formula right | Maths tokens wrong | Prose words wrong | Median seconds |
|---|---|---|---|---|---|---|
| Whole page | 20 of 20 | 775 of 860 (90.1%) | 6 of 20 | 5.1% | 0.3% | 51.6 |
| In two halves | 19 of 20 | 821 of 831 (98.8%) | 12 of 19 | 0.8% | 1.2% | 57.2 |
<!-- /maths:reading -->

The app reads a page whole, and in halves only if the whole reading fails
its check; a page that fails both keeps its text layer. From the two
attempts the benchmark works out what the app would have kept:

<!-- maths:app -->
| | |
|---|---|
| Pages read whole and accepted | 7 |
| Pages accepted on the second attempt, in halves | 7 |
| Pages that kept the PDF's text layer | 6 |
| Formulas right on the pages read | 590 of 594 (99.3%) |
| Pages read with a wrong formula the check let through | 3 |
| Model time per page, median (both attempts when needed) | 83.3 s |
<!-- /maths:app -->

### How the check judged the model's readings

A reading is wrong when any of its formulas is.

<!-- maths:check -->
| Attempt | Wrong, refused | Wrong, accepted | Right, refused | Right, accepted | Not usable |
|---|---|---|---|---|---|
| Whole page | 12 | 2 | 1 | 5 | 0 |
| In two halves | 4 | 3 | 3 | 9 | 1 |

Right readings were refused because:

- Its words differ from the PDF's text: 3
- Its operators differ from the PDF's text: 1
<!-- /maths:check -->

### By kind of notation

<!-- maths:notation -->
| Notation | Formulas in the corpus | Read right, whole page | Read right, in halves | Right among the formulas the app keeps |
|---|---|---|---|---|
| Greek letters | 109 | 85% | 99% | 100% |
| Sigmas (σ, Σ as a letter) | 11 | 91% | 100% | n/a |
| Deltas (δ, Δ) | 17 | 94% | 100% | 100% |
| Bold, blackboard and script letters | 104 | 79% | 97% | 100% |
| Number sets (ℕ, ℤ, ℚ, ℝ, ℂ) | 24 | 96% | 100% | 100% |
| Subscripts | 179 | 88% | 97% | 98% |
| Superscripts | 191 | 90% | 98% | 98% |
| Fractions | 109 | 90% | 97% | 99% |
| Roots | 15 | 87% | 100% | 100% |
| Binomial coefficients | 6 | 83% | 100% | 67% |
| Accents (hat, bar, tilde, dots, arrow) | 36 | 81% | 97% | 94% |
| Primes (f′, f″) | 35 | 83% | 97% | 96% |
| Sums (Σ) | 32 | 91% | 94% | 97% |
| Products (Π) | 5 | 80% | 100% | 100% |
| Integrals (∫, ∬, ∮) | 24 | 88% | 96% | 100% |
| Big unions and intersections | 5 | 80% | 100% | 100% |
| Limits | 16 | 88% | 100% | 100% |
| Derivatives (d/dx, f′, ẋ) | 47 | 87% | 98% | 97% |
| Partial derivatives (∂) | 9 | 78% | 78% | 100% |
| Gradients (∇) | 8 | 88% | 100% | 100% |
| Infinity | 24 | 83% | 100% | 100% |
| Matrices | 13 | 85% | 100% | 100% |
| Determinant bars | 6 | 67% | 100% | 100% |
| Augmented matrices | 6 | 67% | 100% | 100% |
| Transposes and inverses | 24 | 96% | 100% | 100% |
| Norms and inner products | 20 | 50% | 95% | 100% |
| Dots in sums and matrices (…, ⋯, ⋮, ⋱) | 29 | 83% | 100% | 100% |
| Set membership and inclusion (∈, ∉, ⊂, ⊆) | 28 | 93% | 100% | 100% |
| Set operations (∪, ∩, ∖, ∅, complement) | 13 | 69% | 100% | 100% |
| Sets written out ({x : …}) | 16 | 94% | 100% | 100% |
| Logic (∀, ∃, ¬, ∧, ∨, ⇒, ⇔) | 19 | 100% | 100% | 100% |
| Inequalities (<, ≤, ≥, ≪) | 51 | 94% | 100% | 100% |
| Other relations (≠, ≈, ≡, ∼, ⊥) | 33 | 85% | 94% | 96% |
| Arrows and maps (→, ↦, ↔) | 36 | 89% | 100% | 100% |
| Named functions (sin, ln, det, …) | 77 | 96% | 99% | 98% |
| Absolute values, floor and ceiling | 39 | 77% | 97% | 96% |
| Cases (piecewise definitions) | 6 | 100% | 100% | 100% |
| Aligned derivations | 5 | 60% | 80% | 100% |
| Probability (P(A | B), 𝔼, Var, 𝒩) | 22 | 73% | 100% | 100% |
| Complex numbers (conjugate, Re, Im) | 7 | 100% | 100% | 100% |
| Congruences (mod) | 6 | 100% | 83% | 100% |
<!-- /maths:notation -->

### What the model got wrong

<!-- maths:changes -->
| How a wrong formula differed | Times |
|---|---|
| left out | 94 |
| structure | 72 |
| added | 20 |
| letter | 10 |
| digit | 5 |
<!-- /maths:changes -->

<!-- maths:wrong -->
| Lecture | Page | Attempt | Check | The page says | The reading has |
|---|---|---|---|---|---|
| 01 | 1 | whole | refused | `{ R _ 3 \rightarrow R _ 3 - 5 R _ 1 }` | `(nothing)` |
| 01 | 2 | whole | refused | `{ R _ 2 \rightarrow R _ 2 - 2 R _ 1 }` | `(nothing)` |
| 01 | 2 | whole | refused | `0` | `(nothing)` |
| 02 | 1 | halves | accepted | `(nothing); (nothing)` | `(; )` |
| 02 | 2 | whole | refused | `0; - 1` | `5; 4` |
| 03 | 1 | halves | accepted | `(; (nothing); )` | `\begin{matrix}; \\; \end{matrix}` |
| 03 | 1 | halves | accepted | `(; (nothing); )` | `\begin{matrix}; \\; \end{matrix}` |
| 03 | 2 | whole | refused | `\in \mathbb R ^ n` | `ℝⁿ` |
| 03 | 2 | whole | refused | `\langle; \rangle; u ^ T v; u _ 1 v _ 1; \dots; u _ n v _ n` | `(nothing); (nothing); uᵀv; u₁v₁; (nothing); uₙvₙ` |
| 03 | 2 | whole | refused | `\\|; \\|; \sqrt { \langle; \rangle }` | `(nothing); (nothing); (nothing); (nothing)` |
| 03 | 2 | whole | refused | `\perp` | `(nothing)` |
| 03 | 2 | whole | refused | `\langle; \rangle` | `(nothing); (nothing)` |
| 03 | 2 | whole | refused | `(; )` | `(nothing); (nothing)` |
| 03 | 2 | whole | refused | `( -; )` | `(nothing); (nothing)` |
| 03 | 2 | whole | refused | `\| \langle; \rangle \| \leq \\|; \\| \\|; \\|` | `(nothing); (nothing); (nothing); (nothing)` |
| 03 | 2 | whole | refused | `\theta` | `θ` |
| 03 | 2 | whole | refused | `\theta; \frac { \langle; \rangle } { \\|; \\| \\|; \\| }` | `θ; (nothing); (nothing); (nothing); (nothing)` |
| 03 | 2 | whole | refused | `- \hat y` | `ŷ` |
| 03 | 2 | whole | refused | `\hat y` | `ŷ` |
| 03 | 2 | whole | refused | `\\|; - A; \\|` | `(nothing); a; (nothing)` |
| 03 | 2 | whole | refused | `(; ) (` | `(nothing); (nothing)` |
| 03 | 2 | whole | refused | `) (; )` | `(nothing); (nothing)` |
| 03 | 2 | whole | refused | `(; )` | `(nothing); (nothing)` |
| 03 | 2 | whole | refused | `\\|; - A; \\| ^ 2` | `(nothing); a; ²` |
| 05 | 1 | whole | refused | `(nothing); /` | `\frac; {` |
| 05 | 1 | whole | refused | `(nothing)` | `\\` |
| 05 | 1 | whole | refused | `x \partial; (nothing)` | `(nothing); ^ 2` |
| 05 | 1 | whole | refused | `\frac { \partial f } { \partial z }` | `(nothing)` |
| 05 | 1 | whole | refused | `3; 4` | `2; 6` |
| 05 | 1 | whole | refused | `\frac 6 5 +` | `(nothing)` |
| 05 | 1 | whole | refused | `1` | `0` |
| 05 | 1 | halves | refused | `(nothing); /` | `\frac; {` |
| 05 | 1 | halves | refused | `x \partial; (nothing)` | `(nothing); ^ 2` |
| 05 | 2 | halves | refused | `\oint` | `the transcribed content from the image is \int` |
| 06 | 1 | whole | refused | `(nothing)` | `\neq 0` |
| 06 | 1 | halves | refused | `(nothing)` | `0 the general solution to a second order linear differential equation ` |
| 06 | 2 | whole | refused | `'; A x` | `(nothing); ax` |
| 06 | 2 | whole | refused | `\lambda` | `λ` |
| 06 | 2 | whole | refused | `A` | `a` |
| 06 | 2 | whole | refused | `(; ); ^ { \lambda t } v` | `(nothing); (nothing); λtv` |
| 06 | 2 | whole | refused | `A` | `a` |
| 06 | 2 | whole | refused | `v _ 1 v _ 2` | `v₁ v₂` |
| 06 | 2 | whole | refused | `(; ); c _ 1 e ^ { \lambda _ 1 t } v _ 1; c _ 2 e ^ { \lambda _ 2 t } v` | `(nothing); (nothing); c₁e λ₁tv₁; c₂e λ₂tv₂` |
| 06 | 2 | whole | refused | `(nothing); (nothing); '` | `'; '; (nothing)` |
| 06 | 2 | whole | refused | `-` | `(nothing)` |
| 06 | 2 | whole | refused | `(; )` | `(nothing); (nothing)` |
| 06 | 2 | whole | refused | `(; -; )` | `(nothing); (nothing); (nothing)` |
| 06 | 2 | whole | refused | `(; -; )` | `(nothing); (nothing); (nothing)` |
| 06 | 2 | whole | refused | `(; )` | `(nothing); (nothing)` |
| 06 | 2 | whole | refused | `'; (; )` | `(nothing); (nothing); (nothing)` |
| 06 | 2 | whole | refused | `\Delta t` | `δt` |
| 06 | 2 | whole | refused | `'` | `(nothing)` |
| 06 | 2 | whole | refused | `(; )` | `(nothing); (nothing)` |
| 06 | 2 | whole | refused | `y _ { 1 0 } =; ^ {; } \approx` | `y₁₀; (nothing); (nothing)` |
| 06 | 2 | whole | refused | `\approx` | `(nothing)` |
| 07 | 1 | whole | refused | `\Omega` | `ω` |
| 07 | 1 | whole | refused | `A \subseteq \Omega` | `a ω` |
| 07 | 1 | whole | refused | `P` | `p` |
| 07 | 1 | whole | refused | `P ( \Omega )` | `p ω` |
| 07 | 1 | whole | refused | `\leq P ( A ) \leq` | `p a` |
| 07 | 1 | whole | refused | `P ( \bigcup _ {; } ^ \infty A _; ); \sum _ {; } ^ \infty P ( A _; )` | `p; a; (nothing); (nothing); p a; (nothing)` |
| 07 | 1 | whole | refused | `A _` | `a` |
| 07 | 1 | whole | refused | `P ( A ^; ); - P ( A )` | `p a; (nothing); p a` |
| 07 | 1 | whole | refused | `\| \Omega \|` | `ω` |
| 07 | 1 | whole | refused | `P ( A ); \frac { \| A \| } { \| \Omega \| }` | `p a; a ω` |
| 07 | 1 | whole | refused | `A` | `a` |
| 07 | 1 | whole | refused | `B` | `b` |
| 07 | 1 | whole | refused | `A` | `a` |
| 07 | 1 | whole | refused | `B` | `b` |
| 07 | 1 | whole | refused | `P ( A \cap B ); P ( A ) P ( B )` | `p a b; p a p b` |
| 07 | 1 | whole | refused | `B` | `b` |
| 07 | 1 | whole | refused | `A` | `a` |
| 07 | 1 | whole | refused | `A _; \dots A _` | `a; a` |
| 07 | 1 | whole | refused | `P ( A _; \cap \dots \cap A _; ); \prod _ {; } ^; P ( A _; )` | `p a; a; (nothing); (nothing); (nothing); p a; (nothing)` |
| 07 | 1 | whole | refused | `B _; \dots B _` | `b; b` |
| 07 | 1 | whole | refused | `\Omega` | `ω` |
| 07 | 1 | whole | refused | `P ( A ); \sum _ {; } ^; P ( A \| B _; ) P ( B _; )` | `p a; (nothing); (nothing); p a b; p b; (nothing)` |
| 07 | 1 | whole | refused | `X` | `x` |
| 07 | 1 | whole | refused | `(; ); P ( X; )` | `(nothing); (nothing); p x; (nothing)` |
| 07 | 1 | whole | refused | `P (; \leq X \leq; ); \int _; ^; (; ) d x` | `p; x; (nothing); (nothing); (nothing); (nothing); dx` |
| 07 | 1 | whole | refused | `\mathbb; \mathbb; \infty; \infty` | `(nothing); (nothing); ∞; ∞` |
| 07 | 1 | whole | refused | `\mathbb E [ a X; b Y ]; a \mathbb E [ X ]; b \mathbb E [ Y ]` | `e ax; by; ae x; be y` |
| 07 | 1 | whole | refused | `\mu; \mathbb E [ X ]` | `μ; e x` |
| 07 | 1 | whole | refused | `var; \mathbb; \mu; \mathbb; \mu \mathbb; \mu; \mathbb; \mu` | `V a r; (nothing); μ; (nothing); μ; μ; (nothing); μ` |
| 07 | 2 | whole | refused | `9 1` | `3 5` |
| 08 | 1 | whole | refused | `\cap` | `\cup` |
| 08 | 2 | whole | accepted | `{; - 1 }; (nothing)` | `(nothing); (nothing); {` |
| 08 | 2 | halves | refused | `(nothing)` | `n ( n + 1 ) + 2 ( n + 1 ) } 2 = \frac {` |
| 08 | 2 | halves | refused | `(nothing)` | `^ k` |
| 09 | 1 | whole | refused | `(nothing); (nothing)` | `^ 2; ^ 2` |
| 09 | 1 | whole | refused | `[ n ]; 1` | `(nothing); \infty` |
| 09 | 2 | whole | refused | `(nothing); (nothing)` | `+ i; 4` |
| 10 | 1 | whole | accepted | `\overline` | `(nothing)` |
| 10 | 1 | whole | accepted | `\|; \|` | `(nothing); (nothing)` |
| 10 | 1 | halves | accepted | `/ h` | `(nothing)` |
<!-- /maths:wrong -->

## Time

<!-- maths:timing -->
| Step | Time |
|---|---|
| Parse a page (text, blocks, headings) | 9.0 ms |
| Find which pages hold maths | 9.1 ms a page |
| Render a page for the model | 32.7 ms |
| Read a page's text layer for the check | 22.7 ms |
| Make page text and check it | 4.5 ms |
| The model's reading of a page, median | 83.3 s |
| A 400-page textbook, at that rate | 9.3 hours |
| Read the lectures again with read pages in place, and embed | 4.46 s for 20 pages |
| Read the lectures again with truth pages in place, and embed | 6.11 s for 20 pages |
<!-- /maths:timing -->

## Finding the maths again

The 48 questions in [`maths/questions.json`](maths/questions.json) are asked
of the lectures read three ways: as the PDF's text layer has them, with the
model's readings in place where the check accepted them, and with perfect
readings in place. Ten name their topic, ten describe it in other words,
twenty ask for a formula, and eight type the maths itself as words, as a
learner would type it into a search box ("nabla f dot u"). Each names the
passage that answers it by a quote of the lecture's prose, which reads the
same in all three. The methods and scores are those of the retrieval
benchmark (`retrieval-benchmark.md`).

<!-- maths:retrieval -->
| Lectures as | Method | Recall@5 | MRR@10 | Right passage first |
|---|---|---|---|---|
| The PDF's text layer (maths not read) | A. Semantic | 0.896 | 0.738 | 60% |
| The PDF's text layer (maths not read) | B. Lexical | 0.896 | 0.843 | 79% |
| The PDF's text layer (maths not read) | C. Hybrid (fused) | 0.938 | 0.846 | 79% |
| The PDF's text layer (maths not read) | D. Hybrid + reranker (the app) | 0.958 | 0.869 | 79% |
| The model's readings, where the check accepted them | A. Semantic | 0.896 | 0.764 | 65% |
| The model's readings, where the check accepted them | B. Lexical | 0.896 | 0.791 | 71% |
| The model's readings, where the check accepted them | C. Hybrid (fused) | 0.958 | 0.812 | 71% |
| The model's readings, where the check accepted them | D. Hybrid + reranker (the app) | 0.958 | 0.836 | 73% |
| Perfect readings | A. Semantic | 0.896 | 0.783 | 67% |
| Perfect readings | B. Lexical | 0.938 | 0.814 | 73% |
| Perfect readings | C. Hybrid (fused) | 0.979 | 0.850 | 77% |
| Perfect readings | D. Hybrid + reranker (the app) | 1.000 | 0.891 | 81% |
<!-- /maths:retrieval -->

The app's search, MRR@10, by kind of question:

<!-- maths:retrieval-kinds -->
| Question | The PDF's text layer (maths not read) | The model's readings, where the check accepted them | Perfect readings |
|---|---|---|---|
| Names the term | 0.950 | 0.900 | 0.950 |
| In other words | 0.861 | 0.800 | 0.875 |
| Asks for a formula | 0.917 | 0.917 | 0.942 |
| Types the maths as words | 0.656 | 0.601 | 0.708 |
| All | 0.869 | 0.836 | 0.891 |
<!-- /maths:retrieval-kinds -->

Postgres's keyword index splits LaTeX at its backslashes, so a passage whose
maths was read is also indexed under its LaTeX commands and environment
names (decision record 24):

<!-- maths:latex-words -->
| Lectures as | Passages | LaTeX commands, most frequent | Environments |
|---|---|---|---|
| The PDF's text layer (maths not read) | 70 | none | none |
| The model's readings, where the check accepted them | 69 | \frac 102, \mathbf 92, \begin 40, \sum 34, \infty 30, \times 29 | pmatrix 27, vmatrix 5, cases 4, bmatrix 3, align* 1 |
| Perfect readings | 73 | \frac 162, \mathbf 142, \begin 52, \mathbb 46, \partial 42, \to 40 | pmatrix 20, array 10, vmatrix 7, cases 6, aligned 5, bmatrix 4 |
<!-- /maths:latex-words -->

## Practice

With `--practice`, the model extracts the concepts of the lectures as the
app has read them, and chooses computed exercises for each as the app does
(decision record 27): the model picks types from the catalogue, and a type
is kept only when the concept's passages use its words. Each type offered is
judged against the types its lecture teaches, listed in
[`maths/exercise-labels.json`](maths/exercise-labels.json). The catalogue is
linear algebra, so outside the first three lectures any exercise offered is
a misfire.

<!-- maths:practice -->
| | |
|---|---|
| Concepts extracted from the lectures as read | 97 |
| Concepts offered at least one computed exercise | 26 |
| Exercises offered | 35 |
| Exercises of a type their lecture teaches | 33 of 35 (94%) |
| Exercise types the lectures teach that were offered somewhere | 10 of 12 |
| Time to extract concepts, and to choose exercises | 969.5 s and 702.7 s |

| Concept | Lectures | Exercise offered that its lecture does not teach |
|---|---|---|
| Matrix inverse | 02 | reduced_form |
| Characteristic Equation | 03, 06 | determinant |
<!-- /maths:practice -->
