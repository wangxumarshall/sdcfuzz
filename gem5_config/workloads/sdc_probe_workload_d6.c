/*
 * sdc_probe_workload_d6.c — D6组 (操作数多次引用+多路径ACE) gem5工作负载
 *
 * 核心策略(基于ACE扫描数据):
 *   D5是B的超集(额外XOR)但ACE更低(6.1%<7.6%) → 额外XOR掩蔽了bit翻转
 *   B的Reg[4]有63% ACE概率 — 操作数在acc计算中被直接引用(高ACE)
 *
 * D6策略: 不加额外XOR(避免掩蔽), 而是让操作数在循环中被多次引用:
 *   1. carry_chain: x1被用3次(add+multiply+shift), x2被用3次(xor+multiply+add)
 *      → 每个操作数在多个cycle携带输出关键数据 → 高ACE概率
 *   2. toggle_rate: a被用4次(+,^,&,|), b被用4次(+,^,&,|)
 *   3. 不加额外XOR(return acc, 不XOR操作数) → 避免掩蔽
 *   4. 多路径: add/mul/xor/shift/and/or — 每个路径都依赖操作数 → 多cycle ACE
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_d6 sdc_probe_workload_d6.c
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
    /* D6: 操作数多次引用(多cycle ACE) */
    acc += (x1 + 1);          /* x1第1次: 进位边界 */
    acc += (x4 + 1);          /* x4第1次: 进位边界 */
    acc ^= (x2 ^ x3);         /* x2第1次, x3第1次: XOR */
    acc += (x1 * x2);         /* x1第2次, x2第2次: 乘法 */
    acc ^= (x3 << 4);         /* x3第2次: 位移(新路径) */
    acc += (x4 >> 3);         /* x4第2次: 位移(新路径) */
    acc ^= (x1 & x3);         /* x1第3次, x3第3次: AND(新路径) */
    /* 不加额外XOR — 避免掩蔽 */
    return acc;
}

static uint64_t toggle_rate(uint64_t acc) {
    volatile uint64_t a = rng_u64();
    volatile uint64_t b = rng_u64();
    /* D6: 操作数4次引用(多路径) */
    acc += (a + b);           /* a1,b1: 加法 */
    acc ^= (a ^ b);           /* a2,b2: XOR */
    acc &= (a & b);           /* a3,b3: AND */
    acc |= (a | b);           /* a4,b4: OR */
    acc -= (b - a);           /* b5,a5: 减法 */
    acc ^= (a >> 2);          /* a6: 位移 */
    acc += (b << 3);          /* b6: 位移 */
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
    /* D6: store/load多次引用(多cycle ACE) */
    volatile uint64_t *p14 = (volatile uint64_t *)(buf + 14);
    *p14 = v0;               /* v0第1次: store */
    acc ^= *p14;             /* v0第2次: load+use */
    volatile uint64_t *p60 = (volatile uint64_t *)(buf + 60);
    *p60 = v1;               /* v1第1次: store */
    acc ^= *p60;             /* v1第2次: load+use */
    acc += v0;               /* v0第3次: 直接引用(多cycle ACE) */
    acc ^= v1;               /* v1第3次: 直接引用 */
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
