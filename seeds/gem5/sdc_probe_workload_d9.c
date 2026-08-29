/*
 * sdc_probe_workload_d9.c — D9组 (全volatile+多引用+全流入+lsu forwarding) gem5工作负载
 *
 * 根因发现: B的bit-flip高(8.0%)因volatile全程使操作数走stack→每操作数有store+load双ACE路径
 * D8去volatile(carry/toggle)→无store→load→bit-flip只打寄存器→ACE低
 *
 * D9策略: 全volatile(同B, store+load双路径) + 操作数多次引用(D6, 多cycle ACE)
 *         + 全寄存器流入输出(D5, 更多ACE寄存器) + lsu forwarding(D8, struct高ACE)
 *  = B的结构 × D6多引用 × D5全流入 × D8 forwarding → 三者叠加
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_d9 sdc_probe_workload_d9.c
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

/* carry_chain: 全volatile(同B, store+load双ACE) + 多次引用(D6, 多cycle) */
static uint64_t carry_chain(uint64_t seed) {
    volatile uint64_t x1 = rng_u64();  /* volatile→stack, store+load双路径 */
    volatile uint64_t x2 = rng_u64();
    volatile uint64_t x3 = rng_u64();
    volatile uint64_t x4 = rng_u64();
    uint64_t acc = seed;
    acc += (x1 + 1);          /* x1第1次引用 */
    acc += (x4 + 1);          /* x4第1次 */
    acc ^= (x2 ^ x3);         /* x2第1次, x3第1次 */
    acc += (x1 * x2);         /* x1第2次, x2第2次 */
    acc ^= (x3 << 4);         /* x3第2次, 新路径(位移) */
    acc += (x4 >> 3);         /* x4第2次, 新路径(位移) */
    acc ^= (x1 & x3);         /* x1第3次, x3第3次, 新路径(AND) */
    return acc;  /* 不加额外XOR(避免掩蔽) */
}

/* toggle_rate: 全volatile + 操作数多次引用 */
static uint64_t toggle_rate(uint64_t acc) {
    volatile uint64_t a = rng_u64();
    volatile uint64_t b = rng_u64();
    acc += (a + b);           /* a1,b1 */
    acc ^= (a ^ b);           /* a2,b2 */
    acc &= (a & b);           /* a3,b3 */
    acc |= (a | b);           /* a4,b4 */
    acc -= (b - a);           /* b5,a5 */
    acc ^= (a >> 2);          /* a6, 新路径 */
    acc += (b << 3);          /* b6, 新路径 */
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

/* lsu_cross: 全volatile(同B, store+load forwarding) */
static uint64_t lsu_cross(uint64_t acc) {
    static volatile uint8_t buf[256] __attribute__((aligned(64)));
    volatile uint64_t v0 = rng_u64();
    volatile uint64_t v1 = rng_u64();
    volatile uint64_t *p14 = (volatile uint64_t *)(buf + 14);
    *p14 = v0;
    acc ^= *p14;             /* store→load forwarding */
    volatile uint64_t *p60 = (volatile uint64_t *)(buf + 60);
    *p60 = v1;
    acc ^= *p60;
    acc += v0;               /* v0第3次引用 */
    acc ^= v1;               /* v1第3次引用 */
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
