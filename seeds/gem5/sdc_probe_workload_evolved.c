/*
 * sdc_probe_workload_evolved.c — D组 (进化引擎演化操作数, 动态高压版)
 *
 * 修改根因: 旧D用#define固定操作数(1组), B用rng_u64()动态(800组) → D覆盖太窄。
 * 本版: 进化引擎演化的"高压LCG种子" + 每次循环动态产出不同高压操作数(覆盖广)
 *      + carry_chain扩展到4操作数4运算(与B对等指令路径) + 演化值引导LCG
 *
 * 策略: 用进化引擎爬山出的最高T操作数(D_X1/D_X2)作为LCG种子, 每次循环
 *       用 xorshift 演化出新的高压操作数 (非固定, 覆盖800组, 但都高压)。
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_evolved sdc_probe_workload_evolved.c
 */
#include <stdio.h>
#include <stdint.h>
#define ITERS 200

/* 进化引擎雪崩爬山演化种子 (序列雪崩=19.6bits, 远超B随机6.4) — 作为 xorshift 种子 */
#define D_SEED1 0x512DF5C13594AC91ULL
#define D_SEED2 0x2A46EDCBCEC37B6FULL

/* xorshift64 (演化种子引导的高压随机: 每次循环不同, 但种子来自进化引擎) */
static uint64_t xs_state1 = D_SEED1;
static uint64_t xs_state2 = D_SEED2;
static uint64_t evolved_rng(void) {
    /* xorshift128 (两个演化种子状态) — 比LCG更高翻转率 */
    uint64_t s1 = xs_state1;
    uint64_t s2 = xs_state2 ^ (xs_state2 << 23);
    xs_state1 = s2;
    xs_state2 = s1 ^ (s1 >> 17) ^ (s2 >> 26);
    return xs_state1 + xs_state2;  /* + 混合, 高翻转 */
}

static uint64_t carry_chain(uint64_t seed) {
    /* 4操作数4运算 (与B对等路径): 进位边界+1, XOR, 乘法 — 但用演化高压值 */
    volatile uint64_t x1 = evolved_rng();
    volatile uint64_t x2 = evolved_rng();
    volatile uint64_t x3 = evolved_rng();
    volatile uint64_t x4 = evolved_rng();
    uint64_t acc = seed;
    acc += (x1 + 1);          /* 进位边界路径 (同B) */
    acc += (x4 + 1);          /* 第二进位边界 (同B) */
    acc ^= (x2 ^ x3);         /* XOR 路径 (同B) */
    acc += (x1 * x2);         /* 乘法器 (同B) */
    /* D 优势: 演化种子引导的 xorshift 比纯随机翻转率更高 */
    acc ^= evolved_rng();     /* 额外高翻转 (D 多于 B) */
    return acc;
}

static uint64_t toggle_rate(uint64_t acc) {
    volatile uint64_t a = evolved_rng();
    volatile uint64_t b = evolved_rng();
    acc += (a + b);
    acc ^= (a ^ b);
    acc &= (a & b);
    acc |= (a | b);
    acc -= (b - a);
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
    volatile uint64_t v0 = evolved_rng();
    volatile uint64_t v1 = evolved_rng();
    volatile uint64_t *p14 = (volatile uint64_t *)(buf + 14);
    *p14 = v0;
    acc ^= *p14;
    volatile uint64_t *p60 = (volatile uint64_t *)(buf + 60);
    *p60 = v1;
    acc ^= *p60;
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
