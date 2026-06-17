"""
Supply Chain Discrete Event Simulation Engine
Architecture: Object-Oriented, Node-Based Network Flow Architecture
Framework: SimPy, Pandas

This script simulates a multi-site chemical manufacturing and logistics pipeline 
stretching between Emmerich and Ertvelde.
"""

import simpy
import pandas as pd


# ==============================================================================
# LAYER 2: THE PHYSICAL NODE LAYER (Assets)
# ==============================================================================

class StorageTank:
    """Encapsulates a physical storage unit with custom safety volumes and density rules."""
    def __init__(self, env, name, capacity_m3, density, init_fill_pct=0.0):
        self.env = env
        self.name = name
        self.density = density
        
        # Calculate maximum allowed tons based on a 95% working volume safety limit
        self.max_tons = capacity_m3 * 0.95 * density
        self.container = simpy.Container(env, capacity=self.max_tons, init=self.max_tons * init_fill_pct)
        
    @property
    def level(self):
        """Returns the current mass level in tons."""
        return self.container.level
    
    @property
    def free_space(self):
        """Returns the available mass capacity remaining in tons."""
        return self.container.capacity - self.container.level


# ==============================================================================
# LAYER 3: THE EDGE LAYER (Flows & Transformation)
# ==============================================================================

class ProductionProcess:
    """A continuous transformation unit that pumps material from a source node to a destination node."""
    def __init__(self, env, name, source_node, dest_node, flow_rate, process_yield, active_by_default=True):
        self.env = env
        self.name = name
        self.source = source_node
        self.dest = dest_node
        self.flow_rate = flow_rate
        self.process_yield = process_yield
        self.is_running = active_by_default
        
        # Self-registering process execution loop inside the SimPy environment
        self.process_loop = self.env.process(self._run())

    def _run(self):
        while True:
            if self.is_running:
                consumed = self.flow_rate
                produced = consumed * self.process_yield
                
                # Guard Condition: Check source asset availability and destination volume clearance
                if self.source.level >= consumed and self.dest.free_space >= produced:
                    yield self.source.container.get(consumed)
                    yield self.dest.container.put(produced)
                else:
                    # Starved or Blocked state: Force a minor time-step advance to avoid zero-time CPU deadlocks
                    yield self.env.timeout(0.5)
                    continue
            else:
                # Manufacturing process is explicitly suspended: Idle for a standard interval step
                yield self.env.timeout(1.0)
                continue
                
            yield self.env.timeout(1.0) # Standard operational step iteration (1 Hour)


class TransportLink:
    """Handles discrete batch logistics transfers (e.g., road trucks) between separate nodes."""
    def __init__(self, env, name, source_node, dest_node, batch_size, transit_hours):
        self.env = env
        self.name = name
        self.source = source_node
        self.dest = dest_node
        self.batch_size = batch_size
        self.transit_hours = transit_hours
        
        # Self-registering monitoring loop
        self.env.process(self._run())

    def _run(self):
        truck_id = 1
        while True:
            if self.source.level >= self.batch_size:
                # Subtract batch payload immediately from source storage (loading the truck)
                yield self.source.container.get(self.batch_size)
                
                # Spawn an independent asynchronous transit routine so the main loop can track subsequent trucks
                self.env.process(self._transit_routine(truck_id))
                truck_id += 1
            yield self.env.timeout(1.0)

    def _transit_routine(self, truck_id):
        # Simulation of time spent in transit over the road network
        yield self.env.timeout(self.transit_hours)
        
        # Demurrage / Gate holding loop: Hold truck outside plant gate if destination storage cannot accept payload
        while self.dest.free_space < self.batch_size:
            yield self.env.timeout(0.5)
            
        yield self.dest.container.put(self.batch_size)


# ==============================================================================
# LAYER 4: THE CONTROL LAYER (Business Logic & Orchestration)
# ==============================================================================

class CampaignController:
    """Orchestrates and triggers manufacturing campaigns based on asset threshold conditions."""
    def __init__(self, env, trigger_node, controlled_processes):
        self.env = env
        self.trigger_node = trigger_node
        self.processes = controlled_processes # Dynamic list of production process objects
        
        # Self-registering control loop
        self.env.process(self._monitor_loop())

    def _monitor_loop(self):
        while True:
            # Campaign Trigger Criteria: Activate lines when monomer inventory is nearly full (<= 5 tons space left)
            if self.trigger_node.free_space <= 5.0:
                for proc in self.processes:
                    proc.is_running = True
            
            # Campaign Suspension Criteria: Shut down processing streams when monomer asset is fully drained
            if self.trigger_node.level <= 0.1:
                for proc in self.processes:
                    proc.is_running = False
                    
            yield self.env.timeout(1.0)


# ==============================================================================
# LAYER 5: THE OBSERVER LAYER (Telemetry Engine)
# ==============================================================================

class TelemetryEngine:
    """Passive global logging engine running metrics collection loops at steady time intervals."""
    def __init__(self, env, nodes_network):
        self.env = env
        self.network = nodes_network # Network assets dictionary mapped for observation
        self.logs = []
        
        # Self-registering data recording loop
        self.env.process(self._record_states())

    def _record_states(self):
        while True:
            state = {'Timestamp_Hours': self.env.now}
            # Dynamically pull metrics across all registered assets in the map
            for key, node in self.network.items():
                state[f'{key}_Level_Tons'] = round(node.level, 2)
                state[f'{key}_Free_Space_Tons'] = round(node.free_space, 2)
            self.logs.append(state)
            yield self.env.timeout(1.0)

    def export_to_csv(self, file_path):
        """Converts accumulated historical snapshots into a structured CSV file."""
        df = pd.DataFrame(self.logs)
        df.to_csv(file_path, index=False)


# ==============================================================================
# LAYER 6: THE CONFIGURATION LAYER (Execution Environment)
# ==============================================================================

if __name__ == "__main__":
    # Instantiate core SimPy time engine
    env = simpy.Environment()
    
    # 1. Define Network Topology Assets (Nodes)
    network_nodes = {
        'Tank1_CrudeIso':   StorageTank(env, 'Emmerich_Crude', capacity_m3=180, density=0.9, init_fill_pct=0.8),
        'Tank2_Monomer_Em': StorageTank(env, 'Emmerich_Monomer', capacity_m3=60, density=0.9, init_fill_pct=0.0),
        'Tank3_Monomer_Ert':StorageTank(env, 'Ertvelde_Monomer', capacity_m3=360, density=0.9, init_fill_pct=0.0),
        'Tank4_ColdFrac':   StorageTank(env, 'Ertvelde_ColdFrac', capacity_m3=290, density=0.9, init_fill_pct=0.0),
        'Tank6_Purified':   StorageTank(env, 'Ertvelde_Purified', capacity_m3=280, density=0.9, init_fill_pct=0.0)
    }
    
    # Inject a simple continuous Supplier Process feeding the gateway node (Tank 1)
    class ConstantSupplier:
        def __init__(self, env, dest_node, rate):
            self.env, self.dest, self.rate = env, dest_node, rate
            self.env.process(self._run())
        def _run(self):
            while True:
                if self.dest.free_space >= self.rate:
                    yield self.dest.container.put(self.rate)
                yield self.env.timeout(1.0)

    ConstantSupplier(env, network_nodes['Tank1_CrudeIso'], rate=3.0)
    
    # 2. Establish Network Edge Transformations & Material Conveyors
    ProductionProcess(
        env, name='Monomer_Distillation', 
        source_node=network_nodes['Tank1_CrudeIso'], dest_node=network_nodes['Tank2_Monomer_Em'], 
        flow_rate=2.5, process_yield=0.86
    )
    
    TransportLink(
        env, name='Emmerich_To_Ertvelde_Road', 
        source_node=network_nodes['Tank2_Monomer_Em'], dest_node=network_nodes['Tank3_Monomer_Ert'], 
        batch_size=24, transit_hours=3
    )
    
    # Initialize downstream process lines to start as dormant (controlled by the scheduling loop)
    campaign_step_1 = ProductionProcess(
        env, name='Ertvelde_Campaign_Block', 
        source_node=network_nodes['Tank3_Monomer_Ert'], dest_node=network_nodes['Tank4_ColdFrac'], 
        flow_rate=2.5, process_yield=(0.99 * 0.743), active_by_default=False
    )
    
    campaign_step_2 = ProductionProcess(
        env, name='Fractionated_Distillation', 
        source_node=network_nodes['Tank4_ColdFrac'], dest_node=network_nodes['Tank6_Purified'], 
        flow_rate=13.0, process_yield=0.96, active_by_default=False
    )
    
    # 3. Attach Strategic Controller Interface
    CampaignController(
        env, trigger_node=network_nodes['Tank3_Monomer_Ert'], 
        controlled_processes=[campaign_step_1, campaign_step_2]
    )
    
    # 4. Bind Central Telemetry Monitoring Dashboard Observer
    telemetry = TelemetryEngine(env, network_nodes)
    
    # 5. Execute Simulation Core
    print("==========================================================")
    print("Initializing Modular Node-Based Simulation Run...")
    print("==========================================================")
    
    # Run the engine for 2160 hours (90 Days / 1 Quarter)
    env.run(until=2160) 
    
    # 6. Export Historical Datasets
    output_filename = 'oo_node_network_output.csv'
    telemetry.export_to_csv(output_filename)
    
    print("\nSimulation completed successfully.")
    print(f"Data exported to: '{output_filename}'")
    print(f"Final Purified Inventory Status: {network_nodes['Tank6_Purified'].level:.2f} Tons Available.")
    print("==========================================================")