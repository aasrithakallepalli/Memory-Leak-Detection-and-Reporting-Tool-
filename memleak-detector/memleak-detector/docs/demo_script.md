# Live Demo Script (about 5 minutes)

1. `make` - show it builds with no warnings.
2. Show `tests/simple_leak.c` (3 lines). Run:
   `MEMLEAK_LOG=a.log LD_PRELOAD=./libmemleak.so ./build/simple_leak` then
   `python3 tools/report.py a.log --exe build/simple_leak` -> 1 leak, 100 B, correct line.
3. `make test` -> six PASS lines. Explain each scenario in one sentence.
4. `make demo`, open `demo.html` -> grouped leaks by call site, bar chart, cards.
5. Run `double_free` -> program survives, warning printed.
6. (If installed) `valgrind --leak-check=full ./build/loop_leak` -> same numbers.
7. Q&A topics: what `LD_PRELOAD` does, why `busy` exists, why `calloc` needs a bootstrap buffer, what counts as a leak, limitations.
