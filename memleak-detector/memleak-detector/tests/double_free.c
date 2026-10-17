/* Expected: 2 invalid frees reported (1 double, 1 bogus pointer), no crash, 0 leaks */
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    char *p = malloc(16);
    free(p);
    free(p);                      /* double free */
    free((void *)0x1234);         /* invalid free */
    printf("survived\n");
    return 0;
}
