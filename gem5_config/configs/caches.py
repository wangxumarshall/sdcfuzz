# Caches for the TaiShan v110 (Kunpeng 920) smoke-test config.
# Old-style configs (subclass gem5's `Cache`), chosen because it composes
# naturally with CHAOS's `system.CHAOSReg = CHAOSReg(cpu=system.cpu, ...)`
# mounting style. The new gem5.components library wraps the system in a
# Board abstraction that would need adapter code to expose the CPU pointer
# the same way; old-style avoids that friction.

from m5.objects import Cache


class L1Cache(Cache):
    """Common L1 defaults."""
    assoc = 4
    tag_latency = 1
    data_latency = 1
    response_latency = 1
    mshrs = 4
    tgts_per_mshr = 20

    def connectBus(self, bus):
        self.mem_side = bus.cpu_side_ports

    def connectCPU(self, cpu):
        raise NotImplementedError


class L1ICache(L1Cache):
    # L1I 64 KiB, 4-way. Instruction fetch is read-only; use the same
    # simple latency model as L1D minus the load-to-use consideration.
    size = "64KiB"
    assoc = 4
    tag_latency = 2
    data_latency = 2
    response_latency = 2

    def connectCPU(self, cpu):
        self.cpu_side = cpu.icache_port


class L1DCache(L1Cache):
    # L1D 64 KiB, 4-way. Hit load-to-use latency target = 4 cycles.
    # In gem5's classic cache the load-to-use latency is approximated by
    # tag_latency + data_latency + response_latency, so set each to 1
    # to land close to the 4-cycle load-to-use budget (1+1+1 = 3 tag/data/
    # response plus the inherent access = ~4 cycles effective). Tuned to
    # keep it simple; revisit if precise load-to-use is needed.
    size = "64KiB"
    assoc = 4
    tag_latency = 1
    data_latency = 1
    response_latency = 1

    def connectCPU(self, cpu):
        self.cpu_side = cpu.dcache_port


class L2Cache(Cache):
    # L2 512 KiB private, 8-way.
    size = "512KiB"
    assoc = 8
    tag_latency = 8
    data_latency = 8
    response_latency = 8
    mshrs = 20
    tgts_per_mshr = 12

    def connectCPUSideBus(self, bus):
        self.cpu_side = bus.mem_side_ports

    def connectMemSideBus(self, bus):
        self.mem_side = bus.cpu_side_ports
