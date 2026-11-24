# Sets, Logic and Proof

## Sets

A set is a collection of distinct objects, its elements. We write $x \in A$ when $x$ is an element of $A$ and $x \notin A$ when it is not. A set can be listed, as in $A = \{1, 2, 3, 4\}$, or described by a property in set-builder notation:

$$
B = \{ x \in \mathbb{Z} : x^2 < 10 \} = \{-3, -2, -1, 0, 1, 2, 3\}
$$

The standard number sets are the natural numbers $\mathbb{N} = \{0, 1, 2, \ldots\}$, the integers $\mathbb{Z}$, the rationals $\mathbb{Q} = \{ \frac{p}{q} : p, q \in \mathbb{Z}, \ q \neq 0 \}$, the reals $\mathbb{R}$ and the complex numbers $\mathbb{C}$, and $\mathbb{N} \subset \mathbb{Z} \subset \mathbb{Q} \subset \mathbb{R} \subset \mathbb{C}$. The empty set $\emptyset$ has no elements and is a subset of every set.

$A$ is a subset of $B$, written $A \subseteq B$, when every element of $A$ is in $B$, and two sets are equal when each is a subset of the other. From two sets we build their union, intersection and difference:

$$
A \cup B = \{ x : x \in A \lor x \in B \}, \quad A \cap B = \{ x : x \in A \land x \in B \}, \quad A \setminus B = \{ x \in A : x \notin B \}
$$

Inside a universal set $U$, the complement of $A$ is $A^c = U \setminus A$, and De Morgan's laws say $(A \cup B)^c = A^c \cap B^c$ and $(A \cap B)^c = A^c \cup B^c$. With $A = \{1, 2, 3, 4\}$ and $B$ as above, $A \cap B = \{1, 2, 3\}$ and $A \setminus B = \{4\}$. Unions and intersections of many sets are written $\bigcup_{i=1}^{n} A_i$ and $\bigcap_{i=1}^{n} A_i$, and they may have infinitely many terms:

$$
\bigcup_{n=1}^{\infty} \left[ \frac{1}{n}, 1 \right] = (0, 1], \qquad \bigcap_{n=1}^{\infty} \left( -\frac{1}{n}, \frac{1}{n} \right) = \{0\}
$$

The indicator function of a set $A$ records membership as a number:

$$
\mathbf{1}_A(x) = \begin{cases} 1 & \text{if } x \in A \\ 0 & \text{if } x \notin A \end{cases}
$$

The number of elements of a finite set is its cardinality $|A|$. The Cartesian product $A \times B = \{ (a, b) : a \in A, \ b \in B \}$ has $|A| \cdot |B|$ elements, and the power set $\mathcal{P}(A)$, the set of all subsets of $A$, has $|\mathcal{P}(A)| = 2^{|A|}$ of them. By inclusion and exclusion, $|A \cup B| = |A| + |B| - |A \cap B|$.

## Logic

A proposition is a statement that is either true or false. From propositions $p$ and $q$ we form the negation $\neg p$, the conjunction $p \land q$, the disjunction $p \lor q$, the implication $p \implies q$ and the equivalence $p \iff q$. An implication is false only when $p$ is true and $q$ is false, so it is equivalent to its contrapositive:

$$
(p \implies q) \iff (\neg q \implies \neg p)
$$

but not to its converse $q \implies p$. De Morgan's laws hold for propositions too: $\neg(p \land q) \iff \neg p \lor \neg q$.

Quantifiers make statements about every element or some element of a set. The statement $\forall x \in \mathbb{R}, \ x^2 \geq 0$ is true, and $\exists x \in \mathbb{Z} : 2x = 7$ is false. Negating a quantified statement swaps the quantifier and negates what follows:

$$
\neg \left( \forall x \; P(x) \right) \iff \exists x \; \neg P(x), \qquad \neg \left( \exists x \; P(x) \right) \iff \forall x \; \neg P(x)
$$

The order of quantifiers matters: $\forall n \in \mathbb{N} \; \exists m \in \mathbb{N} : m > n$ is true, but $\exists m \in \mathbb{N} \; \forall n \in \mathbb{N} : m > n$ is false.

## Functions

A function $f : A \to B$ assigns to each $x \in A$ exactly one value $f(x) \in B$. It is injective when $f(x_1) = f(x_2) \implies x_1 = x_2$, surjective when every $y \in B$ equals $f(x)$ for some $x$, and bijective when it is both, in which case it has an inverse $f^{-1} : B \to A$. The composition of $f : A \to B$ and $g : B \to C$ is $(g \circ f)(x) = g(f(x))$. The floor and ceiling functions round to integers: $\lfloor 3.7 \rfloor = 3$, $\lceil 3.2 \rceil = 4$ and $\lfloor -1.5 \rfloor = -2$.

## Proof by induction

To prove that a statement $P(n)$ holds for every $n \geq 1$, it is enough to prove $P(1)$, and to prove $P(k) \implies P(k + 1)$ for every $k \geq 1$. **Theorem.** For every $n \geq 1$,

$$
\sum_{k=1}^{n} k = 1 + 2 + \cdots + n = \frac{n(n + 1)}{2}
$$

**Proof.** For $n = 1$ both sides equal $1$. Assume the formula holds for $n$. Then

$$
\begin{aligned}
\sum_{k=1}^{n+1} k &= \sum_{k=1}^{n} k + (n + 1) \\
&= \frac{n(n + 1)}{2} + (n + 1) \\
&= \frac{(n + 1)(n + 2)}{2}
\end{aligned}
$$

which is the formula for $n + 1$, so it holds for every $n$. In the same way one proves $\sum_{k=1}^{n} k^2 = \frac{n(n + 1)(2n + 1)}{6}$. The binomial coefficients obey Pascal's rule $\binom{n}{k} = \binom{n - 1}{k - 1} + \binom{n - 1}{k}$, and induction on $n$ with this rule proves the binomial theorem

$$
(x + y)^n = \sum_{k=0}^{n} \binom{n}{k} x^{n-k} y^{k}
$$

Setting $x = y = 1$ gives $\sum_{k=0}^{n} \binom{n}{k} = 2^n$, the number of subsets of a set of $n$ elements.

## Divisibility and congruences

For integers $a$ and $b$, $a \mid b$ means that $a$ divides $b$. Two integers are congruent modulo $n$ when $n$ divides their difference:

$$
a \equiv b \pmod{n} \iff n \mid (a - b)
$$

So $38 \equiv 2 \pmod{12}$, which is why $38$ hours after midnight a clock shows $2$. Congruences can be added and multiplied like equations: if $a \equiv b$ and $c \equiv d \pmod{n}$, then $a + c \equiv b + d$ and $ac \equiv bd \pmod{n}$. Hence $10 \equiv 1 \pmod{9}$ gives $10^k \equiv 1 \pmod{9}$ for every $k$, which is why a number is divisible by $9$ exactly when the sum of its digits is. The greatest common divisor satisfies Bezout's identity: for all $a, b$ not both zero, there are integers $x, y$ with $ax + by = \gcd(a, b)$, as in $\gcd(12, 42) = 6 = 4 \cdot 12 - 1 \cdot 42$.
