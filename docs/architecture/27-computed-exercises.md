# 27. Computed exercises

Date: 2026-11-22
Status: accepted

## Context

Practice so far was written by the model: four items per concept, each
checked against its passages (record 14). That works for what a passage
says, not for what a learner of mathematics must be able to do: compute a
determinant, row reduce a matrix, find eigenvectors. The model cannot be
trusted with that. It is weak at arithmetic, and record 26 made it quote
maths, never work it out.

Record 24 settled the outline for this phase:
- the model only picks which types of exercise fit a concept, from a fixed
  catalogue;
- the backend makes the numbers, computes the answer in exact fractions,
  writes the worked solution step by step and marks the answer;
- new numbers on every review;
- answers typed as numbers in cells, nothing typed evaluated as code;
- a small exact-arithmetic module of the project's own, not sympy.

## What the prototype showed

- **Clean numbers come from building backward.** Each exercise is made
  from its answer:
  - a chosen solution, for a system of equations;
  - a chosen reduced form, hidden by an invertible integer matrix, for
    reduction, rank and the null space;
  - chosen eigenvalues, hidden by a change of basis.

  Over 1,000 exercises of each of the 9 types, every answer agreed with
  numpy. Every prompt and step rendered. No number was larger than 60, and
  no denominator larger than 6. Each took under half a millisecond.
- **Random vectors give ugly fractions.** The first independence exercise
  used random vectors, and its steps had denominators up to 70. Built from
  a reduced form like the others, they stay at 4 or less.
- **The model's choice needs a check.** Asked which types fit 13 concepts
  from the linear algebra textbook and the operating systems lectures, it
  chose well for maths: row reduction got the reduced form, the
  determinant and cofactor expansion the determinant, the characteristic
  polynomial and diagonalization eigenvalues. But it never chose none:
  deadlock and the convoy effect got a system of equations, page faults a
  null space. Keeping a type only if the concept's own passages use its
  words removed all of those. One word had to go: an operating system's
  "kernel" made page faults look like a null space.

## Decisions

### Nine types, small and exact

| Type | Asks for |
|---|---|
| Determinant | The determinant of a 2 by 2 or 3 by 3 matrix |
| A system | The solution of three equations in three unknowns |
| Reduced form | The reduced row echelon form of a 3 by 4 matrix |
| Rank | The rank of a 3 by 4 matrix |
| Inverse | The inverse of a 2 by 2 or 3 by 3 matrix |
| Product | The product of two small matrices |
| Null space | A basis of the null space of a 3 by 4 matrix of rank 2 |
| Independence | Whether three vectors are independent, and weights if not |
| Eigenvalues | The eigenvalues of a 2 by 2 matrix, and an eigenvector for each |

`app/exact.py` computes them on Python's own `Fraction`: exact, with no
dependency. Row reduction records each operation and the matrix after it,
which is what a worked solution shows. It picks a pivot of 1 or −1 when
there is one, to keep the numbers small.

### The model chooses, the passages confirm

When practice is prepared for a concept, the model is asked which types
practise it (prompt `exercise_types/v1`). It can only name types from the
catalogue. A type is kept only if the concept's own passages use its words,
such as "eigenvalue" or "row echelon"; a concept gets at most two.

- When no passage uses the words of any type, the model is not asked at
  all. That saves a call for every concept that is not maths.
- If choosing fails, for example because the model cannot be reached, the
  concept keeps its written items, and the reason is recorded.
- An exercise cites the passages its type was checked against, so its
  answer shows a source like any other item.

The practice generation keeps its identity (record 14). So concepts
prepared before this phase get exercises the next time their practice is
written, instead of every environment showing its concepts as needing
preparation again.

### New numbers on every review

An exercise item stores only its type. Its numbers come from a seed: the
item and how many times it has been answered. So every review is new, and
an answer is marked against the very numbers it was given. The page sends
back which variant it showed. A variant the item has not reached yet is
refused as out of date.

### Answers in cells, read exactly, never evaluated

- Each number is typed in a cell: an integer, a fraction such as `3/4`, or
  a decimal such as `-0.5`. It is read as an exact fraction. Anything else
  is refused, with which cell and why, and nothing is recorded. `2+3` is
  not a number here, so nothing typed is ever evaluated.
- An answer with one right form, such as a determinant or a matrix, is
  compared cell by cell.
- An answer with many right forms is checked by what it must satisfy:
  - a basis of the null space, by each vector being in it and nonzero, and
    the vectors independent;
  - an eigenvector, by Av = λv for the eigenvalue beside it;
  - dependence weights, by giving the zero vector.

  Any right answer is accepted, not only the one the worked solution
  reaches.
- A partly right answer counts as wrong, and says which cells were right:
  "8 of the 9 entries are right."

### Exercises are practice items

An exercise is a learning item of kind `exercise`, graded by the key. It
counts in the learner's state, its spaced review and today's plan like any
other item. In the plan it is estimated at three minutes. A concept not
yet prepared is still estimated from the four written kinds, since only
some concepts get exercises.

On the page, an exercise shows its cells under the question: a row for a
vector, brackets for a matrix, a choice before weights, an eigenvector
beside each eigenvalue. Once marked, a wrong cell is struck through in the
accent colour, and the worked solution follows, a step a line.

## Testing

- **Every type against an independent computation:** for each of the nine
  types, 200 exercises are generated and their answers checked with numpy.
  numpy works in floating point and shares no code with the exact module.
  Each answer is also marked right by the exercise's own marking.
- **What the learner reads:** every prompt, key and step renders, with no
  number above 60 and no denominator above 6.
- **The worked solution ends at the stored answer:** the last matrix of a
  reduction is the answer, each entry of a product ends its own line, and
  so on for every type.
- **A review shows new numbers:** six variants of an item give at least five
  different exercises, and a seed always gives the same one.
- **Marking:**
  - a wrong number is wrong;
  - a partly right matrix says which entries were right;
  - empty cells, words, `2+3`, code, division by zero and the wrong number
    of cells are refused, never evaluated;
  - integers, fractions, decimals and a typographic minus are read exactly;
  - another basis of the null space, eigenvalues in the other order with
    scaled eigenvectors, and weights in another proportion are right;
  - vectors not in the null space, vectors not independent, a vector that
    is not an eigenvector, wrong eigenvalues, zero weights and the wrong
    choice are each refused with their reason.
- **The choice:** kept only where the concept's passages use the type's
  words; never asked when nothing fits; at most two; a failed choice leaves
  the written items; an exercise cites only the passages its type was
  checked against.
- **Through the API:** an exercise is shown with a variant and a form,
  marked exactly with its worked solution, counted in the learner's state,
  and shown with new numbers once answered; an unreadable answer, and one
  for a variant not reached yet, are refused and not recorded.
- **The page:** each form's cells and their order, the choice before
  weights, wrong cells marked, and a session showing the worked solution.
- **The end-to-end journey** gained a step. It prepares the practice of a
  lecture on eigenvalues, answers an eigenvalue exercise wrongly on
  purpose, and checks the marking and the typeset worked solution.
- **Deliberate breaks.** 23 were made. The first run caught 19. The 4 it
  missed were gaps in the tests: an exercise citing every passage of its
  concept, eigenvectors not in whole numbers, more than two exercises, and
  one break whose pattern was stale. Tests were added; all 23 are caught.

### In the running app, with the real model

The check ran on a stack of its own, with ministral-3:8b on an Apple M3
Pro. The document was the 16 pages of the linear algebra textbook used for
record 26, read from its text layer.

- **Choosing:** practice was prepared for all 6 concepts in 191 seconds,
  the choice of exercises included. The model's choices, after the check:
  - diagonalizable matrix: inverse and eigenvalues;
  - free variable: reduced form. Its null space was refused, as its
    passages never say "null space";
  - parametric form: a system of equations, its null space refused too;
  - reduced row echelon form: reduced form;
  - row reduction: reduced form and a system of equations.

  That is 7 exercises for 5 concepts. The sixth, the eigenspace, got no
  practice: record 26's rule dropped its four written items, which wrote
  "λ = 2" where its passages show only "f(2) = 0".
- **Answering, on a computer:** an eigenvalue exercise was answered with
  the answer the app's own code computes for the item and variant shown.
  It was marked right, cited page 15, and its worked solution ran from the
  characteristic polynomial to both eigenvectors.
- **Answering, on a phone in the dark theme:** a 2 by 2 inverse was answered
  wrongly on purpose. All four cells were struck through, "0 of the 4
  entries are right" was said, and the seven steps of the worked solution
  followed. The page kept to the phone's 390 pixels.
- **One fix:** the worked solution wrote "A − 1I" where it should say
  "A − I". It no longer does.
- There were no console errors.

## Consequences

- **The catalogue is linear algebra, and small.** Other topics, and larger
  matrices, mean new types; the catalogue is built so that adding one is a
  generator, a form and its words.
- **A choice can miss.** A concept whose passages use none of a type's
  words gets no exercise, even if the model was right. A concept about
  similar matrices, whose page never says "inverse" in words, got none.
- **The worked solution follows one method.** A learner who expands a
  determinant along another row, or reduces in another order, reaches the
  same answer by other steps. Only the answer is marked.
- **Exercises arrive with new practice.** Concepts prepared before this
  phase get them when their practice is next written.
