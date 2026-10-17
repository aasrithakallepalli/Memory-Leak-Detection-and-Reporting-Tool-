/* Expected: exactly 1 leak of 4096 bytes (final realloc'd block). No false positives. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
    char *a = malloc(16);
    a = realloc(a, 256);
    a = realloc(a, 4096);         /* never freed: only this size must be reported */
    memset(a, 1, 4096);
    char *b = realloc(NULL, 50);  /* behaves like malloc */
    free(b);
    char *c = malloc(10);
    c = realloc(c, 20);
    free(c);
    printf("ok\n");
    return 0;
}
