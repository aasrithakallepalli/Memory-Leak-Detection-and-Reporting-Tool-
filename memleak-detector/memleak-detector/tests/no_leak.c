/* Expected: 0 leaks */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
    char *a = malloc(100);
    int *b = calloc(10, sizeof *b);
    strcpy(a, "hello"); b[0] = 1;
    printf("%s %d\n", a, b[0]);
    free(a); free(b);
    return 0;
}
