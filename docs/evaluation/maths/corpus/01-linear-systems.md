# Linear Systems and Row Reduction

## Systems of linear equations

A linear equation in the variables $x_1, x_2, \ldots, x_n$ has the form $a_1 x_1 + a_2 x_2 + \cdots + a_n x_n = b$, where the coefficients $a_i$ and the constant $b$ are real numbers. A system of linear equations is a finite collection of such equations in the same variables, and a solution is a list $(s_1, s_2, \ldots, s_n)$ of numbers that makes every equation true at once. The set of all solutions is the solution set of the system.

A system has either no solution, exactly one solution, or infinitely many solutions. Two lines in the plane show why: they cross once, they are parallel and never meet, or they are the same line. A system with at least one solution is called consistent; a system with none is inconsistent.

Consider the system

$$
\begin{aligned}
x_1 - 2x_2 + x_3 &= 0 \\
2x_2 - 8x_3 &= 8 \\
5x_1 - 5x_3 &= 10
\end{aligned}
$$

Its coefficients and constants can be written in an augmented matrix, with a bar separating the coefficients from the right-hand side:

$$
\left[\begin{array}{ccc|c} 1 & -2 & 1 & 0 \\ 0 & 2 & -8 & 8 \\ 5 & 0 & -5 & 10 \end{array}\right]
$$

## Row operations

Three operations on the rows of an augmented matrix never change the solution set:

- replacement: add a multiple of one row to another row, written $R_i \to R_i + cR_j$;
- interchange: swap two rows, written $R_i \leftrightarrow R_j$;
- scaling: multiply every entry of a row by a nonzero constant $c$, written $R_i \to cR_i$.

Each operation can be undone by another of the same kind, which is why the solution set stays the same. Two matrices are row equivalent when one can be turned into the other by a sequence of row operations, and row equivalent augmented matrices describe systems with the same solutions.

**Example.** For the system above, subtract five times the first row from the third, then work down the matrix:

$$
\left[\begin{array}{ccc|c} 1 & -2 & 1 & 0 \\ 0 & 2 & -8 & 8 \\ 5 & 0 & -5 & 10 \end{array}\right]
\xrightarrow{R_3 \to R_3 - 5R_1}
\left[\begin{array}{ccc|c} 1 & -2 & 1 & 0 \\ 0 & 2 & -8 & 8 \\ 0 & 10 & -10 & 10 \end{array}\right]
$$

Scaling the second row by $\frac{1}{2}$ and then using $R_3 \to R_3 - 10R_2$ gives

$$
\left[\begin{array}{ccc|c} 1 & -2 & 1 & 0 \\ 0 & 1 & -4 & 4 \\ 0 & 0 & 30 & -30 \end{array}\right]
$$

so $30x_3 = -30$ and $x_3 = -1$. Substituting back, $x_2 = 4 + 4x_3 = 0$ and $x_1 = 2x_2 - x_3 = 1$. The only solution is $(x_1, x_2, x_3) = (1, 0, -1)$.

## Echelon forms

A matrix is in row echelon form when every nonzero row lies above every row of zeros, and the leading entry of each nonzero row lies in a column to the right of the leading entry of the row above it. It is in reduced row echelon form when, in addition, every leading entry is $1$ and is the only nonzero entry in its column. Each matrix is row equivalent to exactly one matrix in reduced row echelon form.

The leading entries mark the pivot positions, and a column that contains one is a pivot column. In the reduced form below, columns $1$, $3$ and $5$ are pivot columns:

$$
\begin{bmatrix} 1 & 6 & 0 & 3 & 0 \\ 0 & 0 & 1 & -8 & 0 \\ 0 & 0 & 0 & 0 & 1 \end{bmatrix}
$$

The variables that belong to pivot columns are basic variables; the others are free variables, and they may take any value.

## Describing the solution set

Suppose the reduced augmented matrix of a system is

$$
\left[\begin{array}{ccc|c} 1 & 0 & -5 & 1 \\ 0 & 1 & 1 & 4 \\ 0 & 0 & 0 & 0 \end{array}\right]
$$

Then $x_1 = 1 + 5x_3$ and $x_2 = 4 - x_3$, while $x_3$ is free. Writing $x_3 = t$, every solution is a point on a line in $\mathbb{R}^3$:

$$
\mathbf{x} = \begin{pmatrix} 1 \\ 4 \\ 0 \end{pmatrix} + t \begin{pmatrix} 5 \\ -1 \\ 1 \end{pmatrix}, \qquad t \in \mathbb{R}
$$

The same solution set can be written with set-builder notation as $\{ (1 + 5t, 4 - t, t) : t \in \mathbb{R} \}$. This is the parametric vector form of the solution.

A system can also turn out to have no solution at all. Row reducing the system $x_1 + x_2 = 2$, $2x_1 + 2x_2 = 7$ gives

$$
\left[\begin{array}{cc|c} 1 & 1 & 2 \\ 2 & 2 & 7 \end{array}\right] \xrightarrow{R_2 \to R_2 - 2R_1} \left[\begin{array}{cc|c} 1 & 1 & 2 \\ 0 & 0 & 3 \end{array}\right]
$$

and the last row says $0 = 3$, which no choice of $x_1$ and $x_2$ can satisfy.

**Theorem.** A linear system is consistent if and only if the rightmost column of its augmented matrix is not a pivot column, that is, if and only if an echelon form has no row of the form $[\, 0 \; 0 \; \cdots \; 0 \mid b \,]$ with $b \neq 0$. A consistent system has a unique solution when it has no free variables, and infinitely many when it has at least one.

## Homogeneous systems and rank

A system is homogeneous when it can be written $A\mathbf{x} = \mathbf{0}$. It always has the trivial solution $\mathbf{x} = \mathbf{0}$, and it has a nontrivial solution exactly when it has a free variable. If $A$ is an $m \times n$ matrix with $m < n$, there are more variables than equations, so at least $n - m$ variables are free and nontrivial solutions must exist.

The rank of $A$ is its number of pivot columns. With $n$ columns, the number of free variables is $n - \operatorname{rank} A$, so $\operatorname{rank} A \leq \min(m, n)$ and the solution set of $A\mathbf{x} = \mathbf{0}$ has $n - \operatorname{rank} A$ parameters.

Elimination on an $n \times n$ system takes about $\frac{2}{3} n^3$ arithmetic operations. For $n = 1000$ that is roughly $6.7 \times 10^8$ operations, a fraction of a second on a laptop, which is why row reduction, and not a formula for each unknown, is how linear systems are solved in practice.
