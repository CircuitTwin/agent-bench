/* Drive PD12 high as an output and read the pin level (IDR) back.
 * BUG 1: MODER written with the pin number as the shift (1 << 12) instead of 2 * pin (1 << 24). */
#include "rt.h"
void bench_main(void)
{
    RCC_AHB1ENR |= 1u << 3;
#if BUG == 1
    GPIO_MODER(GPIOD_BASE) = (GPIO_MODER(GPIOD_BASE) & ~(3u << 12)) | (1u << 12);
#else
    GPIO_MODER(GPIOD_BASE) = (GPIO_MODER(GPIOD_BASE) & ~(3u << 24)) | (1u << 24);
#endif
    GPIO_BSRR(GPIOD_BASE) = 1u << 12;
    if ((GPIO_IDR(GPIOD_BASE) & (1u << 12)) != 0u) {
        bench_pass("PD12 reads high");
    } else {
        bench_fail("PD12 reads low");
    }
}
