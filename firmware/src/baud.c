/* Report the result at 115200 baud, as the peer expects (HSI 16 MHz, BRR = 0x8B).
 * BUG 1: BRR computed for a 42 MHz APB1 clock (0x16C) that no code ever configured. */
#include "rt.h"
void bench_main(void)
{
    while ((USART2_SR & 0x40u) == 0u) { }
#if BUG == 1
    USART2_BRR = 0x16Cu;
#else
    USART2_BRR = 0x8Bu;
#endif
    bench_pass("sent at the configured rate");
}
