/* Expected: 100 leaks x 64 bytes = 6400 bytes, all from ONE call site (leak_one) */
#include <stdio.h>
#include <stdlib.h>
static void leak_one(void) { char *p = malloc(64); p[0] = 1; }
int main(void) {
    for (int i = 0; i < 100; i++) leak_one();
    char *ok = malloc(32); free(ok);
    printf("done\n");
    return 0;
}
