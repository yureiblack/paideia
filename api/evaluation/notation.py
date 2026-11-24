"""The kinds of mathematical notation the maths benchmark covers.

Purpose
-------
Reading maths is only as good as its weakest notation: a model that writes
matrices perfectly may drop the prime of a derivative, and a check that
counts digits may never notice a lost square root. So the benchmark names
every kind of notation it means to test, makes sure the corpus uses each
kind in several formulas (a test fails otherwise), and reports how well each
kind is read and how often the check catches a mistake in it.

A kind is recognised in a formula's LaTeX by a pattern. One formula usually
shows several kinds: \\(\\sum_{i=1}^{n} \\sigma_i^2\\) is a sum, a Greek
letter, a sigma, a subscript and a superscript.
"""

import re
from dataclasses import dataclass

_GREEK_LOWER = (
    "alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|iota|kappa|"
    "lambda|mu|nu|xi|pi|varpi|rho|varrho|sigma|varsigma|tau|upsilon|phi|varphi|chi|"
    "psi|omega"
)
_GREEK_UPPER = "Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega"


@dataclass(frozen=True)
class Kind:
    name: str  # a short key, as results.json writes it
    label: str  # as the report writes it
    pattern: re.Pattern[str]

    def found_in(self, latex: str) -> bool:
        return bool(self.pattern.search(latex))


def _kind(name: str, label: str, pattern: str) -> Kind:
    return Kind(name, label, re.compile(pattern))


KINDS: tuple[Kind, ...] = (
    # Letters
    _kind("greek", "Greek letters", rf"\\({_GREEK_LOWER}|{_GREEK_UPPER})(?![A-Za-z])"),
    _kind("sigma", "Sigmas (σ, Σ as a letter)", r"\\(sigma|Sigma)(?![A-Za-z])"),
    _kind("delta", "Deltas (δ, Δ)", r"\\(delta|Delta)(?![A-Za-z])"),
    _kind(
        "styled",
        "Bold, blackboard and script letters",
        r"\\(mathbf|boldsymbol|mathbb|mathcal)\{",
    ),
    _kind("number_sets", "Number sets (ℕ, ℤ, ℚ, ℝ, ℂ)", r"\\mathbb\{[NZQRC]\}"),
    # Layout
    _kind("subscript", "Subscripts", r"_"),
    _kind("superscript", "Superscripts", r"\^"),
    _kind("fraction", "Fractions", r"\\[dt]?frac(?![A-Za-z])"),
    _kind("root", "Roots", r"\\sqrt(?![A-Za-z])"),
    _kind("binomial", "Binomial coefficients", r"\\binom(?![A-Za-z])"),
    _kind(
        "accent",
        "Accents (hat, bar, tilde, dots, arrow)",
        r"\\(hat|widehat|bar|overline|tilde|widetilde|dot|ddot|vec)(?![A-Za-z])",
    ),
    _kind("prime", "Primes (f′, f″)", r"'"),
    # Big operators
    _kind("sum", "Sums (Σ)", r"\\sum(?![A-Za-z])"),
    _kind("product", "Products (Π)", r"\\prod(?![A-Za-z])"),
    _kind("integral", "Integrals (∫, ∬, ∮)", r"\\(int|iint|iiint|oint)(?![A-Za-z])"),
    _kind("big_set", "Big unions and intersections", r"\\(bigcup|bigcap)(?![A-Za-z])"),
    _kind("limit", "Limits", r"\\(lim|limsup|liminf)(?![A-Za-z])"),
    # Calculus
    _kind(
        "derivative",
        "Derivatives (d/dx, f′, ẋ)",
        r"\\frac\{d[\^ {]|\\frac\{d\}|'|\\dot\{|\\ddot\{",
    ),
    _kind("partial", "Partial derivatives (∂)", r"\\partial(?![A-Za-z])"),
    _kind("nabla", "Gradients (∇)", r"\\nabla(?![A-Za-z])"),
    _kind("infinity", "Infinity", r"\\infty(?![A-Za-z])"),
    # Linear algebra
    _kind("matrix", "Matrices", r"\\begin\{[pbB]?matrix\}"),
    _kind("determinant", "Determinant bars", r"\\begin\{vmatrix\}"),
    _kind("augmented", "Augmented matrices", r"\\begin\{array\}\{[^}]*\|"),
    _kind("transpose_inverse", "Transposes and inverses", r"\^\{?(T|\\top|-1)\}?"),
    _kind("norm", "Norms and inner products", r"\\\||\\langle(?![A-Za-z])"),
    _kind(
        "dots",
        "Dots in sums and matrices (…, ⋯, ⋮, ⋱)",
        r"\\(ldots|cdots|vdots|ddots|dots)(?![A-Za-z])",
    ),
    # Sets and logic
    _kind(
        "set_relation",
        "Set membership and inclusion (∈, ∉, ⊂, ⊆)",
        r"\\(in|notin|subset|subseteq|supset|supseteq)(?![A-Za-z])",
    ),
    _kind(
        "set_operation",
        "Set operations (∪, ∩, ∖, ∅, complement)",
        r"\\(cup|cap|setminus|emptyset|varnothing)(?![A-Za-z])|\^c(?![A-Za-z])",
    ),
    _kind("set_builder", "Sets written out ({x : …})", r"\\\{"),
    _kind(
        "logic",
        "Logic (∀, ∃, ¬, ∧, ∨, ⇒, ⇔)",
        r"\\(forall|exists|neg|land|lor|implies|iff|Rightarrow|Leftrightarrow)(?![A-Za-z])",
    ),
    # Relations and functions
    _kind(
        "inequality",
        "Inequalities (<, ≤, ≥, ≪)",
        r"<|>|\\(leq?|geq?|ll|gg)(?![A-Za-z])",
    ),
    _kind(
        "relation",
        "Other relations (≠, ≈, ≡, ∼, ⊥)",
        r"\\(neq?|approx|equiv|sim|perp|propto)(?![A-Za-z])",
    ),
    _kind(
        "arrow",
        "Arrows and maps (→, ↦, ↔)",
        r"\\(to|mapsto|rightarrow|leftrightarrow|xrightarrow|longrightarrow)(?![A-Za-z])",
    ),
    _kind(
        "function",
        "Named functions (sin, ln, det, …)",
        r"\\(sin|cos|tan|log|ln|exp|max|min|det|dim|ker|gcd|arg|operatorname)(?![A-Za-z])",
    ),
    _kind(
        "bars",
        "Absolute values, floor and ceiling",
        r"\||\\[lr](floor|ceil|vert)(?![A-Za-z])",
    ),
    _kind("cases", "Cases (piecewise definitions)", r"\\begin\{cases\}"),
    _kind("aligned", "Aligned derivations", r"\\begin\{aligned\}"),
    # Probability and numbers
    _kind(
        "probability",
        "Probability (P(A | B), 𝔼, Var, 𝒩)",
        r"\\mid(?![A-Za-z])|\\mathbb\{E\}|\\operatorname\{(Var|Cov|Bin)\}|\\mathcal\{N\}",
    ),
    _kind(
        "complex",
        "Complex numbers (conjugate, Re, Im)",
        r"\\operatorname\{(Re|Im)\}|\\overline\{z\}",
    ),
    _kind("modular", "Congruences (mod)", r"\\pmod(?![A-Za-z])|\\bmod(?![A-Za-z])"),
)

BY_NAME = {kind.name: kind for kind in KINDS}

# The corpus must show every kind in at least this many formulas, so that a
# rate for the kind rests on more than one or two cases.
MIN_FORMULAS = 5


# An array's column layout, {cc|c}: its bar is a rule, not an absolute value.
_ARRAY_LAYOUT = re.compile(r"(\\begin\{array\})\{[^}]*\}")


def kinds_in(latex: str) -> list[str]:
    """The names of the kinds of notation a formula shows."""
    plain = _ARRAY_LAYOUT.sub(r"\1", latex)
    return [
        kind.name
        for kind in KINDS
        if kind.found_in(latex if kind.name == "augmented" else plain)
    ]
