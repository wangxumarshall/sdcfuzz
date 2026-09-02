/*
 * sdc_probe_workload_d8.c — D8组 (volatile混合: bit+struct双赢) gem5工作负载
 *
 * 核心策略(D6+D7互补):
 *   D7(去volatile): bit=6.4%最高(寄存器保持) 但struct=0%(无forwarding)
 *   D6(volatile):   struct=9.6%最高(forwarding) 但bit=5.8%(stack存)
 *
 * D8混合:
 *   carry_chain: 去volatile → 操作数在寄存器 → bit-flip高ACE
 *   toggle_rate: 去volatile → 同上
 *   lsu_cross: 保留volatile → store→load forwarding → struct高ACE
 *   → bit-flip: carry/toggle贡献高ACE + lsu中等
 *   → struct: lsu贡献forwarding + carry/toggle无(但占比小)
 *
 * 同时: 操作数多次引用(D6策略) + 多路径(位移/AND/OR)
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_d8 sdc_probe_workload_d8.c
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

/* carry_chain: 去volatile → 寄存器保持 → bit-flip高ACE */
static uint64_t carry_chain(uint64_t seed) {
    uint64_t x1 = rng_u64();
    uint64_t x2 = rng_u64();
    uint64_t x3 = rng_u64();
    uint64_t x4 = rng_u64();
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

/* toggle_rate: 去volatile → 寄存器保持 */
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

/* lsu_cross: 保留volatile → store→load forwarding → struct高ACE */
static uint64_t lsu_cross(uint64_t acc) {
    static volatile uint8_t buf[256] __attribute__((aligned(64)));
    volatile uint64_t v0 = rng_u64();
    volatile uint64_t v1 = rng_u64();
    volatile uint64_t *p14 = (volatile uint64_t *)(buf + 14);
    *p14 = v0;               /* store (volatile→stack) */
    acc ^= *p14;             /* load (forwarding path) */
    volatile uint64_t *p60 = (volatile uint64_t *)(buf + 60);
    *p60 = v1;               /* store */
    acc ^= *p60;             /* load */
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
