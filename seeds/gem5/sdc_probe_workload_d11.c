/*
 * sdc_probe_workload_d11.c — D11组 (多跨循环高ACE寄存器) gem5工作负载
 *
 * 根因: D10 bit=B=8.0%持平, 因D10和B结构相同(全volatile+LCG)
 *  B的ACE扫描: Reg[4]=63%高ACE(可能是acc/seed跨循环活)
 *  → 只有1个跨循环高ACE寄存器(acc/seed)
 *
 * D11策略: 增加3-4个跨循环活的高ACE寄存器
 *  1. acc(seed迭代) — 已有, 跨循环活
 *  2. running_crc — 循环内累积CRC, 每迭代都影响 → 跨循环高ACE
 *  3. running_xor — 循环内累积XOR, 跨循环活
 *  4. state(rng_state) — 直接流入输出
 *  → 4个跨循环高ACE寄存器 → bit-flip ACE>B
 *
 * 同时保留: 全volatile(同B, store+load双ACE) + 操作数多次引用(D6)
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_d11 sdc_probe_workload_d11.c
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

static uint64_t popcount64(uint64_t x) {
    x = (x & 0x5555555555555555ULL) + ((x >> 1) & 0x5555555555555555ULL);
    x = (x & 0x3333333333333333ULL) + ((x >> 2) & 0x3333333333333333ULL);
    x = (x + (x >> 4)) & 0x0F0F0F0F0F0F0F0FULL;
    return (x * 0x0101010101010101ULL) >> 56;
}

/* carry_chain: 全volatile + 多引用 + 跨循环acc */
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
    acc ^= (x3 << 4);
    acc += (x4 >> 3);
    acc ^= (x1 & x3);
    return acc;
}

static uint64_t toggle_rate(uint64_t acc) {
    volatile uint64_t a = rng_u64();
    volatile uint64_t b = rng_u64();
    acc += (a + b);
    acc ^= (a ^ b);
    acc &= (a & b);
    acc |= (a | b);
    acc -= (b - a);
    acc ^= (a >> 2);
    acc += (b << 3);
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
    volatile uint64_t *p14 = (volatile uint64_t *)(buf + 14);
    *p14 = v0;
    acc ^= *p14;
    volatile uint64_t *p60 = (volatile uint64_t *)(buf + 60);
    *p60 = v1;
    acc ^= *p60;
    acc += v0;
    acc ^= v1;
    return acc;
}

int main(void) {
    uint64_t sum = 0;
    uint32_t state = 0xCAFEBABEu;
    /* D11关键: 3个跨循环活的高ACE变量 */
    uint64_t running_crc = 0;    /* 跨循环累积CRC → 每迭代影响 → 高ACE */
    uint64_t running_xor = 0;    /* 跨循环累积XOR → 高ACE */
    uint64_t running_pop = 0;    /* 跨循环累积popcount → 高ACE */

    for (int i = 0; i < ITERS; i++) {
        uint64_t s = carry_chain(state);
        s = toggle_rate(s);
        double f = fsu_subnormal(s);
        s = lsu_cross(s);
        union { double d; uint64_t u; } cvt;
        cvt.d = f;
        uint64_t val = s ^ cvt.u ^ (uint64_t)(i + 1);

        /* D11: 3个跨循环累积 → 4个跨循环高ACE寄存器(sum, running_crc/xor/pop) */
        sum += val;
        running_crc ^= (val * 0x42F0E1EBA9EA3693ULL);  /* CRC-like累积 */
        running_xor ^= val;                              /* XOR累积 */
        running_pop += popcount64(val);                  /* popcount累积 */

        state = state * 1103515245u + 12345u;
    }

    /* 最终输出: sum + 3个跨循环累积 → 4个高ACE寄存器都影响输出 */
    uint64_t final_val = sum ^ running_crc ^ running_xor ^ running_pop;
    uint32_t crc = 0xFFFFFFFFu;
    uint64_t tmp = final_val;
    for (int b = 0; b < 8; b++) {
        uint8_t byte = (tmp >> (b * 8)) & 0xFF;
        crc ^= byte;
        for (int j = 0; j < 8; j++) {
            uint32_t mask = -(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    crc = ~crc;
    printf("SUM=%llu CRC=%08x\n", (unsigned long long)final_val, crc);
    return 0;
}
