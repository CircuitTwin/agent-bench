# case:highest-bug-version (version 0 is always the correct firmware). Mirrors ../cases.json.
set(AGENT_BENCH_CASES
    clk_gpio:1 clk_timer:1 gpio_mode:1 poll_flag:1 irq_chain:4 nvic_prio:1 dma_m2m:3 wdg:1 baud:1
    i2c_nack:2 reset_vals:1 stack:1 unaligned:2 race:1 psc:1 ro_write:2 pll:2)
