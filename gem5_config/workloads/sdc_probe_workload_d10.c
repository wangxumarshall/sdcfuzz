/*
 * sdc_probe_workload_d10.c — D10组 (D9+更多rng_u64覆盖) gem5工作负载
 *
 * 根因: D9 bit=6.8%接近B=8.0%但仍低, 因B有更多rng_u64调用(覆盖广)
 * D10策略: D9全volatile+多引用 + 每函数增加更多rng_u64调用(同B覆盖广度)
 *  = D9策略 + 更多操作数(8个per carry_chain, 6个per toggle)
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_d10 sdc_probe_workload_d10.c
 */
#include <stdio.h>
#include <stdint.h>
#define ITERS 200

static uint32_t rng_state = 0xDEADBEEFu;
static uint64_t rng_u64(void) {
    rng_state = rng_state * 1103515245u + 12345u;
    uint64_t lo = rng_state;
    rng_state = rng_state * 1103515245u + 12345u;
    uint64_t hi = rng_state;
    return (hi << 32) | lo;
}

/* carry_chain: 全volatile + 8个操作数(同B覆盖广) + 多次引用 */
static uint64_t carry_chain(uint64_t seed) {
    volatile uint64_t x1 = rng_u64();
    volatile uint64_t x2 = rng_u64();
    volatile uint64_t x3 = rng_u64();
    volatile uint64_t x4 = rng_u64();
    volatile uint64_t x5 = rng_u64();  /* 新增: 覆盖更广 */
    volatile uint64_t x6 = rng_u64();  /* 新增 */
    volatile uint64_t x7 = rng_u64();  /* 新增 */
    volatile uint64_t x8 = rng_u64();  /* 新增 */
    uint64_t acc = seed;
    acc += (x1 + 1);
    acc += (x4 + 1);
    acc ^= (x2 ^ x3);
    acc += (x1 * x2);
    acc ^= (x3 << 4);
    acc += (x4 >> 3);
    acc ^= (x1 & x3);
    /* 新增: x5-x8也参与计算(多次引用) */
    acc += (x5 + x6);
    acc ^= (x7 ^ x8);
    acc += (x5 * x7);
    acc ^= (x6 >> 2);
    acc += (x8 << 3);
    return acc;
}

/* toggle_rate: 全volatile + 6个操作数(增加覆盖) */
static uint64_t toggle_rate(uint64_t acc) {
    volatile uint64_t a = rng_u64();
    volatile uint64_t b = rng_u64();
    volatile uint64_t c = rng_u64();  /* 新增 */
    volatile uint64_t d = rng_u64();  /* 新增 */
    acc += (a + b);
    acc ^= (a ^ b);
    acc &= (a & b);
    acc |= (a | b);
    acc -= (b - a);
    acc ^= (a >> 2);
    acc += (b << 3);
    /* 新增: c,d也参与 */
    acc ^= (c ^ d);
    acc += (c * d);
    acc ^= (d >> 4);
    return acc;
}

static double fsu_subnormal(uint64_t acc) {
    volatile double d0 = 1.0;
    union { uint64_t u; double d; } sn;
    sn.u = 1;
    volatile double d1 = sn.d;
    volatile double r = d0 + d1;
    r *= d1;
    union { uint64_t u; double d; } inf;
    inf.u = 0x7FF0000000000000ULL;
    volatile double di = inf.d;
    r += (di + d1);
    return r + (double)acc;
}

static uint64_t lsu_cross(uint64_t acc) {
    static volatile uint8_t buf[256] __attribute__((aligned(64)));
    volatile uint64_t v0 = rng_u64();
    volatile uint64_t v1 = rng_u64();
    volatile uint64_t v2 = rng_u64();  /* 新增 */
    volatile uint64_t v3 = rng_u64();  /* 新增 */
    volatile uint64_t *p14 = (volatile uint64_t *)(buf + 14);
    *p14 = v0;
    acc ^= *p14;
    volatile uint64_t *p60 = (volatile uint64_t *)(buf + 60);
    *p60 = v1;
    acc ^= *p60;
    volatile uint64_t *p124 = (volatile uint64_t *)(buf + 124);  /* 新增: 跨128B L3 line */
    *p124 = v2;
    acc ^= *p124;
    acc += v0;
    acc ^= v1;
    acc ^= (v2 >> 1);  /* 新增 */
    acc += (v3 << 2);  /* 新增 */
    return acc;
}

int main(void) {
    uint64_t sum = 0;
    uint32_t state = 0xCAFEBABEu;
    for (int i = 0; i < ITERS; i++) {
        uint64_t s = carry_chain(state);
        s = toggle_rate(s);
        double f = fsu_subnormal(s);
        s = lsu_cross(s);
        union { double d; uint64_t u; } cvt;
        cvt.d = f;
        sum += s ^ cvt.u ^ (uint64_t)(i + 1);
        state = state * 1103515245u + 12345u;
    }
    uint32_t crc = 0xFFFFFFFFu;
    uint64_t tmp = sum;
    for (int b = 0; b < 8; b++) {
        uint8_t byte = (tmp >> (b * 8)) & 0xFF;
        crc ^= byte;
        for (int j = 0; j < 8; j++) {
            uint32_t mask = -(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    crc = ~crc;
    printf("SUM=%llu CRC=%08x\n", (unsigned long long)sum, crc);
    return 0;
}
