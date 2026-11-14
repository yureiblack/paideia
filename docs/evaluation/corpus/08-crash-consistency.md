# Crash Consistency and Journaling

## The crash consistency problem

Many file system operations update several structures on the device. Appending one block to a file, for instance, must write the new data block, update the file's inode with the new size and block pointer, and mark the block as used in the free-space bitmap. The device writes these blocks one at a time, and power can fail between any two of them. If only the bitmap update reaches the disk, a block is marked used but belongs to no file, a space leak. If only the inode update reaches the disk, the inode points to a block that still holds garbage, and the bitmap may later hand that same block to another file. The file system must survive such partial updates without losing its structure.

## The file system checker

Early Unix systems accepted inconsistency during normal operation and repaired it after a crash. The file system checker, fsck, runs at boot when the file system was not cleanly unmounted. It scans every inode, every directory and the free-space bitmap, rebuilds the bitmap from the inodes, fixes link counts, and moves files that no directory refers to into a lost+found directory. Fsck works, but it reads the entire device, so on a large disk recovery can take hours, and it can only make the structures consistent; it cannot know what the user's data was meant to be.

## Journaling

Journaling, also called write-ahead logging, borrows an idea from databases. Before changing the main file system structures in place, the file system first writes a description of the changes to a dedicated area of the device called the journal. Only after the description is safely on disk does it apply the changes to their real locations.

A journaled update proceeds in steps. First, the blocks to be changed are written to the journal, preceded by a transaction-begin record. Second, once those writes are on disk, a commit record is written; the transaction counts as committed only when the commit record is durable. Third, the changes are written to their final locations, a step called checkpointing. Finally, the transaction's space in the journal is marked free for reuse.

After a crash, recovery is quick. The file system reads the journal and replays every transaction that has a commit record, writing its blocks to their final locations again; replaying a transaction twice is harmless because it writes the same contents. Transactions without a commit record are simply discarded, as if they had never begun. Recovery reads only the journal, so it takes seconds rather than hours.

## Data journaling and metadata journaling

Writing every block twice, once to the journal and once to its home, doubles the cost of writing file data. Data journaling does exactly this and protects data and metadata alike. Most file systems therefore default to metadata journaling, also called ordered mode, in which only inodes, bitmaps and directories go through the journal. To prevent an inode from pointing at garbage after a crash, ordered mode writes a file's data blocks to their final location before committing the metadata transaction that refers to them. The ext4 file system uses ordered mode by default.

## Log-structured file systems

A log-structured file system takes the journal idea to its conclusion: the log is the only place data lives. All writes, data and metadata alike, are buffered in memory and written sequentially to the end of the log in large segments, never overwriting anything in place. Sequential writes are fast on hard disks, which made this design attractive when memory caches began to absorb most reads. Because the newest version of each inode keeps moving, a small inode map records where the current copy of each inode is. The cost is cleaning: old segments fill with dead blocks that later writes have superseded, and a cleaner must copy the live blocks out of partly empty segments so that whole segments can be reused.

## Copy-on-write file systems

Copy-on-write file systems such as ZFS and Btrfs never overwrite a live block either. To change a block, they write a new copy elsewhere, then write a new copy of the block that points to it, and so on up the tree to the root. The final step atomically switches the single root pointer to the new tree. A crash before that switch leaves the old tree intact and consistent; a crash after it leaves the new tree. Because old trees remain valid until their blocks are reused, these file systems can keep snapshots of the whole file system almost for free.

## Ordering writes and caches

All of these techniques depend on writes reaching the device in a known order. Disks reorder writes inside their own caches for speed, so file systems issue cache flush commands, or mark writes with a force-unit-access flag, to guarantee that the journal blocks are durable before the commit record, and the commit record before checkpointing. Applications face the same problem one level up: a program that saves a document by overwriting it in place can lose both versions in a crash. The safe pattern is to write the new contents to a temporary file, call fsync to force it to the device, and then rename it over the old file, because renaming within a directory is atomic.
