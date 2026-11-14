# Memory Management

## Why programs need address translation

Several processes must share one physical memory without being able to read or overwrite each other's data. The operating system achieves this by giving each process its own virtual address space and translating every address the process uses into a physical one. The program sees a clean range of addresses starting at zero; the hardware and the kernel decide where in physical memory each part actually lives. Translation happens on every single memory access, so it must be done in hardware, by the memory management unit, and it must be fast.

## Base and limit registers

The simplest translation scheme uses two registers per process. The base register holds the physical address where the process's memory begins, and the limit register holds its size. On every access the hardware checks that the virtual address is smaller than the limit and then adds the base to it. An address beyond the limit raises a fault and the kernel usually ends the process. Relocating a process means copying its memory and changing one register. The drawback is that each process needs one contiguous block of physical memory.

## Fragmentation

Allocating variable-sized contiguous blocks leads to external fragmentation: over time free memory becomes scattered into many small holes between allocated blocks, so a request may fail even though the total free memory would be enough. Allocation policies such as first fit, best fit and worst fit choose which hole to use, but none avoids the problem. Compaction moves allocated blocks together to merge the holes, at the price of copying memory.

The opposite problem is internal fragmentation: space wasted inside an allocated block because the block is larger than what was requested. If memory is handed out only in fixed units of 4 kilobytes, a request for 4,097 bytes receives two units and wastes almost a whole one. Fixed-size allocation removes external fragmentation entirely but always pays some internal fragmentation in the last unit of each allocation.

## Segmentation

Segmentation splits a process's address space into a few variable-sized segments that match its logical structure, typically code, heap and stack, each with its own base and limit. A virtual address names a segment and an offset within it. Segments can be placed independently, can grow separately, and can carry their own protection, so the code segment can be shared read-only between processes running the same program. Because segments are still contiguous and of varying size, segmentation suffers from external fragmentation.

## Paging

Paging divides virtual memory into fixed-size pages and physical memory into frames of the same size, commonly 4 kilobytes. Any page can be placed in any free frame, so a process's memory no longer needs to be contiguous and external fragmentation disappears. A virtual address is split into a page number and an offset within the page. The memory management unit looks the page number up in the process's page table, which gives the frame number, and appends the unchanged offset to form the physical address.

Each page table entry holds the frame number plus several bits: a valid bit saying whether the page is mapped at all, protection bits for read, write and execute, a dirty bit set by the hardware when the page is written, and a referenced bit set when it is accessed. The kernel uses the dirty and referenced bits when it decides which pages to evict.

## The translation lookaside buffer

With a page table stored in memory, every access would need an extra memory access just to find the translation, doubling the cost of every load and store. The translation lookaside buffer, or TLB, is a small, fast cache inside the memory management unit that holds recently used translations. Typical TLBs hold between 64 and a few thousand entries. On a TLB hit the translation takes a fraction of a cycle; on a TLB miss the hardware or the kernel walks the page table and loads the entry into the TLB. Because programs tend to reuse nearby addresses, hit rates above 99 percent are common.

When the kernel switches to a different process, the old translations no longer apply. Older processors simply flushed the whole TLB on every context switch. Newer ones tag each entry with an address-space identifier, so entries from several processes can coexist and a switch does not empty the TLB.

## Multi-level page tables

A flat page table for a 32-bit address space with 4-kilobyte pages needs a million entries, 4 megabytes per process, most of them for addresses the process never uses. A 64-bit address space would need far more. Multi-level page tables solve this by making the table itself a tree: the first part of the page number indexes a top-level directory, whose entries point to second-level tables, and so on. Second-level tables are created only for regions that are actually in use, so a process with a small heap and a small stack needs only a few pages of page tables. The x86-64 architecture uses four levels, and newer processors five. The price is that a TLB miss now costs several memory accesses, one per level, which makes the TLB even more important.

## Protection and sharing

Paging gives protection almost for free: a process can reach only the frames that appear in its own page table, and the protection bits stop it writing to read-only pages or executing data. Sharing is just as simple. Two processes that run the same program can map the same frames of code into their address spaces, and shared libraries are mapped this way into hundreds of processes while existing once in physical memory. The same mechanism underlies the copy-on-write behaviour of fork.

## The kernel's own memory

The kernel is mapped into the upper part of every process's address space, so a system call or an interrupt can enter the kernel without switching page tables. Those pages are marked accessible only in kernel mode. After the Meltdown vulnerability showed in 2018 that a processor could leak kernel memory to user code through speculative execution, kernels adopted page table isolation, which unmaps most of the kernel while user code runs, at a measurable cost in system call speed.
