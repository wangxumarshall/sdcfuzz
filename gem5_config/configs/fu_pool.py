# Custom Functional Unit pool modelling TaiShan v110 (Kunpeng 920)
# execution resources.
#
# Target layout (per the smoke-test spec):
#   - Integer ALU x3 (general) + 1 multi-cycle dedicated for mul/div
#   - FPU / SIMD x2 ports, FP32 FMA latency 5 cycles
#   - AGU x2 (MemRead / MemWrite)
#
# gem5 models FU "ports" via FUDesc.count and per-opclass latencies via
# OpDesc(opLat=...). The default latencies in FuncUnitConfig.py are tuned
# for a generic O3; we override the FMA-class latencies to 5 here.

from m5.objects.FuncUnit import FUDesc, OpDesc
from m5.objects.FUPool import FUPool


class TaiShanFUPool(FUPool):
    FUList = [
        # Integer ALU x3 (general single-cycle).
        FUDesc(
            opList=[OpDesc(opClass="IntAlu")],
            count=3,
        ),
        # Integer mul/div x1, multi-cycle, not pipelined for divide.
        FUDesc(
            opList=[
                OpDesc(opClass="IntMult", opLat=3),
                OpDesc(opClass="IntDiv", opLat=20, pipelined=False),
            ],
            count=1,
        ),
        # FPU x2: FP add/cmp/cvt etc., with FP32 FMA (FloatMultAcc) latency 5.
        FUDesc(
            opList=[
                OpDesc(opClass="FloatAdd", opLat=2),
                OpDesc(opClass="FloatCmp", opLat=2),
                OpDesc(opClass="FloatCvt", opLat=2),
                OpDesc(opClass="FloatMult", opLat=4),
                OpDesc(opClass="FloatMultAcc", opLat=5),   # FP32 FMA = 5 cyc
                OpDesc(opClass="FloatMisc", opLat=3),
                OpDesc(opClass="FloatDiv", opLat=12, pipelined=False),
                OpDesc(opClass="FloatSqrt", opLat=24, pipelined=False),
            ],
            count=2,
        ),
        # SIMD / NEON x2 (NEON is 128-bit; SVE is NOT configured per spec).
        FUDesc(
            opList=[
                OpDesc(opClass="SimdAdd"),
                OpDesc(opClass="SimdAddAcc"),
                OpDesc(opClass="SimdAlu"),
                OpDesc(opClass="SimdCmp"),
                OpDesc(opClass="SimdCvt"),
                OpDesc(opClass="SimdMisc"),
                OpDesc(opClass="SimdMult"),
                OpDesc(opClass="SimdMultAcc"),
                OpDesc(opClass="SimdShift"),
                OpDesc(opClass="SimdShiftAcc"),
                OpDesc(opClass="SimdFloatAdd"),
                OpDesc(opClass="SimdFloatMultAcc", opLat=5),  # NEON FMA = 5
            ],
            count=2,
        ),
        # AGU x2 for MemRead (effective address calc / load AGU).
        FUDesc(
            opList=[OpDesc(opClass="MemRead")],
            count=2,
        ),
        # AGU x2 for MemWrite (store AGU).
        FUDesc(
            opList=[OpDesc(opClass="MemWrite")],
            count=2,
        ),
        # One system unit for barriers/membar etc.
        FUDesc(
            opList=[OpDesc(opClass="System")],
            count=1,
        ),
    ]
