/*
 * sdc_probe_workload_d7.c — D7组 (去volatile+寄存器保持+多引用) gem5工作负载
 *
 * 关键发现(反汇编B): volatile强制操作数存stack, X1-X4只是临时
 *  → 翻转X1-X4只影响load/store瞬间, 不是整个计算
 *
 * D7策略:
 *   1. 去掉volatile → 编译器把操作数分配到X1-X4寄存器, 全程保持
 *   2. 操作数多次引用(多cycle ACE): x1用3次, x2用3次, x3用3次, x4用2次
 *   3. 不加额外XOR(避免掩蔽)
 *   4. -O2让编译器内联rng_u64, 操作数全程在寄存器
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_d7 sdc_probe_workload_d7.c
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
    /* D7: 无volatile → 编译器用寄存器保持x1-x4 */
    uint64_t x1 = rng_u64();
    uint64_t x2 = rng_u64();
    uint64_t x3 = rng_u64();
    uint64_t x4 = rng_u64();
    uint64_t acc = seed;
    acc += (x1 + 1);          /* x1第1次 */
    acc += (x4 + 1);          /* x4第1次 */
    acc ^= (x2 ^ x3);         /* x2第1次, x3第1次 */
    acc += (x1 * x2);         /* x1第2次, x2第2次 */
    acc ^= (x3 << 4);         /* x3第2次 */
    acc += (x4 >> 3);         /* x4第2次 */
    acc ^= (x1 & x3);         /* x1第3次, x3第3次 */
    return acc;
}

static uint64_t toggle_rate(uint64_t acc) {
    uint64_t a = rng_u64();
    uint64_t b = rng_u64();
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
    double d0 = 1.0;
    union { uint64_t u; double d; } sn;
    sn.u = 1;
    double d1 = sn.d;
    double r = d0 + d1;
    r *= d1;
    union { uint64_t u; double d; } inf;
    inf.u = 0x7FF0000000000000ULL;
    double di = inf.d;
    r += (di + d1);
    return r + (double)acc;
}

static uint64_t lsu_cross(uint64_t acc) {
    static uint8_t buf[256] __attribute__((aligned(64)));
    uint64_t v0 = rng_u64();
    uint64_t v1 = rng_u64();
    uint64_t *p14 = (uint64_t *)(buf + 14);
    *p14 = v0;
    acc ^= *p14;
    uint64_t *p60 = (uint64_t *)(buf + 60);
    *p60 = v1;
    acc ^= *p60;
    acc += v0;
    acc ^= v1;
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
