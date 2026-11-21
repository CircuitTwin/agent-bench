/* Start the independent watchdog (about 31 ms), then work for about 200 ms.
 * BUG 1: the loop never kicks the watchdog. A watchdog reset shows as RCC_CSR.IWDGRSTF at the next boot. */
#include "rt.h"
#define IWDG_KR REG(0x40003000u)
#define IWDG_PR REG(0x40003004u)
#define IWDG_RLR REG(0x40003008u)
#define IWDG_SR REG(0x4000300Cu)
void bench_main(void)
{
    if ((RCC_CSR & (1u << 29)) != 0u) {
        RCC_CSR |= 1u << 24;
        bench_fail("booted after a watchdog reset");
    }
    IWDG_KR = 0xCCCCu; /* start first: the counter then runs from 0xFFF (RM0090 IWDG); the reload below loads RLR */
    IWDG_KR = 0x5555u;
    IWDG_PR = 0u;
    IWDG_RLR = 250u;
    while (IWDG_SR != 0u) { } /* PVU and RVU clear: the new values are active (RM0090, IWDG_SR) */
    IWDG_KR = 0xAAAAu;
    for (uint32_t i = 0; i < 40u; i++) {
        spin(20000u);
#if BUG != 1
        IWDG_KR = 0xAAAAu;
#endif
    }
    bench_pass("worked 200 ms");
}
