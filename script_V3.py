"""
Supply Chain Discrete Event Simulation Engine (Enhanced Telemetry Log)
Architecture: Object-Oriented, Node-Based Network Flow Architecture
"""

import simpy
import pandas as pd

# ==============================================================================
# LAYER 2: THE PHYSICAL NODE LAYER (Assets)
# ==============================================================================

class StorageTank:
    def __init__(self, env, name, capacity_m3, density, init_fill_pct=0.0):
        self.env = env
        self.name = name
        self.density = density
        self.max_tons = capacity_m3 * 0.95 * density
        self.container = simpy.Container(env, capacity=self.max_tons, init=self.max_tons * init_fill_pct)
        
    @property
    def level(self):
        return self.container.level
    
    @property
    def free_space(self):
        return self.container.capacity - self.container.level


# ==============================================================================
# LAYER 3: THE EDGE LAYER (Flows, Transformation & Metrics Tracking)
# ==============================================================================

class ProductionProcess:
    def __init__(self, env, name, source_node, dest_node, flow_rate, process_yield, active_by_default=True):
        self.env = env
        self.name = name
        self.source = source_node
        self.dest = dest_node
        self.flow_rate = flow_rate  
        self.process_yield = process_yield
        self.is_running = active_by_default
        
        # Metrics fields
        self.status = "Idle"                
        self.total_consumed_tons = 0.0      
        self.total_produced_tons = 0.0      
        
        self.process_loop = self.env.process(self._run())

    def _run(self):
        while True:
            if self.is_running:
                consumed = self.flow_rate
                produced = consumed * self.process_yield
                
                # Check for Starvation (Source empty)
                if self.source.level < consumed:
                    self.status = "Starved"
                    yield self.env.timeout(0.5)
                    continue
                    
                # Check for Blockage (Destination full)
                if self.dest.free_space < produced:
                    self.status = "Blocked"
                    yield self.env.timeout(0.5)
                    continue
                
                # Execution State
                self.status = "Running"
                # FIXED: Changed self.env.source to self.source
                yield self.source.container.get(consumed)
                yield self.dest.container.put(produced)
                
                # Update Telemetry Counters
                self.total_consumed_tons += consumed
                self.total_produced_tons += produced
            else:
                self.status = "Suspended"
                yield self.env.timeout(1.0)
                continue
                
            yield self.env.timeout(1.0)


class TransportLink:
    def __init__(self, env, name, source_node, dest_node, batch_size, transit_hours):
        self.env = env
        self.name = name
        self.source = source_node
        self.dest = dest_node
        self.batch_size = batch_size
        self.transit_hours = transit_hours
        
        # NEW METRICS FIELDS
        self.active_trucks_in_transit = 0
        self.total_trucks_dispatched = 0
        self.total_tons_transported = 0
        
        self.env.process(self._run())

    def _run(self):
        while True:
            if self.source.level >= self.batch_size:
                yield self.source.container.get(self.batch_size)
                
                # Update dispatched metrics
                self.active_trucks_in_transit += 1
                self.total_trucks_dispatched += 1
                self.total_tons_transported += self.batch_size
                
                self.env.process(self._transit_routine())
            yield self.env.timeout(1.0)

    def _transit_routine(self):
        yield self.env.timeout(self.transit_hours)
        while self.dest.free_space < self.batch_size:
            yield self.env.timeout(0.5)
        yield self.dest.container.put(self.batch_size)
        
        # Truck arrived, remove from transit count
        self.active_trucks_in_transit -= 1


# ==============================================================================
# LAYER 4: THE CONTROL LAYER (Campaign Controllers)
# ==============================================================================

class CampaignController:
    def __init__(self, env, trigger_node, controlled_processes):
        self.env = env
        self.trigger_node = trigger_node
        self.processes = controlled_processes
        self.env.process(self._monitor_loop())

    def _monitor_loop(self):
        while True:
            trigger_threshold = self.trigger_node.container.capacity * 0.80
            if self.trigger_node.level >= trigger_threshold:
                for proc in self.processes:
                    proc.is_running = True
            
            if self.trigger_node.level <= 1.0:
                for proc in self.processes:
                    proc.is_running = False
                    
            yield self.env.timeout(1.0)


class DownstreamDistillationController:
    def __init__(self, env, trigger_node, controlled_processes):
        self.env = env
        self.trigger_node = trigger_node
        self.processes = controlled_processes
        self.env.process(self._monitor_loop())

    def _monitor_loop(self):
        while True:
            if self.trigger_node.free_space <= 15.0:
                for proc in self.processes:
                    proc.is_running = True
            
            if self.trigger_node.level <= 1.0:
                for proc in self.processes:
                    proc.is_running = False
                    
            yield self.env.timeout(1.0)


# ==============================================================================
# LAYER 5: ENHANCED TELEMETRY ENGINE (Comprehensive System Logging)
# ==============================================================================

class TelemetryEngine:
    """Ousts state variables, process parameters, and logistics metrics simultaneously."""
    def __init__(self, env, nodes_network, processes_list, logistics_list):
        self.env = env
        self.network = nodes_network
        self.processes = processes_list
        self.logistics = logistics_list
        self.logs = []
        self.env.process(self._record_states())

    def _record_states(self):
        while True:
            # Base timestamp tracking
            state = {'Timestamp_Hours': self.env.now}
            
            # 1. Harvest Tank States (Nodes)
            for key, node in self.network.items():
                state[f'Asset_{key}_Level_Tons'] = round(node.level, 2)
                state[f'Asset_{key}_FreeSpace_Tons'] = round(node.free_space, 2)
            
            # 2. Harvest Plant Process States (Edges)
            for proc in self.processes:
                state[f'Process_{proc.name}_Status'] = proc.status
                state[f'Process_{proc.name}_CumProduced_Tons'] = round(proc.total_produced_tons, 2)
            
            # 3. Harvest Transport States (Logistics Pipelines)
            for link in self.logistics:
                state[f'Logistics_{link.name}_ActiveTrucks'] = link.active_trucks_in_transit
                state[f'Logistics_{link.name}_TotalDispatchedCount'] = link.total_trucks_dispatched
                state[f'Logistics_{link.name}_TotalTransported_Tons'] = link.total_tons_transported
                
            self.logs.append(state)
            yield self.env.timeout(1.0)

    def export_to_csv(self, file_path):
        df = pd.DataFrame(self.logs)
        df.to_csv(file_path, index=False)


# ==============================================================================
# LAYER 6: THE CONFIGURATION LAYER (Execution Environment)
# ==============================================================================

if __name__ == "__main__":
    env = simpy.Environment()
    
    network_nodes = {
        'Tank0_RawProduct': StorageTank(env, 'Emmerich_RawProduct', capacity_m3=250, density=0.9, init_fill_pct=0.9),
        'Tank1_CrudeIso':   StorageTank(env, 'Emmerich_Crude', capacity_m3=180, density=0.9, init_fill_pct=0.0), 
        'Tank2_Monomer_Em': StorageTank(env, 'Emmerich_Monomer', capacity_m3=60, density=0.9, init_fill_pct=0.0),
        'Tank3_Monomer_Ert':StorageTank(env, 'Ertvelde_Monomer', capacity_m3=360, density=0.9, init_fill_pct=0.0),
        'Tank4_ColdFrac':   StorageTank(env, 'Ertvelde_ColdFrac', capacity_m3=290, density=0.9, init_fill_pct=0.0),
        'Tank6_Purified':   StorageTank(env, 'Ertvelde_Purified', capacity_m3=280, density=0.9, init_fill_pct=0.0)
    }
    
    class RawMaterialSupplier:
        def __init__(self, env, dest_node, rate):
            self.env, self.dest, self.rate = env, dest_node, rate
            self.env.process(self._run())
        def _run(self):
            while True:
                if self.dest.free_space >= self.rate:
                    yield self.dest.container.put(self.rate)
                yield self.env.timeout(1.0)

    RawMaterialSupplier(env, network_nodes['Tank0_RawProduct'], rate=4.0)
    
    # Initialize process objects so we can group them for the telemetry tracker
    proc_reactor = ProductionProcess(
        env, name='Upstream_Reactor', source_node=network_nodes['Tank0_RawProduct'], 
        dest_node=network_nodes['Tank1_CrudeIso'], flow_rate=3.5, process_yield=0.90
    )
    
    proc_em_dist = ProductionProcess(
        env, name='Monomer_Distillation', source_node=network_nodes['Tank1_CrudeIso'], 
        dest_node=network_nodes['Tank2_Monomer_Em'], flow_rate=2.5, process_yield=0.86
    )
    
    logistics_road = TransportLink(
        env, name='Emmerich_To_Ertvelde_Road', source_node=network_nodes['Tank2_Monomer_Em'], 
        dest_node=network_nodes['Tank3_Monomer_Ert'], batch_size=24, transit_hours=3
    )
    
    proc_ert_camp = ProductionProcess(
        env, name='Ertvelde_Campaign_Block', source_node=network_nodes['Tank3_Monomer_Ert'], 
        dest_node=network_nodes['Tank4_ColdFrac'], flow_rate=2.5, process_yield=(0.99 * 0.743), active_by_default=False
    )
    
    proc_ert_frac = ProductionProcess(
        env, name='Fractionated_Distillation', source_node=network_nodes['Tank4_ColdFrac'], 
        dest_node=network_nodes['Tank6_Purified'], flow_rate=13.0, process_yield=0.96, active_by_default=False
    )
    
    # Controllers
    CampaignController(env, trigger_node=network_nodes['Tank3_Monomer_Ert'], controlled_processes=[proc_ert_camp])
    DownstreamDistillationController(env, trigger_node=network_nodes['Tank4_ColdFrac'], controlled_processes=[proc_ert_frac])
    
    # Compile lists of objects for Enhanced Logging Engine
    all_production_lines = [proc_reactor, proc_em_dist, proc_ert_camp, proc_ert_frac]
    all_logistics_links = [logistics_road]
    
    # Bind Enhanced Engine
    telemetry = TelemetryEngine(env, network_nodes, all_production_lines, all_logistics_links)
    
    print("==========================================================")
    print("Running Simulation Engine with Enhanced Logging Columns...")
    print("==========================================================")
    
    env.run(until=2160) 
    telemetry.export_to_csv('enhanced_supply_chain_logbook.csv')
    
    print("\nSimulation completed successfully.")
    print("Comprehensive dataset exported to 'enhanced_supply_chain_logbook.csv'.")
    print(f"Final Product Level: {network_nodes['Tank6_Purified'].level:.2f} Tons.")
    print("==========================================================")