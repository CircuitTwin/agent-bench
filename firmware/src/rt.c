#include "rt.h"

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;

void Default_Handler(void) { for (;;) { } }
void SysTick_Handler(void) __attribute__((weak, alias("Default_Handler")));
void TIM3_IRQHandler(void) __attribute__((weak, alias("Default_Handler")));

void Reset_Handler(void);
int main(void);

__attribute__((section(".isr_vector"), used)) void (*const vectors[98])(void) = {
    [0 ... 97] = Default_Handler,
    [0] = (void (*)(void))&_estack,
    [1] = Reset_Handler,
    [15] = SysTick_Handler,
    [16 + IRQ_TIM3] = TIM3_IRQHandler,
};

void Reset_Handler(void)
{
    uint32_t *s = &_sidata;
    for (uint32_t *d = &_sdata; d < &_edata;) {
        *d++ = *s++;
    }
    for (uint32_t *d = &_sbss; d < &_ebss;) {
        *d++ = 0;
    }
    (void)main();
    for (;;) { }
}

static void uart_init(void)
{
    RCC_AHB1ENR |= 1u;                      /* GPIOA */
    GPIO_MODER(GPIOA_BASE) = (GPIO_MODER(GPIOA_BASE) & ~(3u << 4)) | (2u << 4); /* PA2 AF */
    GPIO_AFRL(GPIOA_BASE) = (GPIO_AFRL(GPIOA_BASE) & ~(0xFu << 8)) | (7u << 8); /* AF7 */
    RCC_APB1ENR |= 1u << 17;                /* USART2 */
    USART2_BRR = 0x8Bu;                     /* 16 MHz / 115200 */
    USART2_CR1 = (1u << 13) | (1u << 3);    /* UE | TE */
}

static void put_char(char c)
{
    while ((USART2_SR & 0x80u) == 0u) { }
    USART2_DR = (uint32_t)(uint8_t)c;
}

void uart_puts(const char *s)
{
    while (*s != '\0') {
        put_char(*s++);
    }
}

void uart_put_hex(uint32_t v)
{
    static const char d[] = "0123456789ABCDEF";
    uart_puts("0x");
    for (int i = 7; i >= 0; i--) {
        put_char(d[(v >> (4 * i)) & 0xFu]);
    }
}

static void result(const char *verdict, const char *msg)
{
    uart_puts("CT-BENCH ");
    uart_puts(CASE_NAME);
    uart_puts(" ");
    uart_puts(verdict);
    uart_puts(" ");
    uart_puts(msg);
    uart_puts("\r\nCT-BENCH-DONE\r\n");
    for (;;) { }
}

void bench_pass(const char *msg) { result("PASS", msg); }
void bench_fail(const char *msg) { result("FAIL", msg); }

int main(void)
{
    uart_init();
    bench_main();
    return 0;
}
