# Matrices, Inverses and Determinants

## Matrix notation

An $m \times n$ matrix has $m$ rows and $n$ columns, and its entry in row $i$ and column $j$ is written $a_{ij}$. In general,

$$
A = \begin{pmatrix} a_{11} & a_{12} & \cdots & a_{1n} \\ a_{21} & a_{22} & \cdots & a_{2n} \\ \vdots & \vdots & \ddots & \vdots \\ a_{m1} & a_{m2} & \cdots & a_{mn} \end{pmatrix}
$$

The entries $a_{11}, a_{22}, a_{33}, \ldots$ form the main diagonal. A diagonal matrix has zeros everywhere off the main diagonal, and the identity matrix $I_n$ is the $n \times n$ diagonal matrix with every diagonal entry equal to $1$. The trace of a square matrix is the sum of its diagonal entries, $\operatorname{tr} A = \sum_{i=1}^{n} a_{ii}$.

## Products and transposes

If $A$ is $m \times n$ and $B$ is $n \times p$, the product $AB$ is the $m \times p$ matrix whose entries are

$$
(AB)_{ij} = \sum_{k=1}^{n} a_{ik} b_{kj} = a_{i1} b_{1j} + a_{i2} b_{2j} + \cdots + a_{in} b_{nj}
$$

so each entry is a row of $A$ times a column of $B$. For example,

$$
\begin{pmatrix} 2 & 3 \\ 1 & -5 \end{pmatrix} \begin{pmatrix} 4 & 3 & 6 \\ 1 & -2 & 3 \end{pmatrix} = \begin{pmatrix} 11 & 0 & 21 \\ -1 & 13 & -9 \end{pmatrix}
$$

Matrix multiplication is associative, $(AB)C = A(BC)$, and distributes over addition, but it is not commutative: in general $AB \neq BA$, and $AB = 0$ does not force $A = 0$ or $B = 0$.

The transpose $A^{T}$ of an $m \times n$ matrix is the $n \times m$ matrix with $(A^{T})_{ij} = a_{ji}$; its rows are the columns of $A$. Transposes reverse the order of a product, $(AB)^{T} = B^{T} A^{T}$, and a matrix with $A^{T} = A$ is called symmetric.

## The inverse of a matrix

An $n \times n$ matrix $A$ is invertible when there is a matrix $A^{-1}$ with $A A^{-1} = A^{-1} A = I_n$. For a $2 \times 2$ matrix there is a formula:

$$
\begin{pmatrix} a & b \\ c & d \end{pmatrix}^{-1} = \frac{1}{ad - bc} \begin{pmatrix} d & -b \\ -c & a \end{pmatrix}, \qquad ad - bc \neq 0
$$

For larger matrices, row reduce the augmented matrix $[\, A \mid I \,]$. If $A$ is row equivalent to $I$, the same row operations turn $I$ into $A^{-1}$, so $[\, A \mid I \,]$ becomes $[\, I \mid A^{-1} \,]$; otherwise $A$ has no inverse. For a $2 \times 2$ matrix the steps are $R_2 \to R_2 - 3R_1$ and then $R_1 \to R_1 - 2R_2$:

$$
\left[\begin{array}{cc|cc} 1 & 2 & 1 & 0 \\ 3 & 7 & 0 & 1 \end{array}\right] \to \left[\begin{array}{cc|cc} 1 & 2 & 1 & 0 \\ 0 & 1 & -3 & 1 \end{array}\right] \to \left[\begin{array}{cc|cc} 1 & 0 & 7 & -2 \\ 0 & 1 & -3 & 1 \end{array}\right]
$$

When $A$ is invertible, the system $A\mathbf{x} = \mathbf{b}$ has the unique solution $\mathbf{x} = A^{-1}\mathbf{b}$ for every $\mathbf{b}$ in $\mathbb{R}^n$. Products and transposes of invertible matrices are invertible:

$$
(AB)^{-1} = B^{-1} A^{-1}, \qquad (A^{T})^{-1} = (A^{-1})^{T}
$$

**Example.** With $A = \begin{pmatrix} 3 & 4 \\ 5 & 6 \end{pmatrix}$ we have $\begin{vmatrix} 3 & 4 \\ 5 & 6 \end{vmatrix} = 18 - 20 = -2$, so

$$
A^{-1} = -\frac{1}{2} \begin{pmatrix} 6 & -4 \\ -5 & 3 \end{pmatrix} = \begin{pmatrix} -3 & 2 \\ \frac{5}{2} & -\frac{3}{2} \end{pmatrix}
$$

## Determinants

The determinant of a square matrix is a single number that says whether the matrix is invertible. It is written $\det A$, or with vertical bars around the entries. For $2 \times 2$ and $3 \times 3$ matrices,

$$
\begin{vmatrix} a & b \\ c & d \end{vmatrix} = ad - bc, \qquad \begin{vmatrix} 1 & 5 & 0 \\ 2 & 4 & -1 \\ 0 & -2 & 0 \end{vmatrix} = -2
$$

In general, let $A_{ij}$ be the matrix left when row $i$ and column $j$ are deleted. The $(i, j)$ cofactor is $C_{ij} = (-1)^{i+j} \det A_{ij}$, and the determinant can be expanded along any row $i$:

$$
\det A = \sum_{j=1}^{n} a_{ij} C_{ij} = \sum_{j=1}^{n} (-1)^{i+j} a_{ij} \det A_{ij}
$$

The signs $(-1)^{i+j}$ form a checkerboard, starting with $+$ in the top left corner. A row or column with many zeros makes the expansion short: for the $3 \times 3$ matrix above, expanding along the third row leaves the single term $(-1)^{3+2}(-2) \det \begin{pmatrix} 1 & 0 \\ 2 & -1 \end{pmatrix} = 2 \cdot (-1) = -2$.

## Properties of the determinant

For $n \times n$ matrices $A$ and $B$:

- $\det A \neq 0$ if and only if $A$ is invertible;
- $\det(AB) = \det A \cdot \det B$ and $\det(A^{T}) = \det A$;
- if $A$ is triangular, $\det A = a_{11} a_{22} \cdots a_{nn} = \prod_{i=1}^{n} a_{ii}$;
- $\det(A^{-1}) = \frac{1}{\det A}$ and $\det(cA) = c^{n} \det A$.

A row replacement leaves the determinant unchanged, a row interchange changes its sign, and scaling a row by $k$ scales the determinant by $k$. So if row reduction brings $A$ to an echelon form $U$ with $r$ interchanges and no scaling, then $\det A = (-1)^{r} u_{11} u_{22} \cdots u_{nn}$. This takes about $\frac{2}{3} n^3$ operations, whereas cofactor expansion of an $n \times n$ matrix needs more than $n!$ multiplications, already $3\,628\,800$ for $n = 10$.

Geometrically, $|\det A|$ is the area of the parallelogram, or the volume of the parallelepiped, spanned by the columns of $A$, and a linear map $T(\mathbf{x}) = A\mathbf{x}$ multiplies every area or volume by $|\det A|$.
