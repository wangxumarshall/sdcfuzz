/*
 * sdc_probe_workload.c — gem5-fi 工作负载, 融合 silifuzz SDC 检测用例核心
 *
 * 把 silifuzz 的微架构定向压力模板 (e1 进位链 / e3 翻转率 / f1 subnormal /
 * v4 LSU 往返) 包装成静态 ELF, 供 gem5 TaiShan V110 模型做单 bit 翻转故障注入。
 * 输出 SUM=...CRC=..., 与 golden 比对判断 diverge (SDC 检出)。
 *
 * 设计: 循环重复执行检测用例核心, 让 gem5 在 ROI 内注入的 bit 翻转
 * 有概率落到关键进位链/翻转/前递路径上, 激发可观测的输出差异。
 *
 * Build (host aarch64, native, static for gem5 SE):
 *   gcc -static -O2 -o sdc_probe_workload sdc_probe_workload.c
 *   (注: -O2 可能把核心内联, 用 volatile 防止死代码消除)
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define ITERS 200   // 循环次数 (增大指令数, 让注入更可能命中关键路径; gem5 仍能在 ~60s 内跑完)

/* ---- e1: 加法器最长进位链 (全1 + 1, 64/48/32 位边界) ---- */
static uint64_t carry_chain(uint64_t seed) {
    volatile uint64_t x1 = 0xFFFFFFFFFFFFFFFFu;   // 全 1
    volatile uint64_t x2 = 0x5555555555555555u;    // 交替 01
    volatile uint64_t x3 = 0xAAAAAAAAAAAAAAAAu;    // 交替 10
    volatile uint64_t x4 = 0x00000000FFFFFFFFu;    // 32 位进位边界
    uint64_t acc = seed;
    acc += (x1 + 1);          // 64 位全进位链 → 0, C=1
    acc += (x4 + 1);          // 32 位进位边界 → 0x100000000
    acc ^= (x2 ^ x3);         // 全翻转
    acc += (x1 * x2);         // 乘法器最长延迟路径 (Complex 端口)
    return acc;
}

/* ---- e3: 高翻转率交替操作数 (100% bit-toggle, HCI/NBTI 老化激发) ---- */
static uint64_t toggle_rate(uint64_t acc) {
    volatile uint64_t a = 0x5555555555555555u;
    volatile uint64_t b = 0xAAAAAAAAAAAAAAAAu;
    acc += (a + b);           // 全翻转
    acc ^= (a ^ b);           // XOR 全1
    acc &= (a & b);           // AND 全0
    acc |= (a | b);           // OR 全1
    acc -= (b - a);           // 减法路径全翻转
    return acc;
}

/* ---- f1: FSU subnormal/NaN 慢路径 (走微码, 覆盖盲区) ---- */
static double fsu_subnormal(uint64_t acc) {
    volatile double d0 = 0.0;
    /* 构造最小正 subnormal: 0x0000000000000001 */
    union { uint64_t u; double d; } sn;
    sn.u = 1;
    volatile double d1 = sn.d;     // subnormal
    volatile double r = d0 + d1;  // 0 + subnormal → FSU 慢路径
    r *= d1;                       // subnormal² → 下溢
    union { uint64_t u; double d; } nan;
    nan.u = 0x7FF8000000000000ULL;
    volatile double dn = nan.d;    // Quiet NaN
    r += (dn + d1);                // NaN 传播
    return r + (double)acc;
}

/* ---- v4: LSU 跨边界 store→load 往返 (split-access + 前递) ---- */
static uint64_t lsu_cross(uint64_t acc) {
    /* 静态缓冲区, 跨 16B 边界访问 */
    static volatile uint8_t buf[256] __attribute__((aligned(64)));
    volatile uint64_t v0 = 0x00FF00FF00FF00FFu;
    volatile uint64_t v1 = 0xFFFFFFFFFFFFFFFFu;
    /* base+14 跨 16B 边界 store→load 往返 */
    volatile uint64_t *p14 = (volatile uint64_t *)(buf + 14);
    *p14 = v0;       /* 跨边界 store */
    acc ^= *p14;     /* 跨边界 load (前递) — 应=v0 */
    volatile uint64_t *p60 = (volatile uint64_t *)(buf + 60);
    *p60 = v1;       /* 跨 64B line */
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
        /* 把 FSU 结果混入 (强转整数, 保留 bit 模式) */
        union { double d; uint64_t u; } cvt;
        cvt.d = f;
        sum += s ^ cvt.u ^ (uint64_t)(i + 1);
        /* LCG 推进 state, 制造不同操作数组合 */
        state = state * 1103515245u + 12345u;
    }
    /* CRC32 of sum (确定性输出, 供 golden 比对) */
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
