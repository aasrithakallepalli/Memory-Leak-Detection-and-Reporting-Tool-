CC      ?= gcc
CFLAGS  := -g -O0 -Wall -Wextra
TESTS   := $(patsubst tests/%.c,build/%,$(wildcard tests/*.c))

all: libmemleak.so tests

libmemleak.so: src/memleak.c
	$(CC) -shared -fPIC -g -O1 -Wall -Wextra $< -o $@ -ldl -lpthread

build/%: tests/%.c | build
	$(CC) $(CFLAGS) -no-pie $< -o $@ -lpthread

build:
	mkdir -p build

tests: $(TESTS)

test: all
	./tests/run_tests.sh

demo: all
	MEMLEAK_LOG=demo.log LD_PRELOAD=./libmemleak.so ./build/loop_leak || true
	python3 tools/report.py demo.log --exe ./build/loop_leak --html demo.html --json demo.json
	@echo "Open demo.html in a browser"

clean:
	rm -rf build libmemleak.so *.log demo.html demo.json

.PHONY: all tests test demo clean
