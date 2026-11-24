# Series and Complex Numbers

## Sequences and series

A sequence $(a_n)$ converges to $L$, written $\lim_{n \to \infty} a_n = L$, when for every $\varepsilon > 0$ there is an $N$ with $|a_n - L| < \varepsilon$ for all $n > N$. For example $\lim_{n \to \infty} \frac{3n + 1}{n + 2} = 3$ and $\lim_{n \to \infty} \sqrt[n]{n} = 1$.

A series adds the terms of a sequence. Its partial sums are $S_N = \sum_{n=1}^{N} a_n$, and the series converges to $S$ when $S_N \to S$:

$$
\sum_{n=1}^{\infty} a_n = \lim_{N \to \infty} \sum_{n=1}^{N} a_n
$$

The geometric series is the model for all others. For $|r| < 1$,

$$
\sum_{n=0}^{\infty} r^n = 1 + r + r^2 + \cdots = \frac{1}{1 - r}
$$

and it diverges when $|r| \geq 1$. So $\sum_{n=1}^{\infty} \left(\frac{1}{2}\right)^n = 1$ and $0.999\ldots = \sum_{n=1}^{\infty} \frac{9}{10^n} = 1$.

## Tests for convergence

If $\sum a_n$ converges then $a_n \to 0$, but the converse fails: the harmonic series $\sum_{n=1}^{\infty} \frac{1}{n}$ diverges, although its terms tend to zero. More generally the $p$-series $\sum_{n=1}^{\infty} \frac{1}{n^p}$ converges exactly when $p > 1$, and Euler showed that $\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}$.

The ratio test compares consecutive terms. Let

$$
\rho = \lim_{n \to \infty} \left| \frac{a_{n+1}}{a_n} \right|
$$

If $\rho < 1$ the series converges absolutely, if $\rho > 1$ it diverges, and if $\rho = 1$ the test says nothing. For $a_n = \frac{2^n}{n!}$ the ratio is $\frac{2}{n + 1} \to 0$, so $\sum \frac{2^n}{n!}$ converges. An alternating series $\sum (-1)^{n+1} b_n$ with $b_n$ decreasing to $0$ converges, as $1 - \frac{1}{2} + \frac{1}{3} - \frac{1}{4} + \cdots = \ln 2$ does.

## Taylor series

A function with derivatives of every order at $a$ has the Taylor series

$$
f(x) = \sum_{n=0}^{\infty} \frac{f^{(n)}(a)}{n!} (x - a)^n = f(a) + f'(a)(x - a) + \frac{f''(a)}{2!}(x - a)^2 + \cdots
$$

where $n! = \prod_{k=1}^{n} k$ and $0! = 1$. Around $a = 0$ the most useful series are

$$
e^x = \sum_{n=0}^{\infty} \frac{x^n}{n!}, \qquad \sin x = \sum_{n=0}^{\infty} \frac{(-1)^n x^{2n+1}}{(2n + 1)!}, \qquad \cos x = \sum_{n=0}^{\infty} \frac{(-1)^n x^{2n}}{(2n)!}
$$

all valid for every real $x$, while $\frac{1}{1 - x} = \sum_{n=0}^{\infty} x^n$ holds only for $|x| < 1$. Cutting a series after the term in $x^n$ leaves an error of order $x^{n+1}$, so $\sin x \approx x - \frac{x^3}{6}$ is very accurate for small $x$.

## Complex numbers

A complex number is $z = a + bi$ with $a, b \in \mathbb{R}$ and $i^2 = -1$. Its real and imaginary parts are $\operatorname{Re} z = a$ and $\operatorname{Im} z = b$, its conjugate is $\overline{z} = a - bi$, and its modulus is

$$
|z| = \sqrt{a^2 + b^2} = \sqrt{z \overline{z}}
$$

Complex numbers are added part by part and multiplied using $i^2 = -1$:

$$
\begin{aligned}
(2 + 3i)(1 - i) &= 2 - 2i + 3i - 3i^2 \\
&= 2 + i + 3 = 5 + i
\end{aligned}
$$

To divide, multiply above and below by the conjugate of the denominator: $\frac{1}{3 + 4i} = \frac{3 - 4i}{25}$. Conjugation respects sums and products, $\overline{z + w} = \overline{z} + \overline{w}$ and $\overline{zw} = \overline{z} \, \overline{w}$, and it recovers the two parts:

$$
\operatorname{Re} z = \frac{z + \overline{z}}{2}, \qquad \operatorname{Im} z = \frac{z - \overline{z}}{2i}
$$

## Polar form and roots of unity

Plotting $z = a + bi$ as the point $(a, b)$, its distance from the origin is $r = |z|$ and its angle with the positive real axis is the argument $\theta = \arg z$. Euler's formula links the exponential function to the circle:

$$
e^{i\theta} = \cos\theta + i \sin\theta
$$

so $z = r e^{i\theta}$, and $e^{i\pi} + 1 = 0$. In polar form, multiplication multiplies the moduli and adds the arguments, which gives De Moivre's formula $(\cos\theta + i\sin\theta)^n = \cos n\theta + i \sin n\theta$. The equation $z^n = 1$ has exactly $n$ solutions, the $n$-th roots of unity,

$$
z_k = e^{2\pi i k / n}, \qquad k = 0, 1, \ldots, n - 1
$$

evenly spaced around the unit circle. They sum to zero, $\sum_{k=0}^{n-1} z_k = 0$ for $n \geq 2$, and their product is $\prod_{k=0}^{n-1} z_k = (-1)^{n+1}$. For $n = 4$ they are $1, i, -1$ and $-i$.
