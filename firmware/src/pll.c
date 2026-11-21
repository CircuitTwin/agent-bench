/* Bring the core to 168 MHz from the 8 MHz HSE, check the switch, return to HSI so the console keeps its rate.
 * BUG 1: FLASH_ACR wait states never set (5 WS needed at 168 MHz).
 * BUG 2: SW written right after PLLON and SWS checked at once, without waiting for PLLRDY. */
#include "rt.h"
#define FLASH_ACR REG(0x40023C00u)
void bench_main(void)
{
    RCC_CR |= 1u << 16;
    if (!WAITB((RCC_CR & (1u << 17)) != 0u, 100000u)) {
        bench_fail("HSE not ready");
    }
    RCC_PLLCFGR = 8u | (336u << 6) | (0u << 16) | (1u << 22) | (7u << 24);
    RCC_CR |= 1u << 24;
#if BUG != 2
    if (!WAITB((RCC_CR & (1u << 25)) != 0u, 100000u)) {
        bench_fail("PLL not ready");
    }
#endif
#if BUG != 1
    FLASH_ACR = 5u | (1u << 8) | (1u << 9) | (1u << 10);
#endif
    RCC_CFGR = (RCC_CFGR & ~3u) | (5u << 10) | (4u << 13) | 2u;
#if BUG == 2
    uint32_t sws = (RCC_CFGR >> 2) & 3u;
#else
    (void)WAITB(((RCC_CFGR >> 2) & 3u) == 2u, 100000u);
    uint32_t sws = (RCC_CFGR >> 2) & 3u;
#endif
    RCC_CFGR &= ~3u;
    (void)WAITB(((RCC_CFGR >> 2) & 3u) == 0u, 100000u);
    RCC_CFGR &= ~((7u << 10) | (7u << 13)); /* APB prescalers back to 1: USART2 keeps 115200 at 16 MHz */
    if (sws == 2u) {
        bench_pass("running from the PLL");
    } else {
        bench_fail("SWS never showed the PLL");
    }
}
