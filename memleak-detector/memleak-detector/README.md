# Memory Leak Detection and Reporting Tool

A lightweight leak detector for C/C++ programs on Linux. It is a shared library
(`libmemleak.so`) injected with `LD_PRELOAD`, so **the target program is not modified or
recompiled**. It tracks every heap allocation, and at exit reports leaked blocks grouped by
call site (with `file:line`), plus invalid/double frees and peak memory. A Python tool turns
the log into a console, HTML or JSON report.

```
target program ──► libmemleak.so (LD_PRELOAD) ──► memleak.log ──► tools/report.py ──► text / HTML / JSON
```

## Requirements
Linux, `gcc`, `make`, `binutils` (`addr2line`), `python3` (3.8+). Optional: `valgrind` for comparison.
Tested on Ubuntu 24.04 / gcc 13.

## Build
```bash
make            # builds libmemleak.so and all test programs into build/
```

## Run on any program
Compile the target with debug info so line numbers resolve (`-g`, and `-O0 -no-pie` gives the best results):
```bash
gcc -g -O0 -no-pie myprog.c -o myprog
MEMLEAK_LOG=run.log LD_PRELOAD=./libmemleak.so ./myprog
python3 tools/report.py run.log --exe ./myprog --html report.html --json report.json
```
Options for `report.py`: `--top N` (groups to print), `--fail-on-leak` (exit code 1, useful in CI).
Environment variables: `MEMLEAK_LOG` (log path, default `memleak.log`), `MEMLEAK_QUIET=1` (hide the stderr summary).

## Run the tests
```bash
make test       # runs 6 scenarios and prints PASS/FAIL (plus Valgrind numbers if installed)
make demo       # leaks 100 blocks, writes demo.html and demo.json
```

| Test | What it checks | Expected |
|---|---|---|
| `no_leak` | everything freed | 0 leaks |
| `simple_leak` | one `malloc(100)` never freed | 1 leak, 100 B |
| `loop_leak` | 100 x 64 B leaked from one function | 100 leaks, 6400 B, one call site |
| `double_free` | double free + bogus pointer | 2 invalid frees, no crash |
| `realloc_test` | chain of `realloc` calls | 1 leak, 4096 B, no false positives |
| `threads_leak` | 4 threads x 25 leaks | 100 leaks, 12800 B (thread safety) |

## Example output
```
 LEAKS: 100 blocks, 6400 bytes   |   Invalid/double frees: 0
 #1  6400 bytes in 100 block(s)  [sizes: 64]
      at leak_one() tests/loop_leak.c:4
      by main() tests/loop_leak.c:6
```

## How it works (short)
1. `LD_PRELOAD` makes the dynamic linker resolve `malloc`/`free`/... to our versions first; `dlsym(RTLD_NEXT, ...)` finds the real ones.
2. Each allocation is stored in a mutex-protected hash table (key = pointer) with size and `backtrace()` call stack.
3. `free` removes the entry. A pointer that is not in the table is an invalid/double free: it is reported and skipped so the program does not abort.
4. A `destructor` runs at exit, writes every remaining entry to the log. `report.py` resolves addresses with `addr2line`, groups by call site and renders the report.
5. A thread-local `busy` flag prevents infinite recursion (logging/backtrace may allocate), and a small static buffer serves the `calloc` that `dlsym` makes during start-up.

See `docs/design.md` for details.

## Limitations
- Linux/glibc only; does not track `mmap`, `new` via custom allocators, or statically linked programs.
- A block is a "leak" if it is still allocated at exit; memory still reachable through a global pointer is also reported (Valgrind calls this *still reachable*).
- glibc-internal allocations (stdio buffers, TLS) are filtered by function-name prefix.
- Slows the program down (stack capture per allocation).

## Safety
Use only on your own test programs. Do **not** put the library in `/etc/ld.so.preload`; always set `LD_PRELOAD` for a single command.

## Team
| Member | Role |
|---|---|
| _Name 1_ | Core interposer (`src/memleak.c`) |
| _Name 2_ | Stack traces, `tools/report.py` |
| _Name 3_ | Tests, Valgrind comparison |
| _Name 4_ | Documentation, PPT, demo |
