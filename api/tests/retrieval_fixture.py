"""A small labelled collection for measuring retrieval quality.

Purpose
-------
28 passages on operating systems, written for this project, and 32 questions
labelled with the passages that answer them. The passages include deliberate
near-misses: disk scheduling beside CPU scheduling; journaling beside
write-ahead logging and log-structured file systems; mutexes beside spinlocks
and monitors; a passage on process creation full of the word "process".

The questions come in three kinds:

- term: names something exactly ("TLB", "Belady's anomaly", "zombie"), where
  keyword search is strong;
- meaning: describes it in other words, where semantic search is strong;
- mixed: a rare term inside an everyday question ("what is a zombie process
  and why does it stick around"), where requiring every word fails.

tests/retrieval_eval.py loads this into an environment and scores each way of
searching against it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    text: str
    answers: tuple[str, ...]  # keys into PASSAGES, any of which answers it
    kind: str  # "term", "meaning" or "mixed"


# key: (heading, text)
PASSAGES: dict[str, tuple[str, str]] = {
    "sched-rr": (
        "CPU Scheduling",
        (
            "When several tasks are ready to run, the dispatcher decides which "
            "one gets the processor next. Round robin keeps the ready tasks in a "
            "queue and gives each a fixed time quantum, typically 10 to 100 "
            "milliseconds. When the quantum expires the timer interrupts the "
            "running task, which is preempted and moved to the back of the "
            "queue. A short quantum keeps interactive programs responsive but "
            "spends more time switching; a very long quantum makes round robin "
            "behave like first come, first served, where one long computation "
            "holds up everything queued behind it."
        ),
    ),
    "sched-sjf": (
        "Shortest Job First",
        (
            "Shortest job first always runs the ready task with the smallest "
            "expected next CPU burst. It provably minimises the average waiting "
            "time, but the length of the next burst is not known in advance, so "
            "it is estimated from previous bursts with an exponential average. "
            "The preemptive form, shortest remaining time first, switches to a "
            "newly arrived task whose burst is shorter than what the current "
            "task has left. Long jobs can starve when short ones keep arriving; "
            "aging, which slowly raises the priority of tasks that have waited a "
            "long time, prevents this."
        ),
    ),
    "sched-mlfq": (
        "Multilevel Feedback Queues",
        (
            "A multilevel feedback queue keeps several ready queues of "
            "decreasing priority, each with a longer time slice than the one "
            "above it. New tasks start at the top. A task that uses its whole "
            "slice is assumed to be compute-bound and is moved down a level; a "
            "task that gives up the processor early, for example to wait for "
            "input, stays where it is. Interactive programs therefore stay near "
            "the top and respond quickly, while batch work sinks to the lower "
            "levels. Periodically every task is moved back to the top so that "
            "nothing waits forever."
        ),
    ),
    "disk-sched": (
        "Disk Scheduling",
        (
            "On a hard disk most of the time of a request is spent moving the "
            "arm to the right track, so the order in which pending requests are "
            "served matters. Shortest seek time first (SSTF) always serves the "
            "request closest to the current head position, which reduces total "
            "movement but can starve requests at the edges. SCAN, also called "
            "the elevator algorithm, sweeps the arm from one end to the other "
            "serving requests on the way, then reverses. C-SCAN returns to the "
            "start without serving on the way back, which gives more uniform "
            "waiting times."
        ),
    ),
    "paging": (
        "Paging",
        (
            "Paging divides physical memory into fixed-size frames and each "
            "program's logical address space into pages of the same size, "
            "commonly 4 KB. A page table records, for every page, which frame "
            "holds it. The hardware splits each virtual address into a page "
            "number and an offset, looks the page number up in the page table, "
            "and combines the frame number with the offset to form the physical "
            "address. Because any page can go in any frame, paging avoids "
            "external fragmentation, though the last page of a program is "
            "usually only partly used."
        ),
    ),
    "tlb": (
        "Translation Lookaside Buffer",
        (
            "Looking up the page table in memory on every access would double "
            "the cost of each load and store. The translation lookaside buffer "
            "(TLB) is a small, fast associative cache of recent page-to-frame "
            "translations inside the memory management unit. On a TLB hit the "
            "frame number is available immediately; on a miss the page table is "
            "walked and the result is inserted, evicting an older entry. Because "
            "programs reuse the same pages, hit rates above 99 percent are "
            "common. Entries can be tagged with an address-space identifier so "
            "the buffer need not be flushed on every context switch."
        ),
    ),
    "replacement": (
        "Page Replacement",
        (
            "When a page must be brought in and no frame is free, the operating "
            "system chooses a victim page to evict. The optimal policy evicts "
            "the page that will not be used for the longest time; it cannot be "
            "implemented but serves as a benchmark. FIFO evicts the oldest page "
            "and suffers from Belady's anomaly: for some reference strings, "
            "giving the program more frames produces more page faults, not "
            "fewer. Least recently used (LRU) evicts the page unused for the "
            "longest time and never shows the anomaly; the clock algorithm "
            "approximates it cheaply with a reference bit per frame."
        ),
    ),
    "thrashing": (
        "Thrashing",
        (
            "If the processes in memory together need more frames than exist, "
            "each keeps faulting on pages that another has just pushed out. The "
            "disk is busy all the time, the processor sits idle waiting for it, "
            "and useful work almost stops. This is thrashing. The working-set "
            "model explains it: each process needs its recently used pages "
            "resident to make progress. The remedy is to run fewer processes at "
            "once, suspending some until the working sets of the rest fit, or to "
            "monitor each process's page-fault frequency and adjust its "
            "allocation."
        ),
    ),
    "demand-paging": (
        "Demand Paging",
        (
            "With demand paging a page is loaded only when it is first touched. "
            "Each page-table entry has a valid bit; touching a page that is not "
            "resident raises a page fault, a trap into the kernel. The kernel "
            "checks that the address is legal, finds a free frame, schedules the "
            "disk read, and puts the faulting process to sleep. When the read "
            "completes the page table is updated and the instruction that "
            "faulted is restarted as if nothing had happened. Programs can "
            "therefore be larger than physical memory and start quickly, since "
            "unused parts are never read from disk."
        ),
    ),
    "deadlock": (
        "Deadlock",
        (
            "A set of processes is deadlocked when each holds a resource and "
            "waits for one held by another, so none can ever proceed. Four "
            "conditions must hold at once: mutual exclusion, hold and wait, no "
            "preemption, and circular wait. Preventing any one of them prevents "
            "deadlock; for example, requiring every process to acquire locks in "
            "the same global order rules out a circular wait. A "
            "resource-allocation graph shows the situation: with a single "
            "instance of each resource, a cycle in the graph means deadlock."
        ),
    ),
    "bankers": (
        "Deadlock Avoidance",
        (
            "Avoidance lets processes request resources freely but grants a "
            "request only if the system stays in a safe state, one in which "
            "there is an order that lets every process obtain its declared "
            "maximum and finish. The Banker's algorithm, due to Dijkstra, tracks "
            "for each process its current allocation and its remaining need. On "
            "each request it pretends to grant it and checks whether a safe "
            "sequence still exists; if not, the requester waits. The price is "
            "that every process must declare its maximum demand in advance."
        ),
    ),
    "priority-inversion": (
        "Priority Inversion",
        (
            "Priority inversion happens when a high-priority task waits for a "
            "lock held by a low-priority task, and a medium-priority task, which "
            "needs no lock, keeps preempting the low-priority one. The urgent "
            "task is then effectively held up by a less important one. The Mars "
            "Pathfinder lander suffered exactly this in 1997 and kept resetting "
            "itself. The fix is priority inheritance: while a task holds a lock "
            "that a higher-priority task wants, it temporarily runs at that "
            "higher priority, finishes its critical section quickly, and "
            "releases the lock."
        ),
    ),
    "inodes": (
        "Inodes and Directories",
        (
            "A Unix-style file system describes each file with an inode, a "
            "record holding its size, owner, permissions, timestamps and the "
            "addresses of its data blocks, but not its name. Names live in "
            "directories, which are special files mapping names to inode "
            "numbers. Several names can refer to the same inode; these are hard "
            "links, and the inode counts them, so the file's blocks are freed "
            "only when the last link is removed. A symbolic link, by contrast, "
            "is a small file containing a path."
        ),
    ),
    "journaling": (
        "Journaling",
        (
            "Updating a file system touches several blocks: the inode, the "
            "free-space bitmap, the directory and the data itself. If the power "
            "fails halfway, the on-disk structures disagree, and without help a "
            "full consistency check (fsck) must scan the whole disk at the next "
            "boot. A journaling file system first writes a description of the "
            "intended changes to a log, commits it, and only then applies the "
            "changes in place. After a crash, recovery replays committed "
            "transactions from the log and discards incomplete ones, which takes "
            "seconds instead of hours."
        ),
    ),
    "allocation": (
        "Block Allocation",
        (
            "Contiguous allocation stores a file in consecutive blocks, which "
            "makes sequential reads fast but leads to external fragmentation and "
            "makes files hard to grow. Linked allocation chains blocks together, "
            "so any free block can be used, but reaching the middle of a file "
            "means following every link before it. Indexed allocation gathers "
            "the block addresses into an index block; Unix inodes use a few "
            "direct pointers followed by single, double and triple indirect "
            "blocks, so small files are cheap and large files remain possible."
        ),
    ),
    "mutex": (
        "Race Conditions and Mutexes",
        (
            "When two threads update a shared variable at the same time, the "
            "result can depend on the exact interleaving of their instructions: "
            "incrementing a counter is a load, an add and a store, and two "
            "threads can both load the old value before either stores. This is a "
            "race condition. The code that touches the shared data is a critical "
            "section, and a mutex ensures only one thread is inside it at a "
            "time: a thread locks the mutex on entry, blocking if another holds "
            "it, and unlocks it on exit."
        ),
    ),
    "semaphores": (
        "Semaphores",
        (
            "A semaphore is an integer with two atomic operations: wait "
            "decrements it and blocks if the result is negative, and signal "
            "increments it and wakes a waiting thread. A semaphore initialised "
            "to one acts as a lock. In the bounded-buffer producer-consumer "
            "problem, one semaphore counts empty slots and another counts full "
            "ones: a producer waits on empty before adding an item and signals "
            "full afterwards, and a consumer does the reverse, while a third "
            "semaphore protects the buffer itself."
        ),
    ),
    "threads": (
        "Threads and Context Switches",
        (
            "A thread is a sequence of execution within a process. Threads of "
            "one process share its address space and open files but each has its "
            "own stack and registers. Switching the processor from one thread to "
            "another means saving the registers of the old one and loading those "
            "of the new one. Between threads of the same process the memory "
            "mappings stay the same, so the switch is cheaper than between "
            "processes, where the address space changes and cached translations "
            "become useless."
        ),
    ),
    "syscalls": (
        "System Calls",
        (
            "User programs run in user mode, where privileged instructions and "
            "direct access to devices are forbidden. To read a file or create a "
            "process, a program makes a system call: it places a call number and "
            "arguments in registers and executes a trap instruction. The "
            "processor switches to kernel mode and jumps to a fixed handler, "
            "which checks the arguments, performs the work, and returns to user "
            "mode with the result. Interrupts from devices enter the kernel the "
            "same way."
        ),
    ),
    "sockets": (
        "Sockets",
        (
            "A socket is an endpoint for communication between programs, usually "
            "over a network. A server creates a socket, binds it to a port, and "
            "listens; a client connects to that address. Stream sockets use TCP "
            "and deliver a reliable, ordered sequence of bytes, while datagram "
            "sockets use UDP and deliver separate messages that may be lost or "
            "reordered. The operating system buffers data in both directions and "
            "wakes a process blocked in a read when data arrives."
        ),
    ),
    "process-creation": (
        "Process Creation",
        (
            "A process is a program in execution, with its own address space, "
            "open files and process identifier. On Unix a new process is created "
            "with fork, which makes a near-identical copy of the calling "
            "process; the copy usually calls exec at once to replace its program "
            "with a new one. Copy-on-write makes fork cheap: parent and child "
            "share pages until one of them writes. The parent can wait for the "
            "child to exit and collect its status; a child that has exited but "
            "not yet been waited for is a zombie, and one whose parent exited "
            "first is adopted by init."
        ),
    ),
    "wal": (
        "Write-Ahead Logging in Databases",
        (
            "A database promises that a committed transaction survives a crash "
            "and that an aborted one leaves no trace. Write-ahead logging "
            "delivers this: before a changed page is written to its place on "
            "disk, a log record describing the change is forced to stable "
            "storage. On restart the database redoes the changes of committed "
            "transactions that never reached their pages and undoes those of "
            "transactions that were still running. Checkpoints bound how much of "
            "the log must be read."
        ),
    ),
    "spinlocks": (
        "Spinlocks",
        (
            "A spinlock is a lock that a waiting thread acquires by looping on "
            "an atomic test-and-set or compare-and-swap instruction until it "
            "succeeds, instead of going to sleep. Spinning wastes processor "
            "time, so spinlocks suit only critical sections that last a few "
            "instructions, on multiprocessors where the holder is running at the "
            "same moment on another core. Kernels use them to protect short "
            "updates to their own data structures, often with interrupts "
            "disabled on the local core."
        ),
    ),
    "monitors": (
        "Monitors and Condition Variables",
        (
            "A monitor bundles shared data with the procedures that operate on "
            "it and guarantees that only one thread executes inside at a time. "
            "Inside, a thread that cannot continue waits on a condition "
            "variable, which releases the monitor's lock while it sleeps; "
            "another thread later signals the condition to wake it. Because the "
            "woken thread may find the condition false again, it should recheck "
            "it in a loop. Java's synchronized methods with wait and notify "
            "follow this model."
        ),
    ),
    "mmap": (
        "Memory-Mapped Files",
        (
            "Memory mapping makes a file appear as a range of a process's "
            "address space. The mmap system call sets up page-table entries for "
            "the range without reading anything; the first access to each page "
            "faults, and the kernel fills the page from the file. Writes to the "
            "memory are written back to the file later. Several processes "
            "mapping the same file share the same physical pages, which is also "
            "how shared libraries are loaded once and used by every program."
        ),
    ),
    "cpu-caches": (
        "CPU Caches",
        (
            "Main memory is far slower than the processor, so each core keeps "
            "recently used data in small caches: a level-one cache of a few tens "
            "of kilobytes, a larger level two, and a level three shared between "
            "cores. Data moves in lines of usually 64 bytes. Programs that walk "
            "memory sequentially use each line fully, while scattered accesses "
            "waste most of it. On a multicore chip a coherence protocol keeps "
            "the cores' copies of a line consistent when one of them writes."
        ),
    ),
    "interrupts": (
        "Interrupt Handling",
        (
            "A device signals that it needs attention by raising an interrupt. "
            "The processor finishes the current instruction, saves enough state "
            "to resume, and jumps through the interrupt vector to the handler "
            "for that device. A handler must be short: it acknowledges the "
            "device, records what happened, and defers longer work to a later, "
            "interruptible stage. Without interrupts the processor would have to "
            "poll every device repeatedly to see whether anything had happened."
        ),
    ),
    "lfs": (
        "Log-Structured File Systems",
        (
            "A log-structured file system writes everything, data and metadata "
            "alike, sequentially to the end of a log on disk, turning many small "
            "random writes into one large sequential one. Since nothing is "
            "overwritten in place, an inode map records where the latest copy of "
            "each inode lives. Old copies become garbage, and a cleaner reclaims "
            "space by copying live blocks out of mostly dead segments. Flash "
            "storage, which cannot overwrite in place either, uses similar ideas."
        ),
    ),
}

QUESTIONS: list[Question] = [
    Question(
        "Find material related to process scheduling",
        ("sched-rr", "sched-sjf", "sched-mlfq"),
        "meaning",
    ),
    Question("TLB", ("tlb",), "term"),
    Question("Belady's anomaly", ("replacement",), "term"),
    Question(
        "why can giving a program more memory cause more page faults",
        ("replacement",),
        "meaning",
    ),
    Question(
        "how a journal repairs the disk after a crash", ("journaling",), "meaning"
    ),
    Question("inode", ("inodes",), "term"),
    Question("Banker's algorithm", ("bankers",), "term"),
    Question(
        "how the OS refuses requests that could lead to a deadlock",
        ("bankers",),
        "meaning",
    ),
    Question("elevator algorithm for the disk arm", ("disk-sched",), "term"),
    Question(
        "an urgent task stuck behind a less important one",
        ("priority-inversion",),
        "meaning",
    ),
    Question("SSTF", ("disk-sched",), "term"),
    Question(
        "the computer slows to a crawl because memory is overcommitted",
        ("thrashing",),
        "meaning",
    ),
    Question(
        "stopping two threads from corrupting a shared counter", ("mutex",), "meaning"
    ),
    Question("producer consumer bounded buffer", ("semaphores",), "term"),
    Question("switching from user mode to kernel mode", ("syscalls",), "meaning"),
    Question(
        "what happens when a program touches memory that is not loaded yet",
        ("demand-paging",),
        "meaning",
    ),
    Question(
        "why switching between threads is cheaper than between processes",
        ("threads",),
        "meaning",
    ),
    Question("fsck", ("journaling",), "term"),
    Question("Dijkstra", ("bankers",), "term"),
    Question("C-SCAN", ("disk-sched",), "term"),
    Question("valid bit", ("demand-paging",), "term"),
    Question("4 KB pages", ("paging",), "term"),
    Question("exponential average of previous bursts", ("sched-sjf",), "term"),
    Question("zombie", ("process-creation",), "term"),
    Question(
        "how a file system cleans up after power loss", ("journaling",), "meaning"
    ),
    Question("waiting for a lock without sleeping", ("spinlocks",), "meaning"),
    Question(
        "what is a zombie process and why does it stick around",
        ("process-creation",),
        "mixed",
    ),
    Question(
        "explain the valid bit in a page table entry", ("demand-paging",), "mixed"
    ),
    Question("who came up with the Banker's algorithm", ("bankers",), "mixed"),
    Question("how does C-SCAN differ from plain SCAN", ("disk-sched",), "mixed"),
    Question(
        "what did the Mars Pathfinder bug teach us", ("priority-inversion",), "mixed"
    ),
    Question("when is fsck needed at boot", ("journaling",), "mixed"),
]
