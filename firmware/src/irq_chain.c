/* TIM3 update interrupt at 1 kHz; the handler counts ticks, main waits for three.
 * BUG 1: NVIC enable (ISER) forgotten.  BUG 2: DIER.UIE forgotten.
 * BUG 3: the handler never clears UIF (the interrupt re-enters forever).
 * BUG 4: handler misspelled (TIM3_IRQHandle), so the vector keeps the default handler. */
#include "rt.h"
static volatile uint32_t ticks;
#if BUG == 4
void TIM3_IRQHandle(void)
#else
void TIM3_IRQHandler(void)
#endif
{
#if BUG != 3
    TIM_SR(TIM3_BASE) = 0u;
#endif
    ticks++;
}
void bench_main(void)
{
    RCC_APB1ENR |= 1u << 1;
    TIM_PSC(TIM3_BASE) = 15u;
    TIM_ARR(TIM3_BASE) = 999u;
    TIM_EGR(TIM3_BASE) = 1u;
    TIM_SR(TIM3_BASE) = 0u;
#if BUG != 2
    TIM_DIER(TIM3_BASE) = 1u;
#endif
#if BUG != 1
    NVIC_ISER(0) = 1u << IRQ_TIM3;
#endif
    TIM_CR1(TIM3_BASE) = 1u;
    if (WAITB(ticks >= 3u, 400000u)) {
        bench_pass("3 ticks");
    } else {
        bench_fail("timer interrupt did not run");
    }
}
