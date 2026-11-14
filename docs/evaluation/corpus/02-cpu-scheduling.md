# CPU Scheduling

## The scheduling problem

At any moment several processes may be ready to run but only a few cores exist. The short-term scheduler decides which ready process gets a CPU next, and it runs often: whenever a process blocks, finishes, or uses up its time slice. Its decision is carried out by the dispatcher, the small piece of kernel code that performs the context switch and jumps into the chosen process. The time the dispatcher takes is called dispatch latency.

Most processes alternate between bursts of computation and waits for I/O. An interactive editor has many short CPU bursts separated by long waits for the keyboard; a video encoder has long CPU bursts and rarely waits. Good scheduling exploits this pattern: giving the CPU quickly to a process with a short burst lets it issue its next I/O request sooner, keeping the disks and the network busy at the same time as the CPU.

## Measuring a schedule

Several measures compete, and no single policy wins on all of them:

- CPU utilization: the share of time the CPU does useful work.
- Throughput: how many processes finish per unit of time.
- Turnaround time: from the moment a job arrives until it completes.
- Waiting time: the total time a process spends in the ready queue.
- Response time: from a request until the first response appears, which is what an interactive user feels.

Batch systems care most about throughput and turnaround. Interactive systems care about response time, even at some cost in throughput.

## Preemptive and non-preemptive scheduling

A non-preemptive scheduler lets a process keep the CPU until it blocks or finishes. It is simple, but one long computation can hold everyone else up. A preemptive scheduler can take the CPU away, normally when a timer interrupt signals that the current time slice has ended. Every modern general-purpose operating system preempts, because without it a single runaway loop would freeze the machine.

## First-come, first-served

First-come, first-served runs processes in the order they arrive and never preempts them. It is fair in a narrow sense and trivial to implement with a queue, but its average waiting time can be poor. When one long CPU-bound job arrives just ahead of many short ones, every short job waits for the long one to finish. This pile-up of short processes stuck behind a long one is called the convoy effect, and it also leaves the I/O devices idle while the short jobs wait for their turn.

## Shortest job first

Shortest job first always runs the ready process whose next CPU burst is shortest. For a given set of jobs it provably gives the minimum average waiting time, because moving a short job ahead of a long one helps the short job more than it hurts the long one. Its preemptive version, shortest remaining time first, also switches to a newly arrived job whose burst is shorter than what remains of the current one.

The catch is that the scheduler cannot know the length of the next burst in advance. It predicts it from history using an exponential average: the prediction for the next burst is a weighted sum of the length of the last burst and the previous prediction, with a weight alpha between zero and one. With alpha at one half, recent behaviour and long-term history count equally. Shortest job first also risks starvation: a long job may wait indefinitely if short jobs keep arriving.

## Round robin

Round robin gives each ready process a fixed time quantum, typically between 10 and 100 milliseconds, in turn. When the quantum expires the process is preempted and placed at the tail of the ready queue. No process waits more than (n minus 1) quanta before its next turn, which gives good response time for interactive work.

The choice of quantum matters. If the quantum is very large, round robin behaves like first-come, first-served. If it is very small, the CPU spends a large share of its time on context switches instead of useful work. A common rule of thumb is to choose a quantum longer than most CPU bursts, so that most processes block for I/O before their quantum runs out.

## Priority scheduling and aging

Priority scheduling runs the highest-priority ready process. Priorities can be set externally, for example by an administrator, or computed internally from measurable quantities such as memory needs or the ratio of I/O to computation. Shortest job first is a special case in which the priority is the predicted burst length.

A low-priority process can starve when higher-priority work never stops arriving. The standard remedy is aging: the scheduler gradually raises the priority of a process the longer it waits, so that eventually even the lowest-priority process runs. A story told about an old IBM mainframe holds that when it was shut down, a low-priority job submitted years earlier was found still waiting.

## Multilevel feedback queues

A multilevel feedback queue keeps several ready queues of different priority, often with round robin inside each and a longer quantum at lower levels. A new process starts in the top queue. If it uses its whole quantum, it is demoted one level, on the theory that it is CPU-bound; if it gives up the CPU before the quantum ends, it stays where it is. Interactive processes therefore stay near the top and get quick responses, while long computations sink to the bottom and run when nothing more urgent is ready. To stop processes at the bottom starving, and to catch a process whose behaviour changes, the scheduler periodically boosts every process back to the top queue.

## Scheduling on several cores

With several cores the scheduler must also decide where a process runs. A process that has recently run on one core has data in that core's caches, so moving it elsewhere costs it a burst of cache misses. Schedulers therefore prefer to keep a process on the same core, a preference called processor affinity. Keeping one ready queue per core preserves affinity and avoids contention on a shared queue, but the queues can become unbalanced, so a load balancer periodically migrates work from busy cores to idle ones.

## Linux: the completely fair scheduler

Linux's completely fair scheduler, used for normal processes for many years, does not use fixed time slices. Each process accumulates virtual runtime as it runs, scaled by its weight, which comes from its nice value. The scheduler always picks the process with the smallest virtual runtime, keeping processes in a red-black tree ordered by that value. A process that has slept for a long time has a small virtual runtime when it wakes, so interactive processes are picked quickly without any explicit detection of interactivity.
