#!/usr/bin/env bash
# Runs every test program under libmemleak.so and checks leak count / bytes / invalid frees.
# Optionally cross-checks against Valgrind when it is installed.
cd "$(dirname "$0")/.." || exit 1
[ -f libmemleak.so ] || { echo "run 'make' first"; exit 1; }

# name  expected_leaks  expected_bytes  expected_invalid_frees
CASES=(
  "no_leak 0 0 0"
  "simple_leak 1 100 0"
  "loop_leak 100 6400 0"
  "double_free 0 0 2"
  "realloc_test 1 4096 0"
  "threads_leak 100 12800 0"
)
pass=0; fail=0
printf "%-14s %-14s %-14s %-10s %s\n" TEST "LEAKS(exp/got)" "BYTES(exp/got)" "INVALID" RESULT
for c in "${CASES[@]}"; do
  read -r name el eb ei <<< "$c"
  log="build/$name.log"
  MEMLEAK_QUIET=1 MEMLEAK_LOG="$log" LD_PRELOAD=./libmemleak.so "./build/$name" >/dev/null 2>&1
  read -r _ gl gb _ _ _ _ gi < <(grep '^S' "$log")
  if [ "$gl" = "$el" ] && [ "$gb" = "$eb" ] && [ "$gi" = "$ei" ]; then r=PASS; pass=$((pass+1)); else r=FAIL; fail=$((fail+1)); fi
  printf "%-14s %-14s %-14s %-10s %s\n" "$name" "$el/$gl" "$eb/$gb" "$ei/$gi" "$r"
  if command -v valgrind >/dev/null; then
    v=$(valgrind --leak-check=full "./build/$name" 2>&1 >/dev/null | grep -E "definitely lost:|indirectly lost:" | tr -s ' ' | tr '\n' ';')
    echo "     valgrind: ${v:-n/a}"
  fi
done
echo "Passed: $pass  Failed: $fail"
[ "$fail" -eq 0 ]
