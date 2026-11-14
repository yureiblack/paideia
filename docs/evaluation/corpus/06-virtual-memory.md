# Virtual Memory and Page Replacement

## Demand paging

Virtual memory lets a process use more memory than is physically present by keeping only part of its address space in RAM and the rest on disk. With demand paging, a page is loaded only when the process first touches it. A program that never uses its error-handling code never pays to load it, and a process can start running before all of its executable has been read.

Pages not in memory are marked invalid in the page table. When the process touches one, the hardware raises a page fault and the kernel takes over. It checks that the address is legal at all, finds a free frame, schedules a disk read to bring the page in, and blocks the process meanwhile. When the read completes, the kernel updates the page table entry to valid and restarts the faulting instruction, which now succeeds. If the address was not legal, the kernel instead sends the process a segmentation fault signal.

## The cost of a page fault

A memory access takes on the order of 100 nanoseconds, while servicing a page fault from a hard disk takes several milliseconds, tens of thousands of times longer. The effective access time is therefore dominated by the fault rate: even one fault per hundred thousand accesses noticeably slows a program down. Keeping the fault rate tiny is the whole game of virtual memory, and it depends on which pages the kernel chooses to keep in memory.

## Page replacement

When a fault occurs and no frame is free, the kernel must evict a page to make room. If the victim page is dirty, meaning it was modified since it was loaded, it must first be written back to disk; a clean page can simply be dropped because an identical copy already exists on disk. Page replacement algorithms decide which page to evict, and they are compared by counting faults on a sequence of page references called a reference string.

## FIFO and Belady's anomaly

The first-in, first-out policy evicts the page that has been in memory longest. It is simple, but the oldest page may well be one in heavy use, such as a page of a frequently called library. FIFO also exhibits Belady's anomaly: for some reference strings, giving the process more frames produces more page faults, not fewer. The classic example is the string 1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5, which causes nine faults with three frames but ten faults with four. Algorithms that do not suffer from the anomaly are called stack algorithms, because the set of pages in memory with n frames is always a subset of the set with n plus 1 frames.

## The optimal algorithm

The optimal policy, sometimes called OPT or MIN, evicts the page that will not be used for the longest time in the future. It provably produces the fewest possible faults for any reference string. It cannot be implemented in a real system, because the kernel cannot see the future, but it is valuable as a yardstick: in a simulation, a practical algorithm can be judged by how close it comes to the optimal fault count.

## Least recently used

Least recently used, or LRU, approximates the optimal policy by looking backward instead of forward: it evicts the page whose last use lies furthest in the past, on the assumption that the recent past predicts the near future. LRU is a stack algorithm and so never shows Belady's anomaly. Implementing it exactly is expensive, because every single memory access would have to update a timestamp or move the page to the front of a list. No hardware does this for main memory, so real systems approximate LRU.

## The clock algorithm

The clock algorithm, also called second chance, is the standard approximation of LRU. The frames are arranged in a circle with a hand pointing at one of them. Each page has a referenced bit that the hardware sets whenever the page is accessed. When a victim is needed, the hand examines the current page: if its referenced bit is set, the algorithm clears the bit, giving the page a second chance, and advances; if the bit is clear, that page has not been used since the hand last passed and it is evicted. An enhanced version also considers the dirty bit and prefers to evict clean pages, which avoid a write to disk.

## Frame allocation and the working set

Besides choosing a victim, the kernel must decide how many frames each process gets. The working set of a process is the set of pages it has referenced during a recent window of time, for example its last 10 million memory accesses. If every process has its working set in memory, faults are rare. The working-set model keeps a process running only if its working set fits; otherwise the process is suspended until memory frees up. A related approach, page-fault frequency control, watches each process's fault rate directly, giving more frames to processes that fault too often and taking frames from those that fault rarely.

## Thrashing

When the combined working sets of all running processes exceed physical memory, the system starts thrashing. Every process faults constantly, each fault evicts a page that another process needs almost immediately, and the processes spend nearly all their time waiting for the disk. CPU utilization collapses. A naive scheduler may then admit even more processes to raise utilization, which makes thrashing worse. The cure is to reduce the degree of multiprogramming: suspend or swap out some processes entirely so that the remaining ones fit, or add more memory.

## Memory-mapped files

The same machinery maps files into memory. The mmap system call makes a range of a file appear as a range of the process's address space; reading those addresses faults the corresponding file blocks in, and modified pages are written back to the file later. Executables and shared libraries are loaded this way, which is why starting a program reads only the pages it actually executes.

## Swap space

Pages that do not belong to any file, such as the heap and the stack, need a place on disk when they are evicted. That place is swap space, either a dedicated partition or a special file. Anonymous pages are written to swap when evicted and read back on the next fault. A system with no swap space can still page out file-backed pages, which can be re-read from their files, but must keep every anonymous page in memory, and when memory runs out the kernel must instead kill a process to free its pages.
