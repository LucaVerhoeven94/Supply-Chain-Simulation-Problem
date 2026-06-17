import simpy
import pandas as pd
import pygame
import sys

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
        
        # Metrics fields
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


class EmmerichDistillationController:
    """Controls the Emmerich Distillation column based strictly on Tank 1 levels."""
    def __init__(self, env, trigger_node, controlled_processes):
        self.env = env
        self.trigger_node = trigger_node
        self.processes = controlled_processes
        self.env.process(self._monitor_loop())

    def _monitor_loop(self):
        while True:
            # Trigger distillation when Tank 1 is nearly full (less than 10 tons of space left)
            if self.trigger_node.free_space <= 10.0:
                for proc in self.processes:
                    proc.is_running = True
            
            # Shut down distillation when Tank 1 is drained close to empty
            if self.trigger_node.level <= 1.0:
                for proc in self.processes:
                    proc.is_running = False
                    
            yield self.env.timeout(1.0)


class RawMaterialSupplier:
    def __init__(self, env, dest_node, rate):
        self.env, self.dest, self.rate = env, dest_node, rate
        self.env.process(self._run())
    def _run(self):
        while True:
            if self.dest.free_space >= self.rate:
                yield self.dest.container.put(self.rate)
            yield self.env.timeout(1.0)


# ==============================================================================
# LAYER 5: TELEMETRY ENGINE
# ==============================================================================

class TelemetryEngine:
    def __init__(self, env, nodes_network, processes_list, logistics_list):
        self.env = env
        self.network = nodes_network
        self.processes = processes_list
        self.logistics = logistics_list
        self.logs = []
        self.env.process(self._record_states())

    def _record_states(self):
        while True:
            state = {'Timestamp_Hours': self.env.now}
            for key, node in self.network.items():
                state[f'Asset_{key}_Level_Tons'] = round(node.level, 2)
                state[f'Asset_{key}_FreeSpace_Tons'] = round(node.free_space, 2)
            for proc in self.processes:
                state[f'Process_{proc.name}_Status'] = proc.status
                state[f'Process_{proc.name}_CumProduced_Tons'] = round(proc.total_produced_tons, 2)
            for link in self.logistics:
                state[f'Logistics_{link.name}_ActiveTrucks'] = link.active_trucks_in_transit
                
            self.logs.append(state)
            yield self.env.timeout(1.0)

    def export_to_csv(self, file_path):
        df = pd.DataFrame(self.logs)
        df.to_csv(file_path, index=False)


# ==============================================================================
# LAYER 6: PYGAME VISUALIZATION INTERFACE
# ==============================================================================

def run_visual_simulation():
    # 1. SimPy Initialization
    env = simpy.Environment()
    
    network_nodes = {
        'Tank0_RawProduct': StorageTank(env, 'Raw Product', capacity_m3=250, density=0.9, init_fill_pct=0.9),
        'Tank1_CrudeIso':   StorageTank(env, 'Crude Iso', capacity_m3=180, density=0.9, init_fill_pct=0.0), 
        'Tank2_Monomer_Em': StorageTank(env, 'Monomer EM', capacity_m3=60, density=0.9, init_fill_pct=0.0),
        'Tank3_Monomer_Ert':StorageTank(env, 'Monomer ERT', capacity_m3=360, density=0.9, init_fill_pct=0.0),
        'Tank4_ColdFrac':   StorageTank(env, 'Cold Frac', capacity_m3=290, density=0.9, init_fill_pct=0.0),
        'Tank6_Purified':   StorageTank(env, 'Purified Product', capacity_m3=280, density=0.9, init_fill_pct=0.0)
    }
    
    # Heartbeat loop generator to keep SimPy synchronized with the Pygame clock tick
    def simpy_heartbeat(env):
        while True:
            yield env.timeout(1.0)
    env.process(simpy_heartbeat(env))
    
    RawMaterialSupplier(env, network_nodes['Tank0_RawProduct'], rate=4.0)
    
    proc_reactor = ProductionProcess(env, 'Reactor', network_nodes['Tank0_RawProduct'], network_nodes['Tank1_CrudeIso'], flow_rate=0.42, process_yield=0.90)
    proc_em_dist = ProductionProcess(env, 'Monomer_Dist', network_nodes['Tank1_CrudeIso'], network_nodes['Tank2_Monomer_Em'], flow_rate=2.5, process_yield=0.86, active_by_default=False)
    logistics_road = TransportLink(env, 'Road_Link', network_nodes['Tank2_Monomer_Em'], network_nodes['Tank3_Monomer_Ert'], batch_size=24, transit_hours=3)
    proc_ert_camp = ProductionProcess(env, 'Ert_Campaign', network_nodes['Tank3_Monomer_Ert'], network_nodes['Tank4_ColdFrac'], flow_rate=2.5, process_yield=(0.99 * 0.743), active_by_default=False)
    proc_ert_frac = ProductionProcess(env, 'Frac_Dist', network_nodes['Tank4_ColdFrac'], network_nodes['Tank6_Purified'], flow_rate=13.0, process_yield=0.96, active_by_default=False)
    
    CampaignController(env, trigger_node=network_nodes['Tank3_Monomer_Ert'], controlled_processes=[proc_ert_camp])
    DownstreamDistillationController(env, trigger_node=network_nodes['Tank4_ColdFrac'], controlled_processes=[proc_ert_frac])
    EmmerichDistillationController(env, trigger_node=network_nodes['Tank1_CrudeIso'], controlled_processes=[proc_em_dist])
    
    all_production_lines = [proc_reactor, proc_em_dist, proc_ert_camp, proc_ert_frac]
    telemetry = TelemetryEngine(env, network_nodes, all_production_lines, [logistics_road])

    # 2. Pygame Initialization
    pygame.init()
    screen = pygame.display.set_mode((1100, 650))
    pygame.display.set_caption("Supply Chain Simulation - Real-Time Monitoring Dashboard")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Segoe UI", 13)
    font_bold = pygame.font.SysFont("Segoe UI", 14, bold=True)
    font_title = pygame.font.SysFont("Segoe UI", 18, bold=True)

    # Graphical coordinates of the storage tanks (X, Y, Width, Height)
    tank_positions = {
        'Tank0_RawProduct':  (40, 200, 90, 160),
        'Tank1_CrudeIso':    (220, 200, 90, 160),
        'Tank2_Monomer_Em':  (400, 200, 90, 160),
        'Tank3_Monomer_Ert': (620, 200, 90, 160),
        'Tank4_ColdFrac':    (800, 200, 90, 160),
        'Tank6_Purified':    (970, 200, 90, 160),
    }

    # Status Indicators Colors
    status_colors = {
        "Running": (46, 204, 113),   # Green
        "Starved": (230, 126, 34),  # Orange
        "Blocked": (231, 76, 60),   # Red
        "Suspended": (149, 165, 166),# Gray
        "Idle": (149, 165, 166)
    }

    sim_duration = 2160 
    
    # 3. Main Rendering Loop
    running = True
    while running and env.now < sim_duration:
        clock.tick(60) # Frame rate execution speed modifier

        # Handle window closure events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # --- SIMPY - PYGAME LINK ---
        # Force SimPy to execute upcoming discrete events for the next logical step
        try:
            env.run(until=env.now + 1)
        except Exception as e:
            print(f"SimPy execution break note: {e}")
            break

        # Canvas background color
        screen.fill((245, 247, 250))

        # --- RENDERING PRODUCTION SITE BOUNDARIES ---
        pygame.draw.rect(screen, (230, 240, 255), (20, 110, 500, 420), border_radius=8) # Emmerich Boundary
        pygame.draw.rect(screen, (230, 255, 240), (600, 110, 480, 420), border_radius=8) # Ertvelde Boundary
        
        screen.blit(font_title.render("SITE 1: EMMERICH (Germany)", True, (44, 62, 80)), (30, 120))
        screen.blit(font_title.render("SITE 2: ERTVELDE (Belgium)", True, (44, 62, 80)), (610, 120))

        # --- RENDERING STORAGE ASSETS (TANK NODES) ---
        for key, node in network_nodes.items():
            x, y, w, h = tank_positions[key]
            
            # Volume Fill Height Calculations
            pct = node.level / node.container.capacity
            fill_h = pct * h
            
            # Draw Liquid Volume
            pygame.draw.rect(screen, (41, 128, 185), (x, y + h - fill_h, w, fill_h))
            # Draw Tank Shell Outlines
            pygame.draw.rect(screen, (52, 73, 94), (x, y, w, h), 3)
            
            # Asset Labels & Asset Values Text Blitting
            name_txt = font_bold.render(node.name, True, (44, 62, 80))
            val_txt = font.render(f"{node.level:.1f}/{node.container.capacity:.0f} T", True, (44, 62, 80))
            screen.blit(name_txt, (x, y - 40))
            screen.blit(val_txt, (x, y - 22))

        # --- RENDERING PRODUCTION PIPELINES (EDGES) ---
        processes_draw_data = [
            (proc_reactor, 150, 280),
            (proc_em_dist, 330, 280),
            (proc_ert_camp, 730, 280),
            (proc_ert_frac, 910, 280)
        ]

        for proc, px, py in processes_draw_data:
            color = status_colors.get(proc.status, (127, 143, 166))
            # Render directional status flow vectors
            pygame.draw.line(screen, color, (px, py), (px + 50, py), 5)
            pygame.draw.polygon(screen, color, [(px + 45, py - 6), (px + 55, py), (px + 45, py + 6)])
            
            # State label tracking metrics
            lbl_status = font_bold.render(proc.status, True, color)
            lbl_name = font.render(proc.name, True, (100, 110, 120))
            screen.blit(lbl_name, (px - 10, py - 35))
            screen.blit(lbl_status, (px, py + 10))

        # --- RENDERING INTERSITE FREIGHT CHANNEL (LOGISTICS PIPELINE) ---
        # Fixed road vector line separating Cuve 2 (EM) from Cuve 3 (ERT)
        pygame.draw.line(screen, (127, 140, 141), (490, 280), (620, 280), 3)
        
        # Freight Dispatch Visualization Triggers
        if logistics_road.active_trucks_in_transit > 0:
            pygame.draw.rect(screen, (241, 196, 15), (530, 265, 50, 30), border_radius=4)
            truck_txt = font_bold.render(f"x{logistics_road.active_trucks_in_transit}", True, (0, 0, 0))
            screen.blit(truck_txt, (545, 270))
        
        lbl_road = font.render("Logistics Route (3h)", True, (44, 62, 80))
        screen.blit(lbl_road, (500, 235))

        # --- GLOBAL TIMING AND EXECUTIVE DASHBOARD UPPER BAND ---
        pygame.draw.rect(screen, (44, 62, 80), (0, 0, 1100, 60))
        title_dash = font_title.render("REAL-TIME MONITORING DASHBOARD - INDUSTRIAL SUPPLY CHAIN PROCESS", True, (255, 255, 255))
        time_txt = font_title.render(f"Simulation Time: {env.now} Hours", True, (241, 196, 15))
        screen.blit(title_dash, (20, 18))
        screen.blit(time_txt, (800, 18))

        # KPI Metrics Footer Section Block
        pygame.draw.rect(screen, (220, 225, 230), (20, 550, 1060, 70), border_radius=5)
        foot_txt1 = font.render(f"Total Trucks Dispatched: {logistics_road.total_trucks_dispatched} trucks", True, (44, 62, 80))
        foot_txt2 = font.render(f"Total Mass Dispatched via Freight: {logistics_road.total_tons_transported:.1f} Tons", True, (44, 62, 80))
        foot_txt3 = font_bold.render(f"Final Purified Inventory Stockpile: {network_nodes['Tank6_Purified'].level:.2f} Tons", True, (39, 174, 96))
        screen.blit(foot_txt1, (40, 565))
        screen.blit(foot_txt2, (40, 590))
        screen.blit(foot_txt3, (650, 575))

        pygame.display.flip()

    pygame.quit()
    
    # 4. Final Telemetry Export Routine
    telemetry.export_to_csv('enhanced_supply_chain_logbook.csv')
    print("\nSimulation completed successfully.")
    print("Exported file: 'enhanced_supply_chain_logbook.csv'")

if __name__ == "__main__":
    run_visual_simulation()