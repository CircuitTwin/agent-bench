/* Drive PD12 high and read the pin back.
 * BUG 1: writes GPIOD_IDR (read-only) instead of BSRR.  BUG 2: stores to flash without unlocking it. */
#include "rt.h"
void bench_main(void)
{
#if BUG == 2
    volatile uint32_t *f = (volatile uint32_t *)0x08008000u;
    *f = 0x12345678u;
    if (*f == 0x12345678u) {
        bench_pass("flash word stored");
    } else {
        bench_fail("flash word unchanged");
    }
#else
    RCC_AHB1ENR |= 1u << 3;
    GPIO_MODER(GPIOD_BASE) = (GPIO_MODER(GPIOD_BASE) & ~(3u << 24)) | (1u << 24);
#if BUG == 1
    GPIO_IDR(GPIOD_BASE) = 1u << 12;
#else
    GPIO_BSRR(GPIOD_BASE) = 1u << 12;
#endif
    if ((GPIO_IDR(GPIOD_BASE) & (1u << 12)) != 0u) {
        bench_pass("PD12 high");
    } else {
        bench_fail("PD12 low");
    }
#endif
}
