/* Start TIM3 and expect its counter to advance. BUG 1: the TIM3 clock is never enabled. */
#include "rt.h"
void bench_main(void)
{
#if BUG != 1
    RCC_APB1ENR |= 1u << 1;
#endif
    TIM_PSC(TIM3_BASE) = 15u;
    TIM_ARR(TIM3_BASE) = 0xFFFFu;
    TIM_EGR(TIM3_BASE) = 1u;
    TIM_CR1(TIM3_BASE) = 1u;
    spin(2000u);
    if (TIM_CNT(TIM3_BASE) > 0u) {
        bench_pass("TIM3 counting");
    } else {
        bench_fail("TIM3 counter stuck at 0");
    }
}
