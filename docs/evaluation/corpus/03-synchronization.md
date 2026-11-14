# Synchronization

## Race conditions

When threads share data, the result of their work can depend on the exact interleaving of their instructions. Consider two threads that each add one to a shared counter. The statement looks atomic, but the machine performs three steps: load the counter into a register, add one, and store it back. If both threads load the old value before either stores, both store the same result and one increment is lost. A bug like this, whose outcome depends on timing, is called a race condition. It may appear once in a million runs, which makes it painful to reproduce.

## The critical section problem

A critical section is a piece of code that accesses shared data and must not be executed by more than one thread at a time. A correct solution to the critical section problem must provide three properties:

- Mutual exclusion: at most one thread is inside the critical section at any time.
- Progress: if no thread is inside and some want to enter, one of them is chosen in finite time.
- Bounded waiting: a thread that has asked to enter will get in after a bounded number of other entries, so no thread waits forever.

Software-only solutions such as Peterson's algorithm exist for two threads, but they rely on memory being updated in program order, which modern processors and compilers do not guarantee. Real systems build on atomic instructions provided by the hardware instead.

## Atomic hardware instructions

Processors offer instructions that read and modify a memory location as one indivisible step. Test-and-set writes true to a location and returns its old value. Compare-and-swap writes a new value only if the location still holds an expected old value, and reports whether it succeeded. With either instruction a thread can claim a free lock in one step, because no other thread can slip in between the check and the update.

## Spinlocks

A spinlock is the simplest lock built on an atomic instruction: a thread that finds the lock taken keeps retrying in a tight loop until the holder releases it. Spinning wastes CPU time, but it avoids the cost of putting the thread to sleep and waking it again. Spinlocks are therefore the right choice only when the lock is held for a very short time and the waiting thread runs on a different core from the holder. Inside operating system kernels, spinlocks protect short sections where sleeping is not allowed, such as code running in an interrupt handler.

## Mutexes

A mutex, short for mutual exclusion lock, protects a critical section with two operations: acquire before entering and release after leaving. Unlike a spinlock, a mutex puts a thread that finds it locked to sleep on a waiting list, and the release operation wakes one of the waiters. A mutex has an owner: only the thread that acquired it may release it. Many implementations spin briefly before sleeping, betting that the holder will release the lock soon.

## Semaphores

A semaphore, introduced by Edsger Dijkstra, is an integer counter with two atomic operations. Wait, historically called P, decrements the counter and blocks the caller if the result would be negative. Signal, historically called V, increments the counter and wakes a blocked thread if any are waiting. A binary semaphore, which takes only the values zero and one, behaves much like a lock. A counting semaphore initialised to n allows up to n threads into a section at once, which suits a pool of identical resources such as n database connections. Unlike a mutex, a semaphore has no owner: any thread may signal it, which also makes semaphores useful for one thread to tell another that an event has happened.

## The bounded-buffer problem

In the producer-consumer problem, also called the bounded-buffer problem, producer threads put items into a buffer of fixed size and consumer threads take them out. Producers must wait when the buffer is full and consumers must wait when it is empty. The classic solution uses three semaphores: a mutex initialised to one protects the buffer itself, a semaphore named empty counts the free slots and starts at the buffer size, and a semaphore named full counts the filled slots and starts at zero. A producer waits on empty, then on the mutex, inserts its item, releases the mutex and signals full. The order of the waits matters: if a producer took the mutex first and then blocked on a full buffer, no consumer could ever enter to make room, and the system would deadlock.

## Readers and writers

In the readers-writers problem, many threads may read shared data at the same time, but a writer needs exclusive access. A reader-writer lock allows any number of concurrent readers or exactly one writer. The policy question is who goes first when both are waiting: favouring readers can starve writers indefinitely, and favouring writers can starve readers.

## Monitors and condition variables

A monitor is a language construct that bundles shared data with the procedures that operate on it and guarantees that only one thread is active inside the monitor at a time. Java's synchronized methods are a monitor in practice. Inside a monitor, a thread waits for a condition using a condition variable: wait releases the monitor's lock and sleeps, and signal wakes one waiting thread. Because another thread may run between the signal and the moment the woken thread reacquires the lock, the condition may no longer hold when the waiter resumes. A waiting thread must therefore recheck its condition in a while loop, never with a single if statement.

## Priority inversion

Locks interact badly with priority scheduling. Suppose a low-priority thread holds a lock that a high-priority thread needs. A medium-priority thread that needs no lock at all can now preempt the low-priority holder and run for as long as it likes, so the high-priority thread waits behind a thread of lower priority. This situation is called priority inversion. It famously caused repeated system resets on the Mars Pathfinder lander in 1997. The usual fix is priority inheritance: while a low-priority thread holds a lock that a higher-priority thread is waiting for, it temporarily runs at the higher priority, so medium-priority work can no longer preempt it.

## Lock-free techniques

Some data structures avoid locks altogether. A lock-free stack, for example, pushes an item by reading the current top, pointing the new item at it, and using compare-and-swap to install the new item as the top only if the top has not changed meanwhile; if it has, the thread simply retries. Lock-free code never blocks, so a thread that is descheduled while holding no lock cannot stall the others, but it is notoriously hard to get right and must guard against subtle problems such as a value changing and changing back between the read and the swap.
