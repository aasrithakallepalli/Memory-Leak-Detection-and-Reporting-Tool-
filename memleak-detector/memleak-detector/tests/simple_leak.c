/* Expected: 1 leak, 100 bytes, at the malloc line in main */
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    char *leak = malloc(100);
    leak[0] = 'x';
    printf("allocated 100 bytes and forgot to free\n");
    return 0;
}
