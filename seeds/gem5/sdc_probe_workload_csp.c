/*
 * sdc_probe_workload_csp.c — C组 (CSP定向配对操作数) gem5工作负载
 *
 * A/B/C 对比: A=operand-dict朴素(全1+1等,被掩蔽3.9%), B=随机(8.0%),
 *   C=CSP定向配对(全1+全1等,减掩蔽,目标 > B)。
 * C 与 A/B 结构完全相同(同函数/同ITERS/同指令拓扑), 唯一差异: 操作数用CSP配对
 *   - carry_chain: x1=全1, x2=全1 (配对→0xFFFF...E+C非零结果, vs A的全1+1=0易掩蔽)
 *   - toggle: a=0x5555, b=0xAAAA (同A, 但配对减法路径激活不同)
 *   - fsu: subnormal+Inf配对 (vs A的subnormal+0)
 *   - lsu: byte_alt+全1配对 (vs A的byte_alt+全1, 同)
 * 减掩蔽核心: 每个操作数对产生非零/非确定性结果, bit-flip命中后更易observable diverge。
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_csp sdc_probe_workload_csp.c
 */
#include <stdio.h>
#include <stdint.h>
#define ITERS 200

static uint64_t carry_chain(uint64_t seed) {
    /* CSP配对: 全1+全1 → 0xFFFFFFFFFFFFFFFE + C (非零结果, 减掩蔽) */
    volatile uint64_t x1 = 0xFFFFFFFFFFFFFFFFu;
    volatile uint64_t x2 = 0xFFFFFFFFFFFFFFFFu;
    uint64_t acc = seed;
    acc += (x1 + x2);          /* 全进位链+非零结果 */
    acc += (x1 * x2);          /* 乘法器最长延迟 */
    return acc;
}

static uint64_t toggle_rate(uint64_t acc) {
    /* CSP配对: 0x5555+0xAAAA → 全1 (全翻转+非零结果) */
    volatile uint64_t a = 0x5555555555555555u;
    volatile uint64_t b = 0xAAAAAAAAAAAAAAAAu;
    acc += (a + b);           /* 全翻转→全1 */
    acc ^= (a ^ b);           /* XOR→全1 */
    acc &= (a & b);           /* AND→全0 */
    acc |= (a | b);           /* OR→全1 */
    acc -= (b - a);           /* 减法→0x5555555555555555 */
    return acc;
}

static double fsu_subnormal(uint64_t acc) {
    volatile double d0 = 1.0;       /* 正常数(非0), 减掩蔽 */
    union { uint64_t u; double d; } sn;
    sn.u = 1;                        /* subnormal */
    volatile double d1 = sn.d;
    volatile double r = d0 + d1;     /* 正常+subnormal→FSU慢路径 */
    r *= d1;
    union { uint64_t u; double d; } inf;
    inf.u = 0x7FF0000000000000ULL;  /* +Inf */
    volatile double di = inf.d;
    r += (di + d1);                 /* Inf+subnormal→特殊路径 */
    return r + (double)acc;
}

static uint64_t lsu_cross(uint64_t acc) {
    static volatile uint8_t buf[256] __attribute__((aligned(64)));
    volatile uint64_t v0 = 0x00FF00FF00FF00FFu;
    volatile uint64_t v1 = 0xFFFFFFFFFFFFFFFFu;
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
