# Processes and Threads

## What a process is

A program is a passive file on disk: a sequence of instructions and some initial data. A process is a program in execution, an active entity with its own state. When you start a text editor twice, there is one program but two processes, each with its own memory and its own idea of which file is open. The operating system creates processes, schedules them onto the CPU, gives them memory, and cleans up after them when they finish.

Each process has an address space laid out in regions. The text segment holds the machine code and is usually marked read-only. The data segment holds global and static variables. The heap grows upward as the program asks for memory at run time, and the stack grows downward as functions are called, holding local variables and return addresses. The gap between heap and stack lets both grow without colliding in the common case.

## The process control block

The kernel keeps one record per process, called the process control block. It stores everything needed to stop the process and resume it later as if nothing had happened: the saved program counter and registers, the process identifier, the current state, scheduling information such as priority, a pointer to the page tables that describe its memory, the list of open files, and accounting data such as CPU time used so far. On Linux this record is the task_struct, and the kernel links all of them into lists that the scheduler walks.

## Process states

A process moves through a small set of states during its life:

- New: the process is being created and its control block is being filled in.
- Ready: it could run, and is waiting only for a CPU to become free.
- Running: its instructions are executing on a CPU right now.
- Waiting, also called blocked: it cannot continue until some event happens, such as a disk read completing or a key being pressed.
- Terminated: it has finished, but its control block has not yet been removed.

A running process leaves the CPU in one of three ways. It may finish. It may block on I/O, moving to the waiting state; when the I/O completes, an interrupt moves it back to ready, not straight to running. Or the scheduler may preempt it when its time slice expires, returning it to the ready queue. Only the scheduler ever moves a process from ready to running.

## Context switches

Switching the CPU from one process to another is called a context switch. The kernel saves the registers and program counter of the outgoing process into its control block, picks the next process, and loads that process's saved registers and memory mappings. A context switch is pure overhead: no user work happens while it runs. Its direct cost is a few microseconds, but the indirect cost is often larger, because the incoming process finds the CPU caches and the translation lookaside buffer filled with the previous process's data and suffers a burst of misses while they warm up again.

## Creating processes on Unix

Unix creates processes in two steps. The fork system call makes a near-identical copy of the calling process. Both processes continue from the same point, and they tell themselves apart by the return value: fork returns zero in the child and the child's process identifier in the parent. Copying a whole address space would be slow, so modern kernels use copy-on-write: parent and child share the same physical pages, marked read-only, and a private copy of a page is made only when one of them writes to it.

The exec family of calls then replaces the child's program with a new one, loading a different executable into the same process. Splitting creation into fork and exec looks odd at first, but it lets the shell adjust the child between the two calls, for example redirecting its standard output to a file before the new program starts.

A parent collects a finished child's exit status by calling wait. Until the parent does so, the child's entry in the process table stays behind as a zombie process: it has stopped running and holds no memory, but its identifier and exit status remain so the parent can still read them. A program that starts many children and never waits for them slowly fills the process table with zombies. If the parent dies first, the child becomes an orphan and is adopted by init, the first process, which reaps it when it exits.

## Threads

A thread is a single sequence of execution within a process. A process can contain many threads, and they share its address space, its heap, its global variables and its open files. Each thread has its own program counter, its own registers and its own stack, because each may be in the middle of a different function.

Threads are cheaper than processes. Creating one needs only a new stack and a small control block, and switching between two threads of the same process does not change the memory mappings, so the translation lookaside buffer survives. Threads also communicate simply by reading and writing shared variables. That same sharing is their danger: two threads updating one variable at once can corrupt it, which is why threads need synchronization.

Threads are useful for two reasons. On a machine with several cores, the threads of one process can run truly in parallel. And even on one core, a program can keep responding to its user in one thread while another waits for the network.

## User threads and kernel threads

Threads can be implemented by a library in user space or by the kernel. User-level threads are created and switched without any system call, so they are very fast, but the kernel sees only one schedulable entity: if one user thread blocks in a system call, the whole process blocks, and the threads cannot use more than one core. Kernel-level threads are known to the scheduler individually, so one can block while the others keep running on other cores, at the cost of a system call for each thread operation.

The mapping between the two is described as a model. In the one-to-one model, used by Linux and Windows, every user thread is backed by its own kernel thread. In the many-to-one model, all user threads of a process share a single kernel thread. The many-to-many model multiplexes many user threads over a smaller pool of kernel threads, which is how some language runtimes run thousands of lightweight tasks cheaply.

## Signals and inter-process communication

Processes do not share memory by default, so they need explicit ways to talk. A pipe connects the output of one process to the input of another, as the shell does for a command such as ls piped into grep. Shared memory segments let cooperating processes map the same physical pages and exchange data without copying, but then they must synchronize just as threads do. Message queues and sockets pass discrete messages through the kernel.

Signals are a simpler mechanism: a small numbered notification delivered to a process. Pressing Control-C sends SIGINT; the kill command sends SIGTERM by default; SIGKILL cannot be caught or ignored and always ends the process. A process can install a handler that runs when a signal arrives, interrupting whatever it was doing, which is why handlers must be kept short and must avoid functions that are not safe to call at an arbitrary moment.
