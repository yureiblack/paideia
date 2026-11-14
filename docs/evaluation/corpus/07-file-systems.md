# File Systems

## Files and directories

A file system organises the blocks of a storage device into named files and directories. To a program, a file is a sequence of bytes that can be read and written at any offset; the file system decides which device blocks hold those bytes. A directory is itself a special file that maps human-readable names to the internal identifiers of files. Directories nest to form a tree, and a path such as /home/ana/notes.txt is resolved one component at a time, starting from the root directory.

## Inodes

Unix file systems describe each file with an inode, a fixed-size record stored in a table on the device. The inode holds the file's metadata: its size, owner, permissions, timestamps for last access and last modification, a count of links to it, and the locations of its data blocks. Notably, the inode does not contain the file's name. Names live only in directory entries, each of which pairs a name with an inode number. Running ls -i shows the inode number of each file in a directory.

## Hard links and symbolic links

Because names are separate from inodes, one file can have several names. A hard link is simply another directory entry pointing to the same inode; all hard links to a file are equal, and none of them is the original. The inode's link count records how many directory entries point to it, and the file's data is freed only when the link count drops to zero and no process still has the file open. Hard links cannot point to directories, to avoid cycles in the tree, and cannot cross into another file system, because inode numbers are only meaningful within one.

A symbolic link, or soft link, is a small file whose content is a path to another file. Opening it makes the kernel follow the stored path. A symbolic link can point to a directory or to a file on another file system, but if the target is deleted or moved, the link dangles and opening it fails.

## Allocating blocks to files

The file system must decide which blocks hold each file's data.

Contiguous allocation stores a file in one run of consecutive blocks. Reading it is fast, both sequentially and at any offset, but files cannot easily grow, and the device suffers external fragmentation as files are created and deleted.

Linked allocation stores each block with a pointer to the next one. Files can grow freely and there is no external fragmentation, but reaching the middle of a file means following every pointer from the start, and one damaged pointer loses the rest of the file. The FAT file system, used on many memory cards and USB drives, keeps all these next-block pointers together in a file allocation table instead of inside the data blocks, so the chain can be followed in memory.

Indexed allocation gives each file an index of its block addresses. The classic Unix inode holds twelve direct pointers to data blocks, then a single indirect pointer to a block full of further pointers, a double indirect pointer, and a triple indirect pointer. Small files, which are the majority, are reached with no extra reads at all, while very large files remain possible. Modern file systems such as ext4 replace long lists of pointers with extents: an extent records a starting block and a length, so one entry can describe a run of thousands of contiguous blocks.

## Tracking free space

The file system must also know which blocks are free. A free-space bitmap holds one bit per block, set when the block is in use. A bitmap is compact, and it makes finding a run of consecutive free blocks easy, which helps keep files contiguous. Some file systems instead keep a list of free extents, or a tree of free regions ordered by size.

## Block size

The block size trades space against speed. Large blocks mean fewer blocks per file, fewer pointers, and fewer disk operations for large files, but each file wastes on average half a block at its end, which adds up when most files are small. Most file systems settle on 4 kilobytes, which matches the page size and makes caching file data in memory simple.

## Opening and reading a file

Opening a file walks the path, reading each directory to find the inode number of the next component, checks permissions, and creates an entry in the system-wide open-file table recording the current offset. The process receives a small integer, the file descriptor, which indexes its own per-process table of open files. Subsequent reads and writes use the descriptor and avoid repeating the path lookup. Because many reads hit the same blocks, the kernel keeps recently used blocks in a page cache in memory, and most reads of popular files never reach the device at all.

## The virtual file system

An operating system supports many file systems at once: a local ext4 disk, a FAT memory card, a network share and in-memory systems such as /proc. A virtual file system layer gives them all one interface. Programs call open, read and write, and the virtual file system dispatches each call to the matching function of whichever concrete file system holds the file. This is also why the same tools work unchanged on files of every kind.

## Permissions

Each Unix inode stores an owner, a group, and nine permission bits: read, write and execute for the owner, for members of the group, and for everyone else. For a directory, read permission allows listing its names, write permission allows creating and deleting entries, and execute permission allows passing through it on the way to a file deeper in the tree. Access control lists extend this scheme with per-user entries when nine bits are not enough.
