/* Send a byte and wait until the transmitter is done. BUG 1: waits on RXNE (bit 5, needs a received byte
 * that never comes) instead of TC (bit 6); the poll has no bound. */
#include "rt.h"
void bench_main(void)
{
    USART2_DR = (uint32_t)'.';
#if BUG == 1
    while ((USART2_SR & 0x20u) == 0u) { }
#else
    while ((USART2_SR & 0x40u) == 0u) { }
#endif
    bench_pass("byte sent");
}
