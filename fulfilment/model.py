"""Finite arrival window followed by draining every accepted order to collection."""
from dataclasses import dataclass, asdict
import math
import random
import statistics
import simpy


@dataclass(frozen=True)
class Config:
    pickers: int = 3
    packers: int = 2
    arrival_rate: float = 0.8
    pick_mean: float = 3.0
    pack_mean: float = 2.0
    express_share: float = 0.25
    courier_interval: float = 20.0
    warmup: float = 1000.0
    horizon: float = 6000.0
    express_priority: bool = True

    def __post_init__(self):
        for name in ["pickers", "packers"]:
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ["arrival_rate", "pick_mean", "pack_mean", "courier_interval", "horizon"]:
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not math.isfinite(self.warmup) or not 0 <= self.warmup < self.horizon:
            raise ValueError("warmup must be nonnegative and less than horizon")
        if not math.isfinite(self.express_share) or not 0 <= self.express_share <= 1:
            raise ValueError("express_share must be in [0,1]")


def overlap(start, end, window_start, window_end):
    """Duration intersecting the measurement window, including boundary crossings."""
    return max(0.0, min(end, window_end) - max(start, window_start))


def simulate(config=Config(), seed=42):
    env = simpy.Environment()
    picking = simpy.PriorityResource(env, config.pickers)
    packing = simpy.Resource(env, config.packers)
    # Independent streams avoid changing order attributes when a scenario changes service ordering.
    arrivals_rng, express_rng, pick_rng, pack_rng = [random.Random(f"{seed}:{name}")
        for name in ["arrivals", "express", "picking", "packing"]]
    orders, ready, courier_visits = [], [], []
    arrivals_closed = False
    completed = 0
    drained = env.event()

    def process(order):
        priority = 0 if config.express_priority and order["express"] else 1
        with picking.request(priority=priority) as req:
            yield req
            order["pick_start"] = env.now
            yield env.timeout(order["pick_service"])
            order["pick_end"] = env.now
        with packing.request() as req:
            yield req
            order["pack_start"] = env.now
            yield env.timeout(order["pack_service"])
            order["pack_end"] = env.now
        ready.append(order)

    def arrivals():
        nonlocal arrivals_closed
        while True:
            gap = arrivals_rng.expovariate(config.arrival_rate)
            if env.now + gap >= config.horizon:
                yield env.timeout(config.horizon-env.now)
                arrivals_closed = True
                if completed == len(orders) and not drained.triggered:
                    drained.succeed()
                return
            yield env.timeout(gap)
            order = dict(id=len(orders), arrival=env.now,
                express=express_rng.random() < config.express_share,
                pick_service=pick_rng.expovariate(1/config.pick_mean),
                pack_service=pack_rng.expovariate(1/config.pack_mean))
            orders.append(order)
            env.process(process(order))

    def courier():
        nonlocal completed
        while True:
            yield env.timeout(config.courier_interval)
            if config.warmup <= env.now < config.horizon:
                courier_visits.append(not ready)
            for order in ready:
                order["collected"] = env.now
                completed += 1
            ready.clear()
            if arrivals_closed and completed == len(orders) and not drained.triggered:
                drained.succeed()

    env.process(arrivals())
    env.process(courier())
    env.run(until=drained)
    cohort = [o for o in orders if o["arrival"] >= config.warmup]
    window = config.horizon-config.warmup
    mean = lambda values: statistics.mean(values) if values else None
    durations = [o["collected"]-o["arrival"] for o in cohort]
    waits = [o["pick_start"]-o["arrival"] for o in cohort if o["express"]]
    metrics = {
        "orders": len(cohort),
        "mean_total_time": mean(durations),
        "p95_total_time": sorted(durations)[max(0, math.ceil(.95*len(durations))-1)] if durations else None,
        "mean_processing_time": mean([o["pack_end"]-o["arrival"] for o in cohort]),
        "mean_courier_wait": mean([o["collected"]-o["pack_end"] for o in cohort]),
        "express_wait_over_6": mean([w > 6 for w in waits]),
        "picker_utilisation": sum(overlap(o["pick_start"], o["pick_end"], config.warmup, config.horizon) for o in orders)/(config.pickers*window),
        "packer_utilisation": sum(overlap(o["pack_start"], o["pack_end"], config.warmup, config.horizon) for o in orders)/(config.packers*window),
        "mean_pick_queue": sum(overlap(o["arrival"], o["pick_start"], config.warmup, config.horizon) for o in orders)/window,
        "empty_courier_fraction": mean(courier_visits),
        "completed_after_close": sum(o["collected"] >= config.horizon for o in cohort),
        "drain_duration": env.now-config.horizon,
    }
    return {"config": asdict(config), "seed": seed, "metrics": metrics, "orders": orders,
            "offered_load": {"picking": config.arrival_rate*config.pick_mean/config.pickers,
                             "packing": config.arrival_rate*config.pack_mean/config.packers}}
