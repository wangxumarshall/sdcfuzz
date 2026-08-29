/*
 * sdc_probe_workload_d5.c — D5组 (全寄存器ACE最大化) gem5工作负载
 *
 * 核心策略(击败B的正确路径):
 *   当前carry_chain只return acc, x1-x4是临时量(被覆盖) → 只有acc是ACE
 *   gem5翻转x1-x4物理寄存器不会diverge(它们后续被覆盖)
 *   B的diverge率8.0%主要来自翻转acc相关寄存器
 *
 *   D5策略: 让x1-x4也流入最终sum → 所有寄存器都携带输出相关数据
 *   → gem5翻转任何寄存器都可能diverge → ACE-比例最大化
 *
 *   具体: carry_chain返回acc^x1^x2^x3^x4(所有操作数混合入输出)
 *   toggle/lsu同理: 让所有操作数流入返回值
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_d5 sdc_probe_workload_d5.c
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

static uint64_t carry_chain(uint64_t seed) {
    volatile uint64_t x1 = rng_u64();
    volatile uint64_t x2 = rng_u64();
    volatile uint64_t x3 = rng_u64();
    volatile uint64_t x4 = rng_u64();
    uint64_t acc = seed;
    acc += (x1 + 1);
    acc += (x4 + 1);
    acc ^= (x2 ^ x3);
    acc += (x1 * x2);
    /* D5关键: 所有操作数混合入返回值 → 全寄存器ACE */
    return acc ^ x1 ^ x2 ^ x3 ^ x4;
}

static uint64_t toggle_rate(uint64_t acc) {
    volatile uint64_t a = rng_u64();
    volatile uint64_t b = rng_u64();
    uint64_t r = acc;
    r += (a + b);
    r ^= (a ^ b);
    r &= (a & b);
    r |= (a | b);
    r -= (b - a);
    /* D5: a,b也流入返回值 */
    return r ^ a ^ b;
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
    volatile uint64_t *p14 = (volatile uint64_t *)(buf + 14);
    *p14 = v0;
    acc ^= *p14;
    volatile uint64_t *p60 = (volatile uint64_t *)(buf + 60);
    *p60 = v1;
    acc ^= *p60;
    /* D5: v0,v1也流入返回值 (存储值也ACE) */
    return acc ^ v0 ^ v1;
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
