# Project Report: Memory Leak Detection and Reporting Tool

**Team:** _names / roll numbers_  **Hackathon date:** 17.10.2026

## 1. Abstract
We built a Linux tool that detects heap memory leaks in unmodified C programs by interposing the allocator with `LD_PRELOAD`. It reports leaked bytes, blocks, and the source line of each allocation, and flags double/invalid frees.

## 2. Problem Statement
Detect and report memory leaks in running programs, with an accurate, readable report, demonstrated on test programs in a controlled environment.

## 3. Approach
See `docs/design.md`. In short: wrap `malloc/calloc/realloc/free/posix_memalign/aligned_alloc`, store live blocks with call stacks in a hash table, dump survivors at exit, and post-process with Python and `addr2line`.

## 4. Technologies
C (gcc), glibc (`dlsym`, `dladdr`, `backtrace`), pthreads, Python 3, GNU binutils `addr2line`, Make, Bash; optional Valgrind.

## 5. Implementation summary
`src/memleak.c` (about 200 lines): allocation hooks, hash table, recursion guard, exit report. `tools/report.py` (about 150 lines): parser, address resolver, grouping, text/HTML/JSON output. Six test programs plus `run_tests.sh`.

## 6. Results
All six scenarios pass (leak count, leaked bytes and invalid-free count match expectations exactly):
no_leak 0/0, simple_leak 1/100 B, loop_leak 100/6400 B, double_free 2 invalid frees with no crash, realloc_test 1/4096 B, threads_leak 100/12800 B.

## 7. Impact
Helps students and developers find leaks quickly without recompiling or learning a heavy tool; the grouped call-site report points directly at the line to fix; can run in CI with `--fail-on-leak`.

## 8. Limitations and Future Work
Linux/glibc only; no `mmap`; reachable-at-exit memory is reported as a leak; see design document section 8.

## 9. Responsible implementation
All experiments run on our own programs in a local environment, library loaded per command only, nothing installed system-wide.

## 10. Team contributions
| Member | Contribution |
|---|---|
| | |
