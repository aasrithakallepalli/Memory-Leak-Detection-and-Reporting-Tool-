/* Expected: 4 threads x 25 leaks x 128 bytes = 100 leaks, 12800 bytes (thread-safe) */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
static void *worker(void *arg) {
    (void)arg;
    for (int i = 0; i < 25; i++) {
        char *leak = malloc(128); leak[0] = 1;
        char *ok = malloc(40); free(ok);
    }
    return NULL;
}
int main(void) {
    pthread_t t[4];
    for (int i = 0; i < 4; i++) pthread_create(&t[i], NULL, worker, NULL);
    for (int i = 0; i < 4; i++) pthread_join(t[i], NULL);
    printf("threads done\n");
    return 0;
}
