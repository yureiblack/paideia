# Probability and Statistics

## Events and probability

An experiment has a sample space $\Omega$, the set of its possible outcomes, and an event is a subset $A \subseteq \Omega$. A probability $P$ gives each event a number with $P(\Omega) = 1$, $0 \leq P(A) \leq 1$, and $P\left(\bigcup_{i=1}^{\infty} A_i\right) = \sum_{i=1}^{\infty} P(A_i)$ whenever the events $A_i$ are pairwise disjoint. From these axioms follow the complement rule $P(A^c) = 1 - P(A)$ and the addition rule

$$
P(A \cup B) = P(A) + P(B) - P(A \cap B)
$$

When all $|\Omega|$ outcomes are equally likely, $P(A) = \frac{|A|}{|\Omega|}$. Rolling two dice gives $36$ outcomes, and six of them have a sum of $7$, so that event has probability $\frac{6}{36} = \frac{1}{6}$.

## Conditional probability and Bayes' rule

The probability of $A$ given that $B$ has happened is

$$
P(A \mid B) = \frac{P(A \cap B)}{P(B)}, \qquad P(B) > 0
$$

and $A$ and $B$ are independent when $P(A \cap B) = P(A) \, P(B)$, that is, when knowing $B$ does not change the probability of $A$. Events $A_1, \ldots, A_n$ are mutually independent when every selection of them satisfies the product rule, in particular $P(A_1 \cap \cdots \cap A_n) = \prod_{i=1}^{n} P(A_i)$. If $B_1, \ldots, B_k$ split $\Omega$ into disjoint pieces, the law of total probability gives $P(A) = \sum_{i=1}^{k} P(A \mid B_i) \, P(B_i)$, and Bayes' rule reverses a conditional probability:

$$
P(B_j \mid A) = \frac{P(A \mid B_j) \, P(B_j)}{\sum_{i=1}^{k} P(A \mid B_i) \, P(B_i)}
$$

**Example.** A disease affects $1\%$ of a population. A test detects it $95\%$ of the time and gives a false positive $5\%$ of the time. Then the probability of having the disease after a positive test is only

$$
\frac{0.95 \times 0.01}{0.95 \times 0.01 + 0.05 \times 0.99} = \frac{0.0095}{0.059} \approx 0.161
$$

## Random variables, expectation and variance

A discrete random variable $X$ has a probability mass function $p(x) = P(X = x)$, and a continuous one a density $f$ with $P(a \leq X \leq b) = \int_a^b f(x) \, dx$. The expected value is the average of the values weighted by their probabilities:

$$
\mathbb{E}[X] = \sum_{x} x \, p(x) \qquad \text{or} \qquad \mathbb{E}[X] = \int_{-\infty}^{\infty} x f(x) \, dx
$$

Expectation is linear, $\mathbb{E}[aX + bY] = a\,\mathbb{E}[X] + b\,\mathbb{E}[Y]$. The simplest random variable is a Bernoulli trial, which is $1$ with probability $p$:

$$
p(x) = \begin{cases} p & \text{if } x = 1 \\ 1 - p & \text{if } x = 0 \end{cases}
$$

so its mean is $p$. The variance measures spread around the mean $\mu = \mathbb{E}[X]$, and expanding the square shows a shorter way to compute it:

$$
\begin{aligned}
\operatorname{Var}(X) &= \mathbb{E}\left[(X - \mu)^2\right] \\
&= \mathbb{E}[X^2] - 2\mu\,\mathbb{E}[X] + \mu^2 \\
&= \mathbb{E}[X^2] - \mu^2
\end{aligned}
$$

The standard deviation is $\sigma = \sqrt{\operatorname{Var}(X)}$, and a Bernoulli trial has $\sigma^2 = p - p^2 = p(1 - p)$. For a fair die, $\mu = 3.5$ and $\sigma^2 = \frac{91}{6} - 3.5^2 = \frac{35}{12}$. For two variables, $\operatorname{Cov}(X, Y) = \mathbb{E}[XY] - \mathbb{E}[X]\,\mathbb{E}[Y]$ and the correlation is $\rho = \frac{\operatorname{Cov}(X, Y)}{\sigma_X \sigma_Y}$, a number between $-1$ and $1$.

## Common distributions

The number of successes in $n$ independent trials, each succeeding with probability $p$, has the binomial distribution $X \sim \operatorname{Bin}(n, p)$:

$$
P(X = k) = \binom{n}{k} p^k (1 - p)^{n - k}, \qquad k = 0, 1, \ldots, n
$$

with $\mathbb{E}[X] = np$ and $\operatorname{Var}(X) = np(1 - p)$. Here $\binom{n}{k} = \frac{n!}{k!\,(n - k)!}$ counts the ways to choose which $k$ trials succeed; for instance $\binom{5}{2} = 10$. A Poisson variable with rate $\lambda$ has $P(X = k) = \frac{\lambda^k e^{-\lambda}}{k!}$, and both its mean and its variance are $\lambda$.

The normal distribution $X \sim \mathcal{N}(\mu, \sigma^2)$ has the bell-shaped density

$$
f(x) = \frac{1}{\sigma \sqrt{2\pi}} \exp\left( -\frac{(x - \mu)^2}{2\sigma^2} \right)
$$

and $Z = \frac{X - \mu}{\sigma}$ is standard normal. About $68\%$ of its values lie within $\mu \pm \sigma$ and about $95\%$ within $\mu \pm 1.96\sigma$.

## Estimation

From a sample $x_1, \ldots, x_n$, the sample mean and the sample variance are

$$
\bar{x} = \frac{1}{n} \sum_{i=1}^{n} x_i, \qquad s^2 = \frac{1}{n - 1} \sum_{i=1}^{n} (x_i - \bar{x})^2
$$

The divisor $n - 1$ makes $s^2$ an unbiased estimator: $\mathbb{E}[s^2] = \sigma^2$. An estimator of a parameter $\theta$ is written $\hat{\theta}$. For $n$ independent Bernoulli trials $x_1, \ldots, x_n$, the likelihood of $p$ is the product $L(p) = \prod_{i=1}^{n} p^{x_i} (1 - p)^{1 - x_i}$, and it is largest at the proportion of successes, $\hat{p} = \frac{1}{n} \sum_{i=1}^{n} x_i$. By the central limit theorem the mean of $n$ independent observations is approximately $\mathcal{N}\left(\mu, \frac{\sigma^2}{n}\right)$ for large $n$, so an approximate $95\%$ confidence interval for $\mu$ is

$$
\bar{x} \pm 1.96 \frac{s}{\sqrt{n}}
$$

With $n = 100$, $\bar{x} = 52.3$ and $s = 8$, the interval is $52.3 \pm 1.568$, from $50.732$ to $53.868$.
