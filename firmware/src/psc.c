/* TIM3 must tick at 1 MHz from the 16 MHz HSI. Checked against the SysTick free-running counter (2% band).
 * BUG 1: PSC = 16 (divides by 17) instead of 15. */
#include "rt.h"
void bench_main(void)
{
    RCC_APB1ENR |= 1u << 1;
#if BUG == 1
    TIM_PSC(TIM3_BASE) = 16u;
#else
    TIM_PSC(TIM3_BASE) = 15u;
#endif
    TIM_ARR(TIM3_BASE) = 0xFFFFu;
    TIM_EGR(TIM3_BASE) = 1u;
    SYST_RVR = 0xFFFFFFu;
    SYST_CVR = 0u;
    SYST_CSR = 5u;
    TIM_CR1(TIM3_BASE) = 1u;
    uint32_t t0 = TIM_CNT(TIM3_BASE), s0 = SYST_CVR;
    spin(3000u);
    uint32_t t1 = TIM_CNT(TIM3_BASE), s1 = SYST_CVR;
    uint32_t ds = (s0 - s1) & 0xFFFFFFu, dt = (t1 - t0) & 0xFFFFu;
    uint32_t want = ds, got = dt * 16u;
    uint32_t err = got > want ? got - want : want - got;
    if (ds != 0u && err * 50u <= want) {
        bench_pass("TIM3 at 1 MHz");
    } else {
        uart_puts("sys=");
        uart_put_hex(ds);
        uart_puts(" tim=");
        uart_put_hex(dt);
        uart_puts(" ");
        bench_fail("TIM3 tick rate outside 2%");
    }
}
