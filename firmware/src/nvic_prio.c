/* The TIM3 handler waits for the next SysTick tick, so SysTick must be able to preempt it.
 * BUG 1: TIM3 priority set to 0 (most urgent, "so it is never delayed"), the same as SysTick: no preemption. */
#include "rt.h"
static volatile uint32_t st_ticks, saw_tick, done;
void SysTick_Handler(void) { st_ticks++; }
void TIM3_IRQHandler(void)
{
    uint32_t t = st_ticks;
    uint32_t n = 200000u;
    TIM_SR(TIM3_BASE) = 0u;
    while (st_ticks == t && n != 0u) {
        n--;
    }
    saw_tick = (st_ticks != t);
    done = 1u;
    TIM_DIER(TIM3_BASE) = 0u;
}
void bench_main(void)
{
    SYST_RVR = 16000u - 1u;
    SYST_CVR = 0u;
    SYST_CSR = 7u;
    RCC_APB1ENR |= 1u << 1;
    TIM_PSC(TIM3_BASE) = 15u;
    TIM_ARR(TIM3_BASE) = 999u;
    TIM_EGR(TIM3_BASE) = 1u;
    TIM_SR(TIM3_BASE) = 0u;
#if BUG == 1
    NVIC_IPR8(IRQ_TIM3) = 0x00u;
#else
    NVIC_IPR8(IRQ_TIM3) = 0x80u;
#endif
    TIM_DIER(TIM3_BASE) = 1u;
    NVIC_ISER(0) = 1u << IRQ_TIM3;
    TIM_CR1(TIM3_BASE) = 1u;
    if (!WAITB(done != 0u, 2000000u)) {
        bench_fail("TIM3 handler never ran");
    } else if (saw_tick != 0u) {
        bench_pass("SysTick preempted the TIM3 handler");
    } else {
        bench_fail("SysTick never ran inside the TIM3 handler");
    }
}
