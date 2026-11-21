/* DMA2 stream 0 memory-to-memory copy of 16 words.
 * BUG 1: DMA2 clock never enabled.  BUG 2: FIFO left in direct mode (DMDIS=0), which memory-to-memory forbids.
 * BUG 3: length register left at 0 (the element count was computed from a decayed pointer). */
#include "rt.h"
#define DMA2 0x40026400u
#define DMA_LISR REG(DMA2 + 0x00u)
#define DMA_LIFCR REG(DMA2 + 0x08u)
#define S0CR REG(DMA2 + 0x10u)
#define S0NDTR REG(DMA2 + 0x14u)
#define S0PAR REG(DMA2 + 0x18u)
#define S0M0AR REG(DMA2 + 0x1Cu)
#define S0FCR REG(DMA2 + 0x24u)
static volatile uint32_t src[16], dst[16];
void bench_main(void)
{
    for (uint32_t i = 0; i < 16u; i++) {
        src[i] = 0xC0DE0000u + i;
        dst[i] = 0u;
    }
#if BUG != 1
    RCC_AHB1ENR |= 1u << 22;
#endif
    S0CR = 0u;
    (void)WAITB((S0CR & 1u) == 0u, 10000u);
    DMA_LIFCR = 0x3Du;
    S0PAR = (uint32_t)(uintptr_t)src;
    S0M0AR = (uint32_t)(uintptr_t)dst;
#if BUG == 3
    S0NDTR = 0u;
#else
    S0NDTR = 16u;
#endif
#if BUG == 2
    S0FCR = 3u;
#else
    S0FCR = 3u | (1u << 2);
#endif
    S0CR = (2u << 6) | (1u << 9) | (1u << 10) | (2u << 11) | (2u << 13) | 1u;
    if (!WAITB((DMA_LISR & (1u << 5)) != 0u, 100000u)) {
        bench_fail("no transfer-complete flag");
        return;
    }
    for (uint32_t i = 0; i < 16u; i++) {
        if (dst[i] != src[i]) {
            bench_fail("destination differs");
            return;
        }
    }
    bench_pass("16 words copied");
}
