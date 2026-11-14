# I/O, Interrupts and System Calls

## User mode and kernel mode

Processors run in at least two privilege levels. In user mode, a program can execute ordinary instructions and access its own memory, but privileged instructions are forbidden: it cannot talk to devices directly, change page tables, or disable interrupts. In kernel mode everything is allowed. A mode bit in the processor records the current level. If a user program attempts a privileged instruction, the hardware raises an exception and the kernel takes over, usually ending the program. This separation is what lets one buggy program crash without taking the whole machine down.

## System calls

A program that needs a service only the kernel can provide, such as reading a file or creating a process, makes a system call. The program places a system call number and its arguments in agreed registers and executes a special trap instruction, such as syscall on x86-64. The trap switches the processor to kernel mode and jumps to a fixed entry point that the kernel installed at boot, so a program cannot jump into arbitrary kernel code. The kernel looks the number up in its system call table, checks every argument, since a pointer passed from user space might point anywhere, performs the work, places a return value in a register, and returns to user mode.

Most programmers never execute the trap instruction themselves. The C library wraps each system call in an ordinary function, such as read or write, which sets up the registers and handles the error convention: on failure the function returns minus one and stores an error code in errno. Because each crossing into the kernel costs hundreds of nanoseconds or more, libraries buffer small operations; the printf function, for example, collects output in memory and makes one write call for many lines.

## Traps, exceptions and interrupts

The processor stops normal execution for three kinds of reasons. A trap is deliberate, caused by an instruction such as the system call instruction. An exception is caused by the current instruction going wrong, such as a division by zero or a page fault. Both are synchronous: they happen at a specific instruction of the running program. An interrupt, in contrast, is asynchronous: it is raised by a device, such as a network card announcing that a packet has arrived or a timer announcing that a time slice has ended, and it arrives regardless of what the processor is executing.

On an interrupt, the processor saves the current program counter and status, switches to kernel mode, and jumps through the interrupt vector, a table of handler addresses indexed by interrupt number. The handler must be brief, because further interrupts may be delayed while it runs. Kernels therefore split interrupt handling in two: a top half acknowledges the device and records what happened, and a bottom half, run later with interrupts enabled, does the slower processing.

## Polling versus interrupts

There are two ways for the CPU to learn that a device has finished. With polling, also called busy waiting, the CPU repeatedly reads the device's status register until the ready bit appears. Polling wastes the CPU while it waits, but it reacts with no delay and has no per-event overhead. With interrupts, the CPU does other work and the device signals when it is done. Interrupts are better for slow devices, but each one costs a context save and a handler. A very fast network card can produce so many interrupts that the CPU does nothing but handle them, a condition called receive livelock. Modern network drivers therefore switch adaptively: they use interrupts when traffic is light and fall back to polling under heavy load.

## Direct memory access

Copying a large block of data from a device to memory one word at a time would keep the CPU busy throughout. With direct memory access, or DMA, the CPU instead tells a DMA controller the source, the destination in memory, and the number of bytes, and then goes on with other work. The controller moves the data by itself and raises a single interrupt when the transfer is complete. Disks, network cards and graphics cards all use DMA for bulk transfers. Because the controller writes to physical memory directly, the kernel must make sure the pages involved are not evicted or moved during the transfer.

## Device drivers

A device driver is the kernel code that knows how to operate one kind of device: which registers to write, how to start a transfer and what each interrupt means. Drivers present a uniform interface to the rest of the kernel, typically as block devices that read and write fixed-size blocks, such as disks, or as character devices that produce or consume streams of bytes, such as keyboards and serial ports. Drivers make up most of an operating system's source code and are responsible for a large share of its crashes, since they run in kernel mode with full privileges.

## Buffering, caching and spooling

The kernel stands between programs and devices in three further ways. Buffering holds data in memory while it moves between two parties that work at different speeds or in different block sizes, such as a fast program writing to a slow modem. Caching keeps copies of data that may be needed again, such as recently read disk blocks, so that later requests are served from memory. Spooling queues output for a device that can serve only one job at a time, the classic example being a printer: each program's output is written to a spool file, and a daemon sends the files to the printer one after another, so programs do not wait for the printer and their output never interleaves.

## Blocking and non-blocking I/O

A blocking read puts the calling thread to sleep until data is available, which is simple to program but needs one thread per concurrent operation. A non-blocking read returns immediately, with whatever data is ready or with an indication that none is. Servers that handle thousands of connections use event notification interfaces such as epoll on Linux or kqueue on BSD: one thread registers interest in many file descriptors and is told which of them are ready, then services only those. Asynchronous I/O goes one step further: the program submits a request and is notified when the whole operation has completed, as with Linux's io_uring interface.
