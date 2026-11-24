# Numerical Methods and Error

## Floating-point numbers

Computers store real numbers in floating point, as $\pm m \times 2^{e}$ with a fixed number of binary digits in $m$. In double precision the gap between $1$ and the next representable number is the machine epsilon, $\epsilon_{\text{mach}} = 2^{-52} \approx 2.22 \times 10^{-16}$, and every real number $x$ in range is stored as some $\operatorname{fl}(x)$ with

$$
\frac{|\operatorname{fl}(x) - x|}{|x|} \leq \frac{\epsilon_{\text{mach}}}{2}
$$

Rounding errors are small, but subtraction can magnify them. Computing $\sqrt{x + 1} - \sqrt{x}$ for $x = 10^{12}$ loses most of its digits, while the equal expression $\frac{1}{\sqrt{x + 1} + \sqrt{x}} \approx 5 \times 10^{-7}$ is accurate.

The absolute error of an approximation $\tilde{x}$ to $x$ is $|\tilde{x} - x|$, and its relative error is $\frac{|\tilde{x} - x|}{|x|}$. Approximating $\pi$ by $\frac{22}{7}$ gives an absolute error of about $1.26 \times 10^{-3}$ and a relative error of about $0.04\%$.

## Solving equations

The bisection method finds a root of a continuous $f$ on $[a, b]$ with $f(a) f(b) < 0$. It halves the interval at each step and keeps the half where the sign changes, so after $n$ steps the root is known to within $\frac{b - a}{2^n}$. Reaching a tolerance $\epsilon$ takes

$$
n = \left\lceil \log_2 \frac{b - a}{\epsilon} \right\rceil
$$

steps; for $b - a = 1$ and $\epsilon = 10^{-6}$ that is $\lceil 19.93 \rceil = 20$.

Newton's method follows the tangent line from the current guess to where it crosses zero:

$$
x_{n+1} = x_n - \frac{f(x_n)}{f'(x_n)}
$$

For $f(x) = x^2 - 2$ it becomes $x_{n+1} = \frac{1}{2}\left(x_n + \frac{2}{x_n}\right)$. Starting from $x_0 = 1$ it gives $x_1 = 1.5$, $x_2 = 1.41\overline{6}$ and $x_3 = 1.414215686\ldots$, already within $2.2 \times 10^{-6}$ of $\sqrt{2}$. Near a simple root the error $e_n = x_n - x^{*}$ satisfies

$$
|e_{n+1}| \approx \left| \frac{f''(x^{*})}{2 f'(x^{*})} \right| |e_n|^2
$$

so the number of correct digits roughly doubles at every step. This is quadratic convergence; bisection, which gains one binary digit per step, converges only linearly.

## Approximating derivatives

A derivative can be approximated by a difference quotient with a small step $h$. The forward difference and the central difference are

$$
f'(x) \approx \frac{f(x + h) - f(x)}{h}, \qquad f'(x) \approx \frac{f(x + h) - f(x - h)}{2h}
$$

By Taylor's theorem their errors are $O(h)$ and $O(h^2)$: halving $h$ halves the first error but quarters the second. With the difference operator $\Delta f(x) = f(x + h) - f(x)$, the second difference $\Delta^2 f(x) = f(x + 2h) - 2f(x + h) + f(x)$ approximates $h^2 f''(x)$. The step cannot be made arbitrarily small, because rounding errors of size $\epsilon_{\text{mach}} / h$ grow as $h \to 0$; for the forward difference the best step is near $h \approx \sqrt{\epsilon_{\text{mach}}} \approx 10^{-8}$.

## Numerical integration

The trapezoidal rule with $n$ subintervals of width $h = \frac{b - a}{n}$ and nodes $x_i = a + ih$ is

$$
\int_a^b f(x) \, dx \approx \frac{h}{2} \left[ f(x_0) + 2 \sum_{i=1}^{n-1} f(x_i) + f(x_n) \right]
$$

with an error of at most $\frac{(b - a) h^2}{12} \max_{a \leq x \leq b} |f''(x)|$. Simpson's rule, for even $n$, fits parabolas instead of lines and has an error of order $h^4$. With $n = 4$ on $\int_0^1 x^2 \, dx = \frac{1}{3}$, the trapezoidal rule gives $0.34375$ while Simpson's rule is exact.

## Conditioning and cost

A problem is ill-conditioned when small changes in its data cause large changes in its answer. For a linear system $A\mathbf{x} = \mathbf{b}$ this is measured by the condition number

$$
\kappa(A) = \|A\| \, \|A^{-1}\| \geq 1
$$

and a relative change $\delta$ in $\mathbf{b}$ can change $\mathbf{x}$ by as much as $\kappa(A) \, \delta$. As a rule, about $\log_{10} \kappa(A)$ decimal digits are lost in solving the system.

The cost of an algorithm is described by how it grows with the size $n$ of its input. Merge sort splits a list in two halves, sorts each and merges them, so its running time satisfies

$$
T(n) = \begin{cases} 1 & \text{if } n = 1 \\ 2T\left(\frac{n}{2}\right) + n & \text{if } n > 1 \end{cases}
$$

whose solution is $T(n) = n \log_2 n + n$ for powers of two, that is $T(n) = O(n \log n)$. Since $n \log n \ll n^2$ for large $n$, merge sort beats simple quadratic sorts: for $n = 10^6$ it needs about $2 \times 10^7$ steps instead of $10^{12}$.
