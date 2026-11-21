/* Recursive sum. BUG 1: depth 4000 at about 80 bytes a frame outruns the 128 KB of SRAM. */
#include "rt.h"
#if BUG == 1
#define DEPTH 4000u
#else
#define DEPTH 20u
#endif
static uint32_t recurse(uint32_t n)
{
    volatile uint32_t pad[16];
    pad[0] = n;
    if (n == 0u) {
        return 0u;
    }
    return recurse(n - 1u) + pad[0];
}
void bench_main(void)
{
    if (recurse(DEPTH) == DEPTH * (DEPTH + 1u) / 2u) {
        bench_pass("sum ok");
    } else {
        bench_fail("sum wrong");
    }
}
