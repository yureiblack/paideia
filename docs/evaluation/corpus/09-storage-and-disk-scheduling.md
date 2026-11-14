# Storage Devices and Disk Scheduling

## Hard disk drives

A hard disk drive stores data magnetically on spinning platters. Each surface is divided into concentric tracks, and each track into sectors, traditionally of 512 bytes and now usually 4 kilobytes. A set of read-write heads on a single arm moves across the surfaces. Reading a sector takes three steps: the arm moves to the right track, the seek; the drive waits for the sector to rotate under the head, the rotational latency; and the data passes under the head, the transfer.

Seek and rotation dominate. An average seek takes several milliseconds, and at 7,200 revolutions per minute one rotation takes about 8.3 milliseconds, so the average rotational latency is about 4 milliseconds. Transferring 4 kilobytes, by contrast, takes a few tens of microseconds. The consequence is that a disk reading sequentially can deliver over 100 megabytes per second, while the same disk reading small blocks at random positions may manage only about a hundred operations per second.

## Disk scheduling

Because seeks are so expensive, the operating system or the drive itself reorders pending requests to reduce arm movement. The algorithms are measured by total head movement and by fairness to individual requests.

First-come, first-served serves requests in arrival order. It is fair, but the arm may swing back and forth across the whole disk.

Shortest seek time first, or SSTF, always serves the pending request closest to the current head position. It greatly reduces total seek distance, but it can starve requests at the far edges of the disk when new requests keep arriving near the middle, much as shortest job first can starve long jobs on a CPU.

SCAN, known as the elevator algorithm, moves the arm steadily in one direction, serving every request it passes, until it reaches the end of the disk, then reverses. No request waits for more than two sweeps. Its variant C-SCAN serves requests in one direction only and then returns the arm to the start without serving anything on the way back, which gives more uniform waiting times, because a request just behind the head no longer waits for a full return sweep of the other direction first. LOOK and C-LOOK behave like SCAN and C-SCAN but turn around at the last pending request instead of travelling all the way to the edge.

Modern drives accept many requests at once and reorder them internally, because only the drive knows its exact geometry and the rotational position of the platters. Linux on solid-state drives often uses no scheduler at all, simply passing requests through in order.

## Solid-state drives

A solid-state drive stores data in flash memory and has no moving parts, so a random read costs about the same as a sequential one, typically tens of microseconds. Flash has awkward rules, however. Data is written in pages of a few kilobytes, but a page cannot be overwritten in place: it must first be erased, and erasure works only on whole blocks of hundreds of pages. Each block also tolerates a limited number of erase cycles before it wears out.

The drive hides these rules behind a flash translation layer, firmware that maps logical block addresses to physical flash pages. Each write goes to a fresh, already erased page, and the old page is marked invalid. Garbage collection later copies the valid pages out of a block and erases it. Wear leveling spreads erasures evenly across all blocks so that no block wears out early. The TRIM command lets the operating system tell the drive which logical blocks no longer hold useful data, so garbage collection need not copy them.

## Write amplification

Garbage collection means that one write from the operating system can cause several writes inside the drive, a ratio called write amplification. It grows as the drive fills up, because fewer blocks are entirely invalid and more valid pages must be copied before each erase. Write amplification both slows writes and wears the flash faster, which is why drives reserve extra spare capacity, called over-provisioning, that the user never sees.

## RAID

A redundant array of independent disks combines several drives to gain speed, reliability or both.

RAID 0 stripes data across the drives in fixed-size chunks with no redundancy. Large transfers use all drives in parallel, but the failure of any single drive loses the whole array.

RAID 1 mirrors every block onto two drives. Either drive alone holds all the data, and reads can be served by either, but half the raw capacity is spent on copies.

RAID 5 stripes data across the drives and adds one parity block per stripe, rotating which drive holds the parity so that no single drive becomes a bottleneck. The parity is the exclusive or of the stripe's data blocks, so the contents of any one failed drive can be recomputed from the others. RAID 5 survives one drive failure while giving up only one drive's worth of capacity. Small writes are its weakness: changing one block means reading the old data and old parity and writing new data and new parity, four operations for one logical write. RAID 6 adds a second parity block and survives two failures, which matters for large drives whose rebuild after a failure can take a day or more.

## Measuring storage

Storage performance is described by three numbers that must not be confused. Throughput, or bandwidth, is the amount of data moved per second and matters for large sequential transfers. Operations per second, often written IOPS, counts small independent requests and matters for databases. Latency is the time a single request takes. A device can have excellent throughput and poor latency at the same time, and the right measure depends on the workload.
