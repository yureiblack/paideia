# Deadlock

## What a deadlock is

A set of threads is deadlocked when every thread in the set is waiting for an event that only another thread in the set can cause. The simplest example needs two threads and two locks: thread one holds lock A and waits for lock B, while thread two holds lock B and waits for lock A. Neither can proceed, and neither will ever release what it holds. Unlike a race condition, a deadlock does not corrupt data; it simply stops part of the system for good.

## The four necessary conditions

Edward Coffman and colleagues showed in 1971 that a deadlock can arise only if four conditions hold at the same time:

- Mutual exclusion: at least one resource can be held by only one thread at a time.
- Hold and wait: a thread holds at least one resource while waiting to acquire more.
- No preemption: a resource cannot be taken away from the thread holding it; it is only released voluntarily.
- Circular wait: there is a cycle of threads, each waiting for a resource held by the next one in the cycle.

Because all four are necessary, removing any one of them makes deadlock impossible. Every strategy for handling deadlock works by breaking one of these conditions, by steering around unsafe situations, or by detecting deadlock after it happens.

## Resource-allocation graphs

Deadlock can be pictured with a resource-allocation graph. Threads and resources are the nodes. An edge from a thread to a resource means the thread is requesting it; an edge from a resource to a thread means the resource is assigned to that thread. If every resource has a single instance, a cycle in the graph means deadlock. If resources have several instances, such as three identical printers, a cycle is necessary for deadlock but no longer sufficient, because another instance may free up and break the cycle.

## Prevention

Deadlock prevention designs the system so that one of the four conditions can never hold.

Mutual exclusion usually cannot be removed, since some resources are inherently unshareable. Hold and wait can be removed by requiring a thread to request all its resources at once, before it starts, which wastes resources that sit allocated but unused and can starve threads that need many popular resources. No preemption can be removed for resources whose state is easy to save and restore, such as CPU registers or memory, but not for a lock in the middle of an update.

The most practical prevention rule breaks circular wait: give every lock a number and require that threads always acquire locks in increasing order. A cycle would then need some thread to wait for a lower-numbered lock while holding a higher one, which the rule forbids. Large programs such as operating system kernels document a global lock order for exactly this reason, and tools exist that check the order at run time.

## Avoidance and the banker's algorithm

Deadlock avoidance allows all four conditions in principle but examines every request and grants it only if the system stays in a safe state. A state is safe if there is some order in which every thread can obtain its maximum remaining needs and finish. An unsafe state is not yet a deadlock, but it may lead to one.

Dijkstra's banker's algorithm implements avoidance. Each thread declares in advance the maximum number of each resource it may ever need. When a request arrives, the algorithm pretends to grant it and then searches for a safe sequence: repeatedly find a thread whose remaining need fits within the currently available resources, assume it finishes and returns everything it holds, and continue. If every thread can finish this way, the request is granted; otherwise the requesting thread waits. The algorithm is named after a banker who never lends out cash in a way that would leave him unable to satisfy all his customers' credit limits. Its weakness is practical: few programs know their maximum needs in advance, and the number of threads changes all the time.

## Detection and recovery

The third approach lets deadlocks happen and deals with them afterwards. The system periodically runs a detection algorithm; with single-instance resources this means building a wait-for graph between threads and searching it for a cycle. How often to run detection is a trade-off: running it on every request finds deadlocks immediately but is expensive, while running it every few minutes, or when CPU utilization drops suspiciously, is cheap but lets deadlocked threads sit idle.

Recovery means breaking the cycle. The system can abort all deadlocked processes, which is simple but throws away all their work, or abort them one at a time until the cycle disappears, choosing victims by how much work they would lose. Alternatively it can preempt resources from a victim and roll it back to a saved checkpoint. Databases take this approach routinely: when two transactions deadlock on row locks, the database aborts one of them, rolls back its changes, and reports an error that the application can retry.

## The ostrich approach

Many general-purpose operating systems, including Linux and Windows, do not try to handle deadlocks among application threads at all. They assume deadlocks are rare and leave it to programmers to avoid them, an attitude called the ostrich algorithm after the bird said to bury its head in the sand. The reasoning is economic: prevention and avoidance restrict every program and cost performance all the time, to protect against an event that happens occasionally and can be fixed by restarting the program.

## Starvation and livelock

Two related problems are often confused with deadlock. Starvation means a thread waits indefinitely while others make progress, for example because a lock always happens to be granted to someone else. Livelock means threads are not blocked but keep changing state in response to each other without doing useful work, like two people in a corridor who repeatedly step aside in the same direction. A common livelock arises when two threads each try a lock, back off on failure, and retry in perfect lockstep; adding a random delay before retrying usually breaks the symmetry.
