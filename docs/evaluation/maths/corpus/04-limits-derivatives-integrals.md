# Limits, Derivatives and Integrals

## Limits

We write $\lim_{x \to a} f(x) = L$ when $f(x)$ can be made as close to $L$ as we like by taking $x$ close enough to $a$, but not equal to it. The precise definition uses two small positive numbers, $\varepsilon$ and $\delta$:

$$
\lim_{x \to a} f(x) = L \iff \forall \varepsilon > 0 \; \exists \delta > 0 : 0 < |x - a| < \delta \implies |f(x) - L| < \varepsilon
$$

Limits respect sums, products and quotients, so $\lim_{x \to 2} (x^2 + 3x) = 10$ by substitution. Some limits need more care. The function $\frac{\sin x}{x}$ is not defined at $0$, yet $\lim_{x \to 0} \frac{\sin x}{x} = 1$, and $\lim_{x \to \infty} \left(1 + \frac{1}{x}\right)^{x} = e \approx 2.71828$.

A function is continuous at $a$ when $\lim_{x \to a} f(x) = f(a)$. The piecewise function

$$
g(x) = \begin{cases} x^2 & \text{if } x < 1 \\ 2x - 1 & \text{if } x \geq 1 \end{cases}
$$

is continuous everywhere, since both pieces approach $1$ as $x \to 1$, while the function that is $0$ for $x < 0$ and $1$ for $x \geq 0$ jumps at $0$. The absolute value is piecewise too,

$$
|x| = \begin{cases} x & \text{if } x \geq 0 \\ -x & \text{if } x < 0 \end{cases}
$$

and it is continuous at $0$ but has no derivative there.

## The derivative

The derivative of $f$ at $x$ is the limit of the slopes of secant lines. With $\Delta x = h$ and $\Delta y = f(x + h) - f(x)$,

$$
f'(x) = \lim_{\Delta x \to 0} \frac{\Delta y}{\Delta x} = \lim_{h \to 0} \frac{f(x + h) - f(x)}{h}
$$

In Leibniz notation the derivative of $y = f(x)$ is $\frac{dy}{dx}$, and the second derivative is $f''(x) = \frac{d^2 y}{dx^2}$. The $n$-th derivative is written $f^{(n)}(x)$. For $f(x) = x^3$, the definition gives

$$
\begin{aligned}
f'(x) &= \lim_{h \to 0} \frac{(x + h)^3 - x^3}{h} \\
&= \lim_{h \to 0} \frac{3x^2 h + 3x h^2 + h^3}{h} \\
&= \lim_{h \to 0} \left( 3x^2 + 3xh + h^2 \right) = 3x^2
\end{aligned}
$$

and then $f''(x) = 6x$ and $f'''(x) = 6$.

The rules of differentiation follow from the definition:

- power rule: $\frac{d}{dx} x^n = n x^{n-1}$ for every real $n$;
- product rule: $(fg)' = f'g + fg'$;
- quotient rule: $\left(\frac{f}{g}\right)' = \frac{f'g - fg'}{g^2}$ wherever $g \neq 0$;
- chain rule: if $y = f(u)$ and $u = g(x)$, then $\frac{dy}{dx} = \frac{dy}{du} \cdot \frac{du}{dx}$.

Some derivatives are worth knowing by heart: $\frac{d}{dx} e^x = e^x$, $\frac{d}{dx} \ln x = \frac{1}{x}$ for $x > 0$, $\frac{d}{dx} \sin x = \cos x$ and $\frac{d}{dx} \cos x = -\sin x$. By the chain rule, $\frac{d}{dx} \sqrt{1 + x^2} = \frac{x}{\sqrt{1 + x^2}}$.

## Linear approximation and extreme values

Near a point $a$, a differentiable function is close to its tangent line: $f(x) \approx f(a) + f'(a)(x - a)$. For example $\sqrt{4.1} \approx 2 + \frac{1}{4}(0.1) = 2.025$, against the true value $2.02485\ldots$. A small change $\Delta x$ in the input changes the output by about $\Delta y \approx f'(x)\,\Delta x$.

If $f$ has a local maximum or minimum at an interior point $c$ where it is differentiable, then $f'(c) = 0$. If also $f''(c) > 0$ the point is a local minimum, and if $f''(c) < 0$ it is a local maximum. For $f(x) = x^3 - 3x$, $f'(x) = 3x^2 - 3 = 0$ at $x = \pm 1$; since $f''(-1) = -6 < 0$ and $f''(1) = 6 > 0$, there is a local maximum $f(-1) = 2$ and a local minimum $f(1) = -2$.

## The definite integral

Divide $[a, b]$ into $n$ pieces of width $\Delta x = \frac{b - a}{n}$ and pick a point $x_i^{*}$ in the $i$-th piece. The Riemann sum $\sum_{i=1}^{n} f(x_i^{*}) \, \Delta x$ adds the areas of thin rectangles, and the definite integral is its limit:

$$
\int_a^b f(x) \, dx = \lim_{n \to \infty} \sum_{i=1}^{n} f(x_i^{*}) \, \Delta x
$$

**Theorem (Fundamental Theorem of Calculus).** If $f$ is continuous on $[a, b]$ and $F' = f$, then

$$
\int_a^b f(x) \, dx = F(b) - F(a), \qquad \frac{d}{dx} \int_a^x f(t) \, dt = f(x)
$$

So $\int_0^2 (3x^2 + 1) \, dx = \left[ x^3 + x \right]_0^2 = 10$, and $\int_0^{\pi} \sin x \, dx = \left[ -\cos x \right]_0^{\pi} = 2$.

## Techniques and improper integrals

The substitution $u = g(x)$, $du = g'(x)\,dx$ undoes the chain rule: $\int 2x \cos(x^2) \, dx = \sin(x^2) + C$. Integration by parts undoes the product rule, $\int u \, dv = uv - \int v \, du$, so that $\int x e^x \, dx = x e^x - e^x + C$.

An integral over an infinite interval is a limit of ordinary integrals:

$$
\int_1^{\infty} \frac{1}{x^2} \, dx = \lim_{b \to \infty} \left[ -\frac{1}{x} \right]_1^b = \lim_{b \to \infty} \left( 1 - \frac{1}{b} \right) = 1
$$

whereas $\int_1^{\infty} \frac{1}{x} \, dx$ diverges, because $\ln b \to \infty$. The Gaussian integral $\int_{-\infty}^{\infty} e^{-x^2} \, dx = \sqrt{\pi}$ has no elementary antiderivative but a famous value.
