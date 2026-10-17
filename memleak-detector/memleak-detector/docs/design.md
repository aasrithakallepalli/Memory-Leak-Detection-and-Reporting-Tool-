# Design Document

## 1. Problem
A memory leak is heap memory that is allocated but never released. In long-running programs leaks grow until the process is slow or killed. Developers need a tool that says *how much* leaked and *where it was allocated*.

## 2. Existing tools and the gap
Valgrind (very accurate, 10-50x slowdown), AddressSanitizer/LeakSanitizer (needs recompilation). Our tool: no recompilation, small code base, understandable end-to-end, and a custom grouped HTML/JSON report.

## 3. Architecture
| Component | File | Responsibility |
|---|---|---|
| Interposer | `src/memleak.c` | Wrap allocator functions, track live blocks, emit log at exit |
| Log | `memleak.log` | Tab-separated records: `L` leak, `E` error, `S` summary |
| Reporter | `tools/report.py` | Parse, resolve with `addr2line`, group by call site, render text/HTML/JSON |
| Tests | `tests/*.c`, `run_tests.sh` | Six scenarios with expected numbers |

## 4. Data structure
Hash table of 65,536 buckets, chained, keyed by `(ptr >> 4) * 2654435761`. Insert and delete are O(1) on average. A single mutex protects the table and counters.

## 5. Key design decisions
- **Recursion guard** (`__thread int busy`): `backtrace()`, `fprintf` and `dladdr` can call `malloc`; while `busy` is set, such calls are passed straight to the real allocator and not tracked.
- **Bootstrap buffer**: `dlsym` calls `calloc` before the real functions are known, so `calloc` serves those from a static 16 KB arena. `free`/`realloc` of arena pointers are ignored/copied.
- **realloc** = forget old block, record new block (size and stack of the latest call).
- **Invalid free** is logged with its stack and *not* forwarded to glibc, so the demo does not crash.
- **Internal allocations** whose stack contains `_IO_*`, `_dl_*`, `_nl_*` functions (stdio buffers etc.) are excluded from the leak list.
- **Address resolution** is done offline: log stores `address|module_base|module_path`; the reporter subtracts 1 from return addresses and uses the absolute address for non-PIE executables or `address - base` for PIE/shared objects.

## 6. Complexity and overhead
Per allocation: one `backtrace` (about 1-2 us), one hash insert, one 160-byte node. Memory overhead is proportional to live allocations.

## 7. Testing and validation
`make test` runs six scenarios and compares leak count, leaked bytes and invalid frees to hard-coded expectations. With Valgrind installed, `run_tests.sh` also prints Valgrind's "definitely lost" bytes for comparison.

| Test | Ours | Valgrind (expected "definitely lost") |
|---|---|---|
| simple_leak | 100 B / 1 block | 100 B in 1 block |
| loop_leak | 6400 B / 100 blocks | 6,400 B in 100 blocks |
| realloc_test | 4096 B / 1 block | 4,096 B in 1 block |
| threads_leak | 12800 B / 100 blocks | 12,800 B in 100 blocks |

(Fill the Valgrind column with your own measured output on the demo machine.)

## 8. Future work
Hash-keyed grouping in C, `mmap` tracking, C++ `new[]/delete[]` mismatch detection, periodic snapshots for a memory-vs-time graph, "still reachable" vs "definitely lost" classification via pointer scanning.
