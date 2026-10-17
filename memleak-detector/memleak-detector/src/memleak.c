/*
 * memleak.c - Memory Leak Detection and Reporting Tool (LD_PRELOAD interposer)
 *
 * Build: make
 * Use:   LD_PRELOAD=./libmemleak.so ./your_program
 * Env:   MEMLEAK_LOG=<file>   machine-readable log (default: memleak.log)
 *        MEMLEAK_QUIET=1      suppress the one-line stderr summary
 *
 * Wraps malloc/calloc/realloc/free/posix_memalign/aligned_alloc, keeps every
 * live allocation in a hash table together with its call stack, and at process
 * exit writes a log that tools/report.py turns into a readable report.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <execinfo.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define MAX_BT   16
#define NBUCKETS 65536          /* power of two */

typedef struct Node {
    void *ptr; size_t size;
    void *bt[MAX_BT]; int depth;
    struct Node *next;
} Node;

static void *(*real_malloc)(size_t);
static void  (*real_free)(void *);
static void *(*real_realloc)(void *, size_t);
static int   (*real_posix_memalign)(void **, size_t, size_t);
static void *(*real_aligned_alloc)(size_t, size_t);

static Node *table[NBUCKETS];
static pthread_mutex_t lk = PTHREAD_MUTEX_INITIALIZER;
static __thread int busy;       /* recursion guard: backtrace()/stdio may call malloc */
static char tmp[16384];         /* bootstrap memory: dlsym() calls calloc during init */
static size_t tmp_off;
static size_t live, peak, total_alloc, n_alloc, n_free, n_invalid;
static volatile int init_done, initializing;
static FILE *logf;

static inline size_t hash(void *p) {
    return (((uintptr_t)p >> 4) * 2654435761u) & (NBUCKETS - 1);
}

static void init(void) {
    if (init_done || initializing) return;
    initializing = 1;
    real_malloc         = dlsym(RTLD_NEXT, "malloc");
    real_free           = dlsym(RTLD_NEXT, "free");
    real_realloc        = dlsym(RTLD_NEXT, "realloc");
    real_posix_memalign = dlsym(RTLD_NEXT, "posix_memalign");
    real_aligned_alloc  = dlsym(RTLD_NEXT, "aligned_alloc");
    initializing = 0;
    init_done = 1;
}

static void record(void *p, size_t n) {
    Node *nd = real_malloc(sizeof *nd);
    if (!nd) return;
    nd->ptr = p; nd->size = n;
    nd->depth = backtrace(nd->bt, MAX_BT);
    size_t h = hash(p);
    pthread_mutex_lock(&lk);
    nd->next = table[h]; table[h] = nd;
    live += n; total_alloc += n; n_alloc++;
    if (live > peak) peak = live;
    pthread_mutex_unlock(&lk);
}

static int forget(void *p) {    /* returns 1 if p was tracked */
    size_t h = hash(p);
    pthread_mutex_lock(&lk);
    for (Node **c = &table[h]; *c; c = &(*c)->next)
        if ((*c)->ptr == p) {
            Node *d = *c;
            *c = d->next; live -= d->size; n_free++;
            pthread_mutex_unlock(&lk);
            real_free(d);
            return 1;
        }
    pthread_mutex_unlock(&lk);
    return 0;
}

static int in_tmp(void *p) { return (char *)p >= tmp && (char *)p < tmp + sizeof tmp; }

static void open_log(void) {
    if (logf) return;
    const char *f = getenv("MEMLEAK_LOG");
    logf = fopen(f ? f : "memleak.log", "w");
}

/* One frame = addr|module_base|module_path, tab separated. report.py resolves them. */
static void log_frames(FILE *f, void **bt, int depth) {
    for (int i = 0; i < depth; i++) {
        Dl_info di;
        if (dladdr(bt[i], &di) && di.dli_fname)
            fprintf(f, "\t%p|%p|%s", bt[i], di.dli_fbase, di.dli_fname);
    }
    fputc('\n', f);
}

void *malloc(size_t n) {
    init();
    if (!real_malloc) return NULL;
    void *p = real_malloc(n);
    if (p && !busy) { busy = 1; record(p, n); busy = 0; }
    return p;
}

void *calloc(size_t c, size_t n) {
    if (!init_done) {           /* dlsym() itself calls calloc during init */
        void *p = tmp + tmp_off;
        tmp_off += (c * n + 15) & ~15UL;
        return p;
    }
    size_t total;
    if (__builtin_mul_overflow(c, n, &total)) return NULL;
    void *p = malloc(total);
    if (p) memset(p, 0, total);
    return p;
}

void *realloc(void *old, size_t n) {
    init();
    if (old && in_tmp(old)) {   /* bootstrap block: copy out, never free */
        void *p = malloc(n);
        if (p) memcpy(p, old, n < 64 ? n : 64);
        return p;
    }
    void *p = real_realloc(old, n);
    if (p && !busy) { busy = 1; if (old) forget(old); record(p, n); busy = 0; }
    return p;
}

int posix_memalign(void **out, size_t al, size_t n) {
    init();
    int r = real_posix_memalign(out, al, n);
    if (r == 0 && !busy) { busy = 1; record(*out, n); busy = 0; }
    return r;
}

void *aligned_alloc(size_t al, size_t n) {
    init();
    void *p = real_aligned_alloc(al, n);
    if (p && !busy) { busy = 1; record(p, n); busy = 0; }
    return p;
}

void free(void *p) {
    init();
    if (!p || in_tmp(p)) return;
    if (busy) { real_free(p); return; }
    busy = 1;
    if (!forget(p)) {
        /* Not tracked: double free or invalid pointer. We skip the real free so
           the program keeps running instead of aborting inside glibc. */
        void *bt[MAX_BT];
        int d = backtrace(bt, MAX_BT);
        __sync_fetch_and_add(&n_invalid, 1);
        fprintf(stderr, "[memleak] WARNING: invalid or double free of %p\n", p);
        open_log();
        if (logf) { fprintf(logf, "E\tinvalid_free\t%p", p); log_frames(logf, bt, d); }
        busy = 0;
        return;
    }
    busy = 0;
    real_free(p);
}

/* glibc allocates its own stdio buffers / TLS blocks and never frees them before exit.
   Those are not user leaks, so skip allocations whose stack passes through them. */
static int is_internal(Node *n) {
    for (int i = 0; i < n->depth; i++) {
        Dl_info di;
        if (dladdr(n->bt[i], &di) && di.dli_sname &&
            (!strncmp(di.dli_sname, "_IO_", 4) || !strncmp(di.dli_sname, "_dl_", 4) ||
             !strncmp(di.dli_sname, "_nl_", 4)))
            return 1;
    }
    return 0;
}

__attribute__((destructor)) static void report(void) {
    busy = 1;
    open_log();
    size_t leaks = 0, bytes = 0;
    for (size_t i = 0; i < NBUCKETS; i++)
        for (Node *n = table[i]; n; n = n->next) {
            if (is_internal(n)) continue;
            leaks++; bytes += n->size;
            if (logf) { fprintf(logf, "L\t%zu\t%p", n->size, n->ptr); log_frames(logf, n->bt, n->depth); }
        }
    if (logf) {
        /* S: leaks, leaked_bytes, peak_bytes, total_bytes, allocs, frees, invalid_frees */
        fprintf(logf, "S\t%zu\t%zu\t%zu\t%zu\t%zu\t%zu\t%zu\n",
                leaks, bytes, peak, total_alloc, n_alloc, n_free, n_invalid);
        fclose(logf);
    }
    if (!getenv("MEMLEAK_QUIET"))
        fprintf(stderr, "[memleak] %zu allocs, %zu freed, %zu live at exit (%zu bytes), "
                "peak %zu bytes, %zu invalid frees. Run tools/report.py for details.\n",
                n_alloc, n_free, leaks, bytes, peak, n_invalid);
}
