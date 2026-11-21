/* Read a 64-bit pair from a byte buffer.
 * BUG 1: LDRD at buf + 2 (LDRD/LDM always fault on a misaligned address).
 * BUG 2: CCR.UNALIGN_TRP set, then a plain word load at buf + 1. */
#include "rt.h"
static volatile uint8_t buf[16] __attribute__((aligned(8))) = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};
void bench_main(void)
{
    uint32_t a = 0, b = 0;
#if BUG == 1
    volatile uint8_t *p = buf + 2;
    __asm volatile("ldrd %0, %1, [%2]" : "=&r"(a), "=&r"(b) : "r"(p) : "memory");
#elif BUG == 2
    SCB_CCR |= 1u << 3;
    a = *(volatile uint32_t *)(buf + 1);
#else
    volatile uint8_t *p = buf;
    __asm volatile("ldrd %0, %1, [%2]" : "=&r"(a), "=&r"(b) : "r"(p) : "memory");
#endif
    if (a != 0u || b != 0u) {
        bench_pass("loaded");
    } else {
        bench_fail("zero");
    }
}
