/* Agent-bench runtime: register addresses, console, result line. Bare metal, no CMSIS, no libc. */
#ifndef RT_H
#define RT_H
#include <stdint.h>

#define REG(a) (*(volatile uint32_t *)(a))

#define RCC_CR REG(0x40023800u)
#define RCC_PLLCFGR REG(0x40023804u)
#define RCC_CFGR REG(0x40023808u)
#define RCC_AHB1ENR REG(0x40023830u)
#define RCC_APB1ENR REG(0x40023840u)
#define RCC_APB2ENR REG(0x40023844u)
#define RCC_CSR REG(0x40023874u)

#define GPIOA_BASE 0x40020000u
#define GPIOD_BASE 0x40020C00u
#define GPIO_MODER(b) REG((b) + 0x00u)
#define GPIO_IDR(b) REG((b) + 0x10u)
#define GPIO_ODR(b) REG((b) + 0x14u)
#define GPIO_BSRR(b) REG((b) + 0x18u)
#define GPIO_AFRL(b) REG((b) + 0x20u)

#define USART2_SR REG(0x40004400u)
#define USART2_DR REG(0x40004404u)
#define USART2_BRR REG(0x40004408u)
#define USART2_CR1 REG(0x4000440Cu)

#define TIM3_BASE 0x40000400u
#define TIM_CR1(b) REG((b) + 0x00u)
#define TIM_DIER(b) REG((b) + 0x0Cu)
#define TIM_SR(b) REG((b) + 0x10u)
#define TIM_EGR(b) REG((b) + 0x14u)
#define TIM_CNT(b) REG((b) + 0x24u)
#define TIM_PSC(b) REG((b) + 0x28u)
#define TIM_ARR(b) REG((b) + 0x2Cu)

#define NVIC_ISER(n) REG(0xE000E100u + 4u * (n))
#define NVIC_IPR8(irq) (*(volatile uint8_t *)(0xE000E400u + (irq)))
#define SYST_CSR REG(0xE000E010u)
#define SYST_RVR REG(0xE000E014u)
#define SYST_CVR REG(0xE000E018u)
#define SCB_SHPR3 REG(0xE000ED20u)
#define SCB_CCR REG(0xE000ED14u)

#define IRQ_TIM3 29u

void uart_puts(const char *s);
void uart_put_hex(uint32_t v);
void bench_pass(const char *msg);
void bench_fail(const char *msg);
void bench_main(void);
static inline void spin(uint32_t n) { while (n--) __asm volatile("" ::: "memory"); }
/* Bounded wait: evaluates to the final value of cond after at most n polls. */
#define WAITB(cond, n) ({ uint32_t _n = (n); while (!(cond) && _n != 0u) { _n--; } (cond); })
#endif
