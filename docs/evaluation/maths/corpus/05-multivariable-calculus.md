# Multivariable Calculus

## Vectors in space

A vector in $\mathbb{R}^3$ is written $\vec{v} = \langle v_1, v_2, v_3 \rangle$ or $\mathbf{v} = v_1 \hat{\mathbf{i}} + v_2 \hat{\mathbf{j}} + v_3 \hat{\mathbf{k}}$, where $\hat{\mathbf{i}}$, $\hat{\mathbf{j}}$ and $\hat{\mathbf{k}}$ are the unit vectors along the axes. Its length is $\|\mathbf{v}\| = \sqrt{v_1^2 + v_2^2 + v_3^2}$, and $\hat{\mathbf{v}} = \mathbf{v} / \|\mathbf{v}\|$ is the unit vector in its direction. The dot product $\mathbf{u} \cdot \mathbf{v} = u_1 v_1 + u_2 v_2 + u_3 v_3 = \|\mathbf{u}\| \|\mathbf{v}\| \cos\theta$ is a number, while the cross product is a vector orthogonal to both:

$$
\mathbf{u} \times \mathbf{v} = \begin{vmatrix} \hat{\mathbf{i}} & \hat{\mathbf{j}} & \hat{\mathbf{k}} \\ u_1 & u_2 & u_3 \\ v_1 & v_2 & v_3 \end{vmatrix} = (u_2 v_3 - u_3 v_2) \hat{\mathbf{i}} - (u_1 v_3 - u_3 v_1) \hat{\mathbf{j}} + (u_1 v_2 - u_2 v_1) \hat{\mathbf{k}}
$$

Its length $\|\mathbf{u} \times \mathbf{v}\| = \|\mathbf{u}\| \|\mathbf{v}\| \sin\theta$ is the area of the parallelogram the two vectors span.

## Partial derivatives

For a function of two variables $f(x, y)$, the partial derivative with respect to $x$ holds $y$ fixed:

$$
\frac{\partial f}{\partial x}(x, y) = \lim_{h \to 0} \frac{f(x + h, y) - f(x, y)}{h}
$$

It is also written $f_x$ or $\partial_x f$. For $f(x, y) = x^2 y + \sin(xy)$, we get $f_x = 2xy + y\cos(xy)$ and $f_y = x^2 + x\cos(xy)$. Second partial derivatives are written $\frac{\partial^2 f}{\partial x^2}$ and $\frac{\partial^2 f}{\partial x \, \partial y}$, and when they are continuous the mixed ones agree, $f_{xy} = f_{yx}$. They form the Hessian matrix

$$
H_f = \begin{bmatrix} \frac{\partial^2 f}{\partial x^2} & \frac{\partial^2 f}{\partial x \, \partial y} \\ \frac{\partial^2 f}{\partial y \, \partial x} & \frac{\partial^2 f}{\partial y^2} \end{bmatrix}
$$

At a critical point, where $f_x = f_y = 0$, the point is a local minimum if $\det H_f > 0$ and $f_{xx} > 0$, a local maximum if $\det H_f > 0$ and $f_{xx} < 0$, and a saddle point if $\det H_f < 0$.

## The gradient

The gradient of $f$ collects its partial derivatives into a vector, $\nabla f = \left\langle \frac{\partial f}{\partial x}, \frac{\partial f}{\partial y}, \frac{\partial f}{\partial z} \right\rangle$. The rate of change of $f$ in the direction of a unit vector $\mathbf{u}$ is the directional derivative

$$
D_{\mathbf{u}} f = \nabla f \cdot \mathbf{u} = \|\nabla f\| \cos\theta
$$

so $f$ increases fastest in the direction of $\nabla f$, at the rate $\|\nabla f\|$, and $\nabla f$ is perpendicular to the level curves of $f$. For $f(x, y) = x^2 + 3y^2$ at the point $(1, 1)$, $\nabla f = \langle 2x, 6y \rangle = \langle 2, 6 \rangle$, and in the direction $\mathbf{u} = \langle \frac{3}{5}, \frac{4}{5} \rangle$ the directional derivative is $\frac{6}{5} + \frac{24}{5} = 6$.

When $x$ and $y$ themselves depend on $t$, the chain rule reads

$$
\frac{dz}{dt} = \frac{\partial z}{\partial x} \frac{dx}{dt} + \frac{\partial z}{\partial y} \frac{dy}{dt}
$$

## Double integrals

The integral of $f$ over a region $D$ in the plane is written $\iint_D f(x, y) \, dA$. Over a rectangle it is an iterated integral, and by Fubini's theorem the order does not matter:

$$
\iint_R xy^2 \, dA = \int_0^2 \int_1^3 xy^2 \, dy \, dx = \int_0^2 \frac{26}{3} x \, dx = \frac{52}{3}
$$

Regions bounded by circles are easier in polar coordinates, $x = r\cos\theta$ and $y = r\sin\theta$, where the area element becomes $dA = r \, dr \, d\theta$. The area of the disc of radius $a$ is then $\int_0^{2\pi} \int_0^{a} r \, dr \, d\theta = \pi a^2$.

In general, a change of variables $x = x(u, v)$, $y = y(u, v)$ scales areas by the absolute value of the Jacobian determinant:

$$
\frac{\partial(x, y)}{\partial(u, v)} = \begin{vmatrix} \frac{\partial x}{\partial u} & \frac{\partial x}{\partial v} \\ \frac{\partial y}{\partial u} & \frac{\partial y}{\partial v} \end{vmatrix}
$$

For polar coordinates it is $\cos\theta \cdot r\cos\theta - (-r\sin\theta)\sin\theta = r$, which is where the factor $r$ comes from.

## Line integrals and Green's theorem

The work done by a force field $\mathbf{F}$ along a curve $C$ is the line integral $\int_C \mathbf{F} \cdot d\mathbf{r}$. If $\mathbf{F} = \nabla \phi$ for some potential $\phi$, the integral depends only on the endpoints, $\int_C \nabla \phi \cdot d\mathbf{r} = \phi(\mathbf{r}(b)) - \phi(\mathbf{r}(a))$, and around any closed curve it is zero. For $\mathbf{F} = \langle P, Q \rangle$ and a closed curve $C$ bounding a region $D$ counterclockwise, Green's theorem turns the line integral into a double integral:

$$
\oint_C P \, dx + Q \, dy = \iint_D \left( \frac{\partial Q}{\partial x} - \frac{\partial P}{\partial y} \right) dA
$$
