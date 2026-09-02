/*
 * sdc_probe_workload_random.c — A/B 对照工作负载 (B组: 操作数随机, 非operand-dict定向)
 *
 * A/B 实验对照: 与 sdc_probe_workload.c (A组, operand-dict定向极端操作数) 对比。
 * 本工作负载保持与A组完全相同的函数骨架/循环结构/指令拓扑(ITERS=200,
 * carry_chain/toggle_rate/fsu_subnormal/lsu_cross四模块), 唯一差异是:
 *   - A组: 操作数用 operand_dict 极端值 (0xFFFF/0x5555/0xAAAA/subnormal/NaN)
 *   - B组: 操作数用LCG随机值 (无定向, 无极端值字典)
 * 这样 gem5-fi 同等注入下 diverge 率差异可归因于"操作数是否 operand-dict 定向"。
 *
 * Build (host aarch64, static for gem5 SE):
 *   gcc -static -O2 -o sdc_probe_workload_random sdc_probe_workload_random.c
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define ITERS 200   // 与 A 组相同

static uint32_t rng_state = 0xDEADBEEFu;
static uint64_t rng_u64(void) {
    /* LCG 随机 64-bit (无定向, 无极端值) */
    rng_state = rng_state * 1103515245u + 12345u;
    uint64_t lo = rng_state;
    rng_state = rng_state * 1103515245u + 12345u;
    uint64_t hi = rng_state;
    return (hi << 32) | lo;
}

/* ---- 对照 carry_chain: 随机操作数 (非全1/交替/进位边界) ---- */
static uint64_t carry_chain(uint64_t seed) {
    volatile uint64_t x1 = rng_u64();   // 随机, 非全1
    volatile uint64_t x2 = rng_u64();   // 随机, 非交替01
    volatile uint64_t x3 = rng_u64();   // 随机, 非交替10
    volatile uint64_t x4 = rng_u64();   // 随机, 非进位边界
    uint64_t acc = seed;
    acc += (x1 + 1);
    acc += (x4 + 1);
    acc ^= (x2 ^ x3);
    acc += (x1 * x2);
    return acc;
}

/* ---- 对照 toggle_rate: 随机操作数 (非0x5555/0xAAAA) ---- */
static uint64_t toggle_rate(uint64_t acc) {
    volatile uint64_t a = rng_u64();
    volatile uint64_t b = rng_u64();
    acc += (a + b);
    acc ^= (a ^ b);
    acc &= (a & b);
    acc |= (a | b);
    acc -= (b - a);
    return acc;
}

/* ---- 对照 fsu: 正常浮点 (非subnormal/NaN/Inf) ---- */
static double fsu_subnormal(uint64_t acc) {
    volatile double d0 = 1.0;           // 正常数, 非0/subnormal
    /* 随机构造正常 double (非subnormal/NaN/Inf): 指数在 [0x3FF, 0x7FE] */
    union { uint64_t u; double d; } sn;
    sn.u = 0x3FF0000000000000ULL | (rng_u64() & 0x000FFFFFFFFFFFFFULL);
    volatile double d1 = sn.d;          // 正常 double
    volatile double r = d0 + d1;
    r *= d1;
    union { uint64_t u; double d; } normal;
    normal.u = 0x4000000000000000ULL | (rng_u64() & 0x000FFFFFFFFFFFFFULL);
    volatile double dn = normal.d;      // 正常 double, 非NaN
    r += (dn + d1);
    return r + (double)acc;
}

/* ---- 对照 lsu_cross: 随机写入值 (非0x00FF交替/全1) ---- */
static uint64_t lsu_cross(uint64_t acc) {
    static volatile uint8_t buf[256] __attribute__((aligned(64)));
    volatile uint64_t v0 = rng_u64();   // 随机, 非字节交替
    volatile uint64_t v1 = rng_u64();   // 随机, 非全1
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
