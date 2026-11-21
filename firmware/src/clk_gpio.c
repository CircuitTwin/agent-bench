/* Output a level on PD12 and read it back. BUG 1: the GPIOD clock is never enabled. */
#include "rt.h"
void bench_main(void)
{
#if BUG != 1
    RCC_AHB1ENR |= 1u << 3;
#endif
    GPIO_MODER(GPIOD_BASE) = (GPIO_MODER(GPIOD_BASE) & ~(3u << 24)) | (1u << 24);
    GPIO_BSRR(GPIOD_BASE) = 1u << 12;
    if ((GPIO_ODR(GPIOD_BASE) & (1u << 12)) != 0u) {
        bench_pass("PD12 high");
    } else {
        bench_fail("PD12 did not go high");
    }
}
