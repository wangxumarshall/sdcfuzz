/*
 * sdc_probe_workload_d13.c — D13组 (基于随机值+定向变异的进化引擎) gem5工作负载
 *
 * 用户核心洞察: "定向变异是基于随机值的基础上再定向变异,不是基于固定值"
 *  即: 每次随机后, 下次操作数对"上次随机值的定向变异值"和"第二次随机值"
 *  做评估, 选择更能激发SDC的操作数。
 *
 * D13实现: 在运行时(runtime)做定向变异选择
 *  - carry_chain: 生成2个随机候选(rng_u64 A, rng_u64 B)
 *    对A做定向变异(A^mask, A+1, A<<1) → 得A'
 *    评估A' vs B: 选高翻转量(高ACE)的作为操作数
 *  - 不是固定值, 而是运行时随机+定向选择 → 覆盖广(同B)+定向(高ACE)
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_d13 sdc_probe_workload_d13.c
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

/* 定向变异: 对随机值A做变异, 生成A'
   变异方式: XOR mask / +1 / <<1 / ~ (位翻转) */
static uint64_t targeted_mutate(uint64_t a) {
    uint64_t mask = rng_u64();  /* 随机mask */
    uint64_t a_mut = a ^ mask;  /* XOR变异 */
    a_mut += 1;                 /* 进位链触发 */
    a_mut = (a_mut << 1) | (a_mut >> 63);  /* 循环位移 */
    a_mut ^= ~a;                /* 与原值XOR (差异放大) */
    return a_mut;
}

/* 评估: 哪个操作数更高翻转量(高ACE代理) */
static uint64_t pick_high_toggle(uint64_t a, uint64_t b) {
    /* 定向变异A → A' */
    uint64_t a_mut = targeted_mutate(a);
    /* 评估A' vs B: 选popcount更高的(更多bit翻转→更高ACE概率) */
    uint64_t a_eval = a_mut ^ (a_mut + 1);  /* A'与A'+1的差(进位链长度代理) */
    uint64_t b_eval = b ^ (b + 1);
    if (popcount64(a_eval) >= popcount64(b_eval)) {
        return a_mut;  /* A'的定向变异值更优 */
    } else {
        return b;      /* B的随机值更优 */
    }
}

/* carry_chain: 随机值+定向变异选择(非固定值) */
static uint64_t carry_chain(uint64_t seed) {
    /* 每次生成2个随机候选, 定向变异后选高ACE的 */
    volatile uint64_t x1 = pick_high_toggle(rng_u64(), rng_u64());
    volatile uint64_t x2 = pick_high_toggle(rng_u64(), rng_u64());
    volatile uint64_t x3 = pick_high_toggle(rng_u64(), rng_u64());
    volatile uint64_t x4 = pick_high_toggle(rng_u64(), rng_u64());
    volatile uint64_t x5 = rng_u64();  /* 纯随机(保留覆盖广度) */
    volatile uint64_t x6 = rng_u64();
    volatile uint64_t x7 = rng_u64();
    volatile uint64_t x8 = rng_u64();
    uint64_t acc = seed;
    acc += (x1 + 1);
    acc += (x4 + 1);
    acc ^= (x2 ^ x3);
    acc += (x1 * x2);
    acc ^= (x3 << 4);
    acc += (x4 >> 3);
    acc ^= (x1 & x3);
    acc += (x5 + x6);
    acc ^= (x7 ^ x8);
    acc += (x5 * x7);
    acc ^= (x6 >> 2);
    acc += (x8 << 3);
    return acc;
}

static uint64_t toggle_rate(uint64_t acc) {
    volatile uint64_t a = pick_high_toggle(rng_u64(), rng_u64());
    volatile uint64_t b = pick_high_toggle(rng_u64(), rng_u64());
    volatile uint64_t c = rng_u64();
    volatile uint64_t d = rng_u64();
    acc += (a + b);
    acc ^= (a ^ b);
    acc &= (a & b);
    acc |= (a | b);
    acc -= (b - a);
    acc ^= (a >> 2);
    acc += (b << 3);
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
    volatile uint64_t v0 = pick_high_toggle(rng_u64(), rng_u64());
    volatile uint64_t v1 = pick_high_toggle(rng_u64(), rng_u64());
    volatile uint64_t v2 = rng_u64();
    volatile uint64_t v3 = rng_u64();
    volatile uint64_t *p14 = (volatile uint64_t *)(buf + 14);
    *p14 = v0;
    acc ^= *p14;
    volatile uint64_t *p60 = (volatile uint64_t *)(buf + 60);
    *p60 = v1;
    acc ^= *p60;
    volatile uint64_t *p124 = (volatile uint64_t *)(buf + 124);
    *p124 = v2;
    acc ^= *p124;
    acc += v0;
    acc ^= v1;
    acc ^= (v2 >> 1);
    acc += (v3 << 2);
    return acc;
}

int main(void) {
    uint64_t sum = 0;
    uint32_t state = 0xCAFEBABEu;
    uint64_t running_crc = 0;
    uint64_t running_xor = 0;
    uint64_t running_pop = 0;

    for (int i = 0; i < ITERS; i++) {
        uint64_t s = carry_chain(state);
        s = toggle_rate(s);
        double f = fsu_subnormal(s);
        s = lsu_cross(s);
        union { double d; uint64_t u; } cvt;
        cvt.d = f;
        uint64_t val = s ^ cvt.u ^ (uint64_t)(i + 1);

        sum += val;
        running_crc ^= (val * 0x42F0E1EBA9EA3693ULL);
        running_xor ^= val;
        running_pop += popcount64(val);

        state = state * 1103515245u + 12345u;
    }

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
