/* SysTick handler publishes a pair (a, ~a); main reads the pair and checks the invariant.
 * BUG 1: main reads the two words without masking interrupts (torn read when the handler runs between them). */
#include "rt.h"
static volatile uint32_t va, vb, n;
void SysTick_Handler(void)
{
    n++;
    va = n;
    vb = ~n;
}
void bench_main(void)
{
    va = 0u;
    vb = ~0u;
    SYST_RVR = 200u;
    SYST_CVR = 0u;
    SYST_CSR = 7u;
    for (uint32_t i = 0; i < 20000u; i++) {
        uint32_t x, y;
#if BUG != 1
        __asm volatile("cpsid i" ::: "memory");
#endif
        x = va;
        y = vb;
#if BUG != 1
        __asm volatile("cpsie i" ::: "memory");
#endif
        if (x != ~y) {
            bench_fail("torn read");
        }
    }
    if (n == 0u) {
        bench_fail("handler never ran");
    }
    bench_pass("pair consistent");
}
