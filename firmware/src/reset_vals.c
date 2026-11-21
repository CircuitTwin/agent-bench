/* Use a word of SRAM nobody wrote since reset (the unused heap area).
 * BUG 1: assumes it reads as zero; a vendor documents SRAM contents after power-up as undefined. */
#include "rt.h"
extern uint32_t end;
void bench_main(void)
{
    volatile uint32_t *p = &end;
#if BUG != 1
    for (uint32_t i = 0; i < 8u; i++) {
        p[i] = 0u;
    }
#endif
    for (uint32_t i = 0; i < 8u; i++) {
        if (p[i] != 0u) {
            bench_fail("scratch word is not zero");
        }
    }
    bench_pass("scratch zero");
}
