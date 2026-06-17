# Supply-Chain-Simulation-Problem
Supply chain simulations by Python


What do want to do:
- real time simulation of products flows through different processing units and storage tanks/buffer tanks
- target 1 = optimisation of tank requirements throughout processing steps
- target 2 = visualisation of product flows to show management

Tank storage
------------
Tank 0 = raw materials tank (EMM)
Tank 1 = crude product tank (EMM)
Tank 2 = distilled product tank (EMM)
Tank 3 = distilled product tank (ERT)
Tank 4  = cold fractionated product tank (ERT)
Tank 5 = fractionated distillation tank (ERT)

Simpy
-----
simpy.environment = time-engine via env.now
simpy.process (interactions)
simpy.Container = declaration of resources via .get() and .put()

Simpy interaction
--------------------
┌────────────────────────┐         1. Checks Levels          ┌──────────────────────┐
│   ProductionProcess    │ ────────────────────────────────► │     StorageTank      │
│  (Custom Flow Object)  │ ◄──────────────────────────────── │ (Layer 2 Asset Node) │
└────────────────────────┘          2. Returns True          └──────────────────────┘
            │
            │ 3. Yields a Event Request
            │    (e.g., env.timeout(1.0) or container.get())
            ▼
┌────────────────────────┐
│   simpy.Environment    │ ──► 4. Advances clock (env.now)
│  (Layer 1 Core Engine) │ ──► 5. Wakes up ProductionProcess when event triggers
└────────────────────────┘
