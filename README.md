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
