/*
 * sdc_probe_workload_evolved.c — D组 (进化引擎演化操作数) gem5工作负载
 *
 * A/B/C/D对比: A=朴素operand-dict(3.9%), B=随机(8.0%), C=CSP配对(3.7%),
 *   D=进化引擎演化(目标>B, 验证进化引擎击败随机)。
 * D 与 A/B/C 结构完全相同(同函数/同ITERS/同指令拓扑), 唯一差异: 操作数用
 * 进化引擎(梯度爬山+边界放大+上下文重组)演化的高压值(T=42, 非魔术数字)。
 * 减掩蔽: 演化操作数无规律但翻转量最大 + 高熵结果(反掩蔽)。
 *
 * Build: gcc -static -O2 -o sdc_probe_workload_evolved sdc_probe_workload_evolved.c
 */
#include <stdio.h>
#include <stdint.h>
#define ITERS 200

/* 进化引擎演化操作数 (T=42, 梯度爬山40轮×20次trial取最高) */
#define D_X0 0x00D18B24C72CC66BULL
#define D_X1 0x30F25D1A06320AF2ULL
#define D_X2 0x7412C7831E1C4D98ULL

static uint64_t carry_chain(uint64_t seed) {
    volatile uint64_t x1 = D_X1;
    volatile uint64_t x2 = D_X2;
    uint64_t acc = seed;
    acc += (x1 + x2);          /* 演化操作数, 高翻转 */
    acc += (x1 * x2);          /* 乘法器 */
    return acc;
}

static uint64_t toggle_rate(uint64_t acc) {
    volatile uint64_t a = D_X0;
    volatile uint64_t b = D_X2;
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
    volatile uint64_t v0 = D_X0;
    volatile uint64_t v1 = D_X1;
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
