# Vector Spaces, Eigenvalues and Orthogonality

## Subspaces, span and independence

A subspace of $\mathbb{R}^n$ is a set $H \subseteq \mathbb{R}^n$ that contains the zero vector and is closed under addition and scalar multiplication: if $\mathbf{u}, \mathbf{v} \in H$ and $c \in \mathbb{R}$, then $\mathbf{u} + \mathbf{v} \in H$ and $c\mathbf{u} \in H$. The span of vectors $\mathbf{v}_1, \ldots, \mathbf{v}_p$ is the set of all their linear combinations,

$$
\operatorname{Span}\{\mathbf{v}_1, \ldots, \mathbf{v}_p\} = \{ c_1 \mathbf{v}_1 + \cdots + c_p \mathbf{v}_p : c_1, \ldots, c_p \in \mathbb{R} \}
$$

and it is always a subspace, as is the intersection of any number of subspaces, $\bigcap_{i=1}^{k} H_i$. The vectors are linearly independent when the only solution of $c_1 \mathbf{v}_1 + \cdots + c_p \mathbf{v}_p = \mathbf{0}$ is $c_1 = c_2 = \cdots = c_p = 0$. A basis of a subspace $H$ is a linearly independent set that spans $H$; every basis of $H$ has the same number of vectors, the dimension $\dim H$.

Two subspaces come with every $m \times n$ matrix $A$. The null space is $\operatorname{Nul} A = \{ \mathbf{x} \in \mathbb{R}^n : A\mathbf{x} = \mathbf{0} \}$, and the column space $\operatorname{Col} A$ is the span of the columns of $A$, a subspace of $\mathbb{R}^m$. The pivot columns of $A$ form a basis of $\operatorname{Col} A$, and the rank–nullity theorem links the two dimensions:

$$
\operatorname{rank} A + \dim \operatorname{Nul} A = n
$$

## Eigenvalues and eigenvectors

An eigenvector of an $n \times n$ matrix $A$ is a nonzero vector $\mathbf{x}$ with $A\mathbf{x} = \lambda \mathbf{x}$ for some scalar $\lambda$, called an eigenvalue. Rewriting this as $(A - \lambda I)\mathbf{x} = \mathbf{0}$ shows that $\lambda$ is an eigenvalue exactly when $A - \lambda I$ is not invertible, that is, when $\lambda$ solves the characteristic equation

$$
\det(A - \lambda I) = 0
$$

**Example.** For $A = \begin{pmatrix} 2 & 3 \\ 3 & -6 \end{pmatrix}$,

$$
\det(A - \lambda I) = \begin{vmatrix} 2 - \lambda & 3 \\ 3 & -6 - \lambda \end{vmatrix} = \lambda^2 + 4\lambda - 21 = (\lambda - 3)(\lambda + 7)
$$

so the eigenvalues are $\lambda_1 = 3$ and $\lambda_2 = -7$. Solving $(A - 3I)\mathbf{x} = \mathbf{0}$ gives the eigenvector $\mathbf{v}_1 = (3, 1)$, and $(A + 7I)\mathbf{x} = \mathbf{0}$ gives $\mathbf{v}_2 = (-1, 3)$. The sum of the eigenvalues equals the trace, $3 + (-7) = -4 = 2 + (-6)$, and their product equals the determinant, $-21$.

## Diagonalization

A matrix is diagonalizable when $A = PDP^{-1}$ with $D$ diagonal. This happens exactly when $A$ has $n$ linearly independent eigenvectors: they form the columns of $P$, and the matching eigenvalues form the diagonal of $D$. For the example above,

$$
P = \begin{bmatrix} 3 & -1 \\ 1 & 3 \end{bmatrix}, \qquad D = \begin{bmatrix} 3 & 0 \\ 0 & -7 \end{bmatrix}
$$

Powers then cost almost nothing: $A^k = P D^k P^{-1}$, and $D^k$ has entries $3^k$ and $(-7)^k$. A matrix with $n$ distinct eigenvalues is always diagonalizable, and a symmetric matrix can always be diagonalized by an orthogonal $P$, one with $P^{-1} = P^{T}$.

## Inner products and orthogonality

The inner product of $\mathbf{u}, \mathbf{v} \in \mathbb{R}^n$ is $\langle \mathbf{u}, \mathbf{v} \rangle = \mathbf{u}^{T}\mathbf{v} = u_1 v_1 + \cdots + u_n v_n$, and the length of a vector is its norm, $\|\mathbf{v}\| = \sqrt{\langle \mathbf{v}, \mathbf{v} \rangle}$. Two vectors are orthogonal, $\mathbf{u} \perp \mathbf{v}$, when $\langle \mathbf{u}, \mathbf{v} \rangle = 0$; the eigenvectors $(3, 1)$ and $(-1, 3)$ above are orthogonal, as eigenvectors of a symmetric matrix for different eigenvalues always are. The Cauchy–Schwarz inequality $|\langle \mathbf{u}, \mathbf{v} \rangle| \leq \|\mathbf{u}\| \, \|\mathbf{v}\|$ makes the angle $\theta$ between two vectors well defined by $\cos\theta = \frac{\langle \mathbf{u}, \mathbf{v} \rangle}{\|\mathbf{u}\| \, \|\mathbf{v}\|}$.

The orthogonal projection of $\mathbf{y}$ onto the line spanned by a nonzero $\mathbf{u}$ is

$$
\hat{\mathbf{y}} = \frac{\langle \mathbf{y}, \mathbf{u} \rangle}{\langle \mathbf{u}, \mathbf{u} \rangle} \mathbf{u}
$$

and $\mathbf{y} - \hat{\mathbf{y}}$ is orthogonal to $\mathbf{u}$. Among all points of the line, $\hat{\mathbf{y}}$ is the one closest to $\mathbf{y}$.

## Least squares

When $A\mathbf{x} = \mathbf{b}$ has no solution, a least-squares solution $\hat{\mathbf{x}}$ makes $\|\mathbf{b} - A\hat{\mathbf{x}}\|$ as small as possible. Such an $\hat{\mathbf{x}}$ solves the normal equations

$$
A^{T} A \hat{\mathbf{x}} = A^{T} \mathbf{b}
$$

and if the columns of $A$ are linearly independent it is unique, $\hat{\mathbf{x}} = (A^{T}A)^{-1} A^{T} \mathbf{b}$. Fitting a line $y = \beta_0 + \beta_1 x$ to the points $(0, 1)$, $(1, 1)$ and $(2, 4)$ gives

$$
A^{T}A = \begin{pmatrix} 3 & 3 \\ 3 & 5 \end{pmatrix}, \quad A^{T}\mathbf{b} = \begin{pmatrix} 6 \\ 9 \end{pmatrix}, \quad \begin{pmatrix} \hat{\beta}_0 \\ \hat{\beta}_1 \end{pmatrix} = \begin{pmatrix} \frac{1}{2} \\ \frac{3}{2} \end{pmatrix}
$$

so the least-squares line is $y = \frac{1}{2} + \frac{3}{2}x$, and the error $\|\mathbf{b} - A\hat{\boldsymbol{\beta}}\|^2 = \frac{3}{2}$ is the smallest any line can reach.
