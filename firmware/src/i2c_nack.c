/* Address a sensor (0x68) that is not on the bus. The firmware must see the NACK (SR1.AF) and report it.
 * BUG 1: waits for ADDR only, without bound.  BUG 2: bounded wait, NACK never checked, reports the read as done. */
#include "rt.h"
#define I2C1 0x40005400u
#define I2C_CR1 REG(I2C1 + 0x00u)
#define I2C_CR2 REG(I2C1 + 0x04u)
#define I2C_DR REG(I2C1 + 0x10u)
#define I2C_SR1 REG(I2C1 + 0x14u)
#define I2C_SR2 REG(I2C1 + 0x18u)
#define I2C_CCR REG(I2C1 + 0x1Cu)
#define I2C_TRISE REG(I2C1 + 0x20u)
#define GPIOB 0x40020400u
void bench_main(void)
{
    RCC_AHB1ENR |= 1u << 1;
    GPIO_MODER(GPIOB) = (GPIO_MODER(GPIOB) & ~(0xFu << 12)) | (0xAu << 12);
    REG(GPIOB + 0x04u) |= (3u << 6);
    GPIO_AFRL(GPIOB) = (GPIO_AFRL(GPIOB) & ~(0xFFu << 24)) | (0x44u << 24);
    RCC_APB1ENR |= 1u << 21;
    I2C_CR2 = 16u;
    I2C_CCR = 80u;
    I2C_TRISE = 17u;
    I2C_CR1 = 1u;
    I2C_CR1 |= 1u << 8;
    if (!WAITB((I2C_SR1 & 1u) != 0u, 100000u)) {
        bench_fail("no start condition");
        return;
    }
    I2C_DR = 0x68u << 1;
#if BUG == 1
    while ((I2C_SR1 & 2u) == 0u) { }
    bench_pass("address acknowledged");
#elif BUG == 2
    (void)WAITB((I2C_SR1 & 2u) != 0u, 100000u);
    I2C_CR1 |= 1u << 9;
    bench_pass("sensor read done");
#else
    if (WAITB((I2C_SR1 & ((1u << 10) | 2u)) != 0u, 100000u) && (I2C_SR1 & (1u << 10)) != 0u) {
        I2C_SR1 &= ~(1u << 10);
        I2C_CR1 |= 1u << 9;
        bench_pass("NACK seen and handled");
    } else {
        bench_fail("no NACK and no ACK");
    }
#endif
}
