# Differential Equations

## First-order equations

A differential equation relates an unknown function to its derivatives. The simplest model of growth says that a quantity changes at a rate proportional to its size, $y' = ky$, and its solutions are

$$
y(t) = y_0 e^{kt}, \qquad y_0 = y(0)
$$

With $k > 0$ this is exponential growth, with doubling time $\frac{\ln 2}{k}$; with $k < 0$ it is decay, and a radioactive sample with half-life $T$ has $k = -\frac{\ln 2}{T}$. Fixing $y(0) = y_0$ turns the equation into an initial value problem with exactly one solution.

An equation $\frac{dy}{dx} = g(x) h(y)$ is separable: dividing by $h(y)$ and integrating both sides gives $\int \frac{dy}{h(y)} = \int g(x) \, dx$. For $\frac{dy}{dx} = -2xy^2$ with $y(0) = 1$,

$$
\int \frac{dy}{y^2} = \int -2x \, dx \implies -\frac{1}{y} = -x^2 + C \implies y = \frac{1}{x^2 + 1}
$$

A linear first-order equation $y' + p(t) y = q(t)$ is solved with the integrating factor $\mu(t) = e^{\int p(t) \, dt}$, since $(\mu y)' = \mu q$. Logistic growth, $\frac{dP}{dt} = rP\left(1 - \frac{P}{K}\right)$, adds a carrying capacity $K$: the population grows almost exponentially while $P \ll K$ and levels off as $P \to K$.

## Second-order linear equations

A homogeneous linear equation with constant coefficients,

$$
a y'' + b y' + c y = 0, \qquad a \neq 0
$$

has solutions of the form $e^{rt}$ exactly when $r$ solves the characteristic equation $a r^2 + b r + c = 0$. Its discriminant $\Delta = b^2 - 4ac$ decides the shape of the general solution:

$$
y(t) = \begin{cases} c_1 e^{r_1 t} + c_2 e^{r_2 t} & \text{if } \Delta > 0 \\ (c_1 + c_2 t) e^{r t} & \text{if } \Delta = 0 \\ e^{\alpha t} (c_1 \cos\beta t + c_2 \sin\beta t) & \text{if } \Delta < 0 \end{cases}
$$

where $r_1, r_2$ are the two real roots, $r = -\frac{b}{2a}$ is the double root, and $\alpha \pm i\beta$ are the complex roots. For $y'' - 5y' + 6y = 0$ the roots are $2$ and $3$, so $y = c_1 e^{2t} + c_2 e^{3t}$; the conditions $y(0) = 1$ and $y'(0) = 0$ give $c_1 = 3$ and $c_2 = -2$. Two solutions $y_1, y_2$ are independent exactly when their Wronskian is not zero:

$$
W(y_1, y_2) = \begin{vmatrix} y_1 & y_2 \\ y_1' & y_2' \end{vmatrix} = y_1 y_2' - y_2 y_1', \qquad W(e^{2t}, e^{3t}) = e^{5t} \neq 0
$$

## Oscillations

In mechanics, time derivatives are often written with dots: $\dot{x} = \frac{dx}{dt}$ is velocity and $\ddot{x} = \frac{d^2 x}{dt^2}$ is acceleration. A mass $m$ on a spring of stiffness $k$ obeys Newton's law $m\ddot{x} = -kx$, so

$$
\ddot{x} + \omega^2 x = 0, \qquad \omega = \sqrt{\frac{k}{m}}
$$

and it oscillates as $x(t) = A\cos(\omega t - \varphi)$ with period $\frac{2\pi}{\omega}$. Friction adds a term $\gamma \dot{x}$: the motion is underdamped when $\gamma^2 < 4mk$, critically damped when $\gamma^2 = 4mk$ and overdamped when $\gamma^2 > 4mk$, the three cases of the discriminant above.

## Systems of equations

Two populations, or two masses joined by springs, lead to a system $\mathbf{x}' = A\mathbf{x}$. If $\lambda$ is an eigenvalue of $A$ with eigenvector $\mathbf{v}$, then $\mathbf{x}(t) = e^{\lambda t} \mathbf{v}$ is a solution, and when $A$ has independent eigenvectors $\mathbf{v}_1, \mathbf{v}_2$ the general solution is $\mathbf{x}(t) = c_1 e^{\lambda_1 t} \mathbf{v}_1 + c_2 e^{\lambda_2 t} \mathbf{v}_2$. For

$$
\begin{pmatrix} x_1 \\ x_2 \end{pmatrix}' = \begin{pmatrix} 1 & 2 \\ 2 & 1 \end{pmatrix} \begin{pmatrix} x_1 \\ x_2 \end{pmatrix}
$$

the eigenvalues are $3$ and $-1$, with eigenvectors $(1, 1)$ and $(1, -1)$. Because one eigenvalue is positive and one negative, the origin is a saddle: solutions approach it along $(1, -1)$ and leave along $(1, 1)$.

## Euler's method and the Laplace transform

Most equations have no formula for their solution, and are solved step by step. Euler's method for $y' = f(t, y)$ takes steps of size $h = \Delta t$:

$$
y_{n+1} = y_n + h \, f(t_n, y_n), \qquad t_{n+1} = t_n + h
$$

For $y' = y$ with $y(0) = 1$ and $h = 0.1$, ten steps give $y_{10} = 1.1^{10} \approx 2.5937$, against the true $e \approx 2.7183$. The error at a fixed time shrinks in proportion to $h$.

The Laplace transform turns derivatives into multiplication by $s$, so that a linear equation with initial values becomes an algebra problem:

$$
\mathcal{L}\{f\}(s) = \int_0^{\infty} e^{-st} f(t) \, dt, \qquad \mathcal{L}\{f'\}(s) = s \, \mathcal{L}\{f\}(s) - f(0)
$$

For instance $\mathcal{L}\{e^{at}\} = \frac{1}{s - a}$ for $s > a$, and $\mathcal{L}\{\sin \omega t\} = \frac{\omega}{s^2 + \omega^2}$.
