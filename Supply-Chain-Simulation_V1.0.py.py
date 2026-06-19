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
        
        self.status = "Idle"                
        self.total_consumed_tons = 0.0      
        self.total_produced_tons = 0.0      
        
        self.process_loop = self.env.process(self._run())

    def _run(self):
        while True:
            if self.is_running:
                if self.source.level < 3.0:
                    self.status = "Suspended"
                    yield self.env.timeout(1.0)
                    continue

                consumed = self.flow_rate
                produced = consumed * self.process_yield
                
                if self.source.level < consumed:
                    self.status = "Starved"
                    yield self.env.timeout(0.5)
                    continue
                    
                if self.dest.free_space < produced:
                    self.status = "Blocked"
                    yield self.env.timeout(0.5)
                    continue
                
                self.status = "Running"
                yield self.source.container.get(consumed)
                yield self.dest.container.put(produced)
                
                self.total_consumed_tons += consumed
                self.total_produced_tons += produced
            else:
                self.status = "Suspended"
                yield self.env.timeout(1.0)
                continue
                
            yield self.env.timeout(1.0)


class BatchProductionProcess:
    def __init__(self, env, name, source_node, dest_node, batch_size, processing_hours, process_yield, active_by_default=True):
        self.env = env
        self.name = name
        self.source = source_node
        self.dest = dest_node
        self.batch_size = batch_size
        self.processing_hours = processing_hours
        self.process_yield = process_yield
        self.is_running = active_by_default
        
        self.status = "Idle"
        self.total_consumed_tons = 0.0
        self.total_produced_tons = 0.0
        
        self.process_loop = self.env.process(self._run())

    def _run(self):
        while True:
            if self.is_running:
                if self.source.level < self.batch_size:
                    self.status = "Suspended"
                    yield self.env.timeout(1.0)
                    continue
                
                produced = self.batch_size * self.process_yield
                if self.dest.free_space < produced:
                    self.status = "Blocked"
                    yield self.env.timeout(1.0)
                    continue
                
                self.status = "Running"
                yield self.source.container.get(self.batch_size)
                self.total_consumed_tons += self.batch_size
                
                yield self.env.timeout(self.processing_hours)
                
                while self.dest.free_space < produced:
                    self.status = "Blocked"
                    yield self.env.timeout(0.5)
                
                yield self.dest.container.put(produced)
                self.total_produced_tons += produced
                self.status = "Idle"
            else:
                self.status = "Suspended"
                yield self.env.timeout(1.0)


class TransportLink:
    def __init__(self, env, name, source_node, dest_node, batch_size, transit_hours, trigger_pct=0.0):
        self.env = env
        self.name = name
        self.source = source_node
        self.dest = dest_node
        self.batch_size = batch_size
        self.transit_hours = transit_hours
        self.trigger_pct = trigger_pct  
        
        self.active_trucks_in_transit = 0
        self.total_trucks_dispatched = 0
        self.total_tons_transported = 0
        self.shipping_allowed = False if trigger_pct > 0.0 else True
        
        self.env.process(self._run())

    def _run(self):
        while True:
            if self.trigger_pct > 0.0:
                threshold = self.source.container.capacity * self.trigger_pct
                if not self.shipping_allowed and self.source.level >= threshold:
                    self.shipping_allowed = True
                if self.shipping_allowed and self.source.level < self.batch_size:
                    self.shipping_allowed = False

            if self.shipping_allowed and self.source.level >= self.batch_size:
                yield self.source.container.get(self.batch_size)
                
                self.active_trucks_in_transit += 1
                self.total_trucks_dispatched += 1
                self.total_tons_transported += self.batch_size
                
                self.env.process(self._transit_routine())
                yield self.env.timeout(0.5)
            else:
                yield self.env.timeout(1.0)

    def _transit_routine(self):
        yield self.env.timeout(self.transit_hours)
        while self.dest.free_space < self.batch_size:
            yield self.env.timeout(0.5)
        yield self.dest.container.put(self.batch_size)
        self.active_trucks_in_transit -= 1


# ==============================================================================
# LAYER 4: THE CONTROL LAYER (Parameterized Controllers)
# ==============================================================================

class CampaignController:
    def __init__(self, env, trigger_node, controlled_processes, trigger_high_pct, trigger_low_tons):
        self.env = env
        self.trigger_node = trigger_node
        self.processes = controlled_processes
        self.trigger_high_pct = trigger_high_pct    
        self.trigger_low_tons = trigger_low_tons    
        self.env.process(self._monitor_loop())

    def _monitor_loop(self):
        while True:
            high_threshold = self.trigger_node.container.capacity * self.trigger_high_pct
            currently_running = self.processes[0].is_running
            
            if not currently_running and self.trigger_node.level >= high_threshold:
                for proc in self.processes:
                    proc.is_running = True
            
            elif currently_running and self.trigger_node.level <= self.trigger_low_tons:
                for proc in self.processes:
                    proc.is_running = False
                    
            yield self.env.timeout(1.0)


class EmmerichDistillationController:
    def __init__(self, env, trigger_node, controlled_processes, free_space_trigger_tons, low_trigger_tons):
        self.env = env
        self.trigger_node = trigger_node
        self.processes = controlled_processes
        self.free_space_trigger = free_space_trigger_tons  
        self.low_trigger = low_trigger_tons                
        self.env.process(self._monitor_loop())

    def _monitor_loop(self):
        while True:
            if self.trigger_node.free_space <= self.free_space_trigger:
                for proc in self.processes:
                    proc.is_running = True
            
            if self.trigger_node.level <= self.low_trigger:
                for proc in self.processes:
                    proc.is_running = False
                    
            yield self.env.timeout(1.0)


class DownstreamDistillationController:
    def __init__(self, env, trigger_node, controlled_processes, high_trigger_tons, low_trigger_tons):
        self.env = env
        self.trigger_node = trigger_node
        self.processes = controlled_processes
        self.high_trigger = high_trigger_tons  
        self.low_trigger = low_trigger_tons    
        self.env.process(self._monitor_loop())

    def _monitor_loop(self):
        while True:
            if self.trigger_node.level >= self.high_trigger:
                for proc in self.processes:
                    proc.is_running = True
            
            if self.trigger_node.level <= self.low_trigger:
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
# LAYER 6: PYGAME VISUALIZATION INTERFACE & INPUT MANAGER
# ==============================================================================

def get_optimization_inputs():
    """Prompts the user for terminal configuration inputs targeting only designable tanks."""
    print("=" * 60)
    print(" SCENARIO OPTIMIZATION: INPUT CAPACITIES FOR BUILDABLE TANKS (m3)")
    print("=" * 60)
    
    def ask_capacity(prompt, default_val):
        try:
            user_in = input(f"{prompt} [{default_val} m3]: ").strip()
            return float(user_in) if user_in else default_val
        except ValueError:
            return default_val

    # Request entries only for components to be built/sized
    cap_t2_dist  = ask_capacity("Capacity Tank2 (Emmerich Distillate Buffer)   ", 60)
    cap_t3_dist  = ask_capacity("Capacity Tank3 (Ertvelde Distillate Buffer)   ", 360)
    cap_t5_buf   = ask_capacity("Capacity Tank5 (Cold Product Buffer ERT)      ", 290)
    cap_t7_ret   = ask_capacity("Capacity Tank7 (Cold Product Return EMM)      ", 82)
    cap_t6_purif = ask_capacity("Capacity Tank6 (Final ISA Storage Hub)        ", 2000)
    
    print("-" * 60)
    print("FIXED ASSETS: Tank 0 (250m3) | Tank 1 (180m3) | Tank 4 (292.4m3)")
    print(f"BUILT ASSETS: T2: {cap_t2_dist} | T3: {cap_t3_dist} | T5: {cap_t5_buf} | T7: {cap_t7_ret} | T6: {cap_t6_purif}")
    print("=" * 60)
    
    return cap_t2_dist, cap_t3_dist, cap_t5_buf, cap_t7_ret, cap_t6_purif


def run_visual_simulation():
    # Retrieve user optimization properties
    cap_t2_dist, cap_t3_dist, cap_t5_buf, cap_t7_ret, cap_t6_purif = get_optimization_inputs()

    env = simpy.Environment()
    
    # Configure inventory systems (T0, T1, T4 are fixed)
    network_nodes = {
        'Tank0_RawProduct':  StorageTank(env, 'Raw Product', capacity_m3=250, density=0.9, init_fill_pct=0.9),
        'Tank1_CrudeIso':    StorageTank(env, 'Crude Product', capacity_m3=180, density=0.9, init_fill_pct=0.0),
        'Tank2_Monomer_Em':  StorageTank(env, 'distillate EM', capacity_m3=cap_t2_dist, density=0.9, init_fill_pct=0.0),
        'Tank3_Monomer_Ert': StorageTank(env, 'distillate ERT', capacity_m3=cap_t3_dist, density=0.9, init_fill_pct=0.0),
        'Tank4_Hydro_Buffer':StorageTank(env, 'hydrogenated ERT', capacity_m3=292.4, density=0.9, init_fill_pct=0.0),
        'Tank5_Ert_Buffer':  StorageTank(env, 'cold product ERT', capacity_m3=cap_t5_buf, density=0.9, init_fill_pct=0.0), 
        'Tank7_Em_Return':   StorageTank(env, 'cold product EMM', capacity_m3=cap_t7_ret, density=0.9, init_fill_pct=0.0), 
        'Tank6_Purified':    StorageTank(env, 'Final ISA', capacity_m3=cap_t6_purif, density=0.9, init_fill_pct=0.0)   
    }
    
    def simpy_heartbeat(env):
        while True:
            yield env.timeout(1.0)
    env.process(simpy_heartbeat(env))
    
    RawMaterialSupplier(env, network_nodes['Tank0_RawProduct'], rate=0.42)
    
    proc_reactor = ProductionProcess(env, 'Reactor', network_nodes['Tank0_RawProduct'], network_nodes['Tank1_CrudeIso'], flow_rate=0.42, process_yield=0.90)
    proc_em_dist = ProductionProcess(env, 'Monomer_Dist', network_nodes['Tank1_CrudeIso'], network_nodes['Tank2_Monomer_Em'], flow_rate=2.5, process_yield=0.86, active_by_default=False)
    
    logistics_outbound = TransportLink(env, 'Outbound_Link', network_nodes['Tank2_Monomer_Em'], network_nodes['Tank3_Monomer_Ert'], batch_size=24, transit_hours=3)
    
    proc_hydrogenation = BatchProductionProcess(env, 'Hydrogenation', network_nodes['Tank3_Monomer_Ert'], network_nodes['Tank4_Hydro_Buffer'], batch_size=16.5, processing_hours=6.0, process_yield=0.99, active_by_default=False)
    proc_cold_frac = ProductionProcess(env, 'Cold_Fractionation', network_nodes['Tank4_Hydro_Buffer'], network_nodes['Tank5_Ert_Buffer'], flow_rate=2.5, process_yield=0.743, active_by_default=True)
    
    logistics_inbound = TransportLink(env, 'Inbound_Return_Link', network_nodes['Tank5_Ert_Buffer'], network_nodes['Tank7_Em_Return'], batch_size=24, transit_hours=3, trigger_pct=0.90)
    
    proc_em_frac = ProductionProcess(env, 'Final_Frac_Dist', network_nodes['Tank7_Em_Return'], network_nodes['Tank6_Purified'], flow_rate=2.5, process_yield=0.96, active_by_default=False)
    
    # Controllers mapped to the current topology
    CampaignController(env, trigger_node=network_nodes['Tank3_Monomer_Ert'], controlled_processes=[proc_hydrogenation], trigger_high_pct=0.90, trigger_low_tons=17.0)
    EmmerichDistillationController(env, trigger_node=network_nodes['Tank1_CrudeIso'], controlled_processes=[proc_em_dist], free_space_trigger_tons=15.0, low_trigger_tons=1.0)
    DownstreamDistillationController(env, trigger_node=network_nodes['Tank7_Em_Return'], controlled_processes=[proc_em_frac], high_trigger_tons=20.0, low_trigger_tons=1.0)
    
    all_production_lines = [proc_reactor, proc_em_dist, proc_hydrogenation, proc_cold_frac, proc_em_frac]
    all_logistics = [logistics_outbound, logistics_inbound]
    telemetry = TelemetryEngine(env, network_nodes, all_production_lines, all_logistics)

    pygame.init()
    screen = pygame.display.set_mode((1200, 700))
    pygame.display.set_caption("Supply Chain Simulation - Custom Build Configuration")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Segoe UI", 12)
    font_bold = pygame.font.SysFont("Segoe UI", 13, bold=True)
    font_title = pygame.font.SysFont("Segoe UI", 16, bold=True)

    tank_positions = {
        'Tank0_RawProduct':  (50, 160, 85, 120),
        'Tank1_CrudeIso':    (210, 160, 85, 120),
        'Tank2_Monomer_Em':  (370, 160, 85, 120),
        'Tank3_Monomer_Ert': (720, 160, 85, 120),
        'Tank4_Hydro_Buffer':(880, 160, 85, 120),
        'Tank5_Ert_Buffer':  (880, 440, 85, 120), 
        'Tank7_Em_Return':   (370, 440, 85, 120),
        'Tank6_Purified':    (210, 440, 85, 120)
    }

    status_colors = {
        "Running": (46, 204, 113), "Starved": (230, 126, 34), "Blocked": (231, 76, 60),
        "Suspended": (149, 165, 166), "Idle": (149, 165, 166)
    }

    sim_duration = 7000 
    running = True
    
    while running and env.now < sim_duration:
        clock.tick(60) 

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        try:
            env.run(until=env.now + 1)
        except Exception as e:
            break

        screen.fill((244, 246, 249))

        # 1. GEOGRAFISCHE ZONES
        pygame.draw.rect(screen, (235, 242, 250), (25, 95, 500, 515), border_radius=12) # Germany
        pygame.draw.rect(screen, (238, 252, 242), (660, 95, 510, 515), border_radius=12) # Belgium
        
        screen.blit(font_title.render("SITE 1: EMMERICH", True, (44, 62, 80)), (40, 110))
        screen.blit(font_title.render("SITE 2: ERTVELDE", True, (44, 62, 80)), (675, 110))

        # 2. INTERNAL PROCESS PIPELINES
        processes_draw_data = [
            (proc_reactor, 135, 220, "horizontal", True),       
            (proc_em_dist, 295, 220, "horizontal", True),       
            (proc_hydrogenation, 805, 220, "horizontal", True), 
            (proc_cold_frac, 922, 280, "vertical", True),       
            (proc_em_frac, 295, 500, "horizontal", False)       
        ]

        for proc, px, py, orientation, forward in processes_draw_data:
            color = status_colors.get(proc.status, (127, 143, 166))
            lbl_status = font_bold.render(proc.status, True, color)
            
            if orientation == "vertical":
                pygame.draw.line(screen, color, (px, py), (px, py + 160), 5)
                pygame.draw.polygon(screen, color, [(px - 6, py + 150), (px, py + 160), (px + 6, py + 150)])
                screen.blit(font.render(proc.name, True, (110, 120, 135)), (px + 15, py + 60))
                screen.blit(lbl_status, (px + 15, py + 77))
            else:
                pygame.draw.line(screen, color, (px, py), (px + 75, py), 5)
                if forward:
                    pygame.draw.polygon(screen, color, [(px + 65, py - 6), (px + 75, py), (px + 65, py + 6)])
                else:
                    pygame.draw.polygon(screen, color, [(px + 10, py - 6), (px, py), (px + 10, py + 6)])
                screen.blit(font.render(proc.name, True, (110, 120, 135)), (px + 2, py - 28))
                screen.blit(lbl_status, (px + 8, py + 10))

        # LOGISTICS LINK 1: OUTBOUND PIPELINE BRIDGE
        pygame.draw.line(screen, (170, 178, 185), (455, 220), (720, 220), 3)
        if logistics_outbound.active_trucks_in_transit > 0:
            pygame.draw.rect(screen, (241, 196, 15), (560, 208, 45, 24), border_radius=4)
            screen.blit(font_bold.render(f"x{logistics_outbound.active_trucks_in_transit}", True, (0, 0, 0)), (573, 212))
        screen.blit(font.render("Outbound Freight (3h)", True, (52, 73, 94)), (535, 185))

        # LOGISTICS LINK 2: RETURN PIPELINE BRIDGE
        pygame.draw.line(screen, (170, 178, 185), (455, 500), (880, 500), 3)
        if logistics_inbound.active_trucks_in_transit > 0:
            pygame.draw.rect(screen, (241, 196, 15), (630, 488, 45, 24), border_radius=4)
            screen.blit(font_bold.render(f"x{logistics_inbound.active_trucks_in_transit}", True, (0, 0, 0)), (643, 492))
        screen.blit(font.render("Return Freight (3h)", True, (52, 73, 94)), (615, 515))

        # 3. DRAW STORAGE ASSETS
        for key, node in network_nodes.items():
            x, y, w, h = tank_positions[key]
            pct = node.level / node.container.capacity
            fill_h = pct * h
            
            pygame.draw.rect(screen, (41, 128, 185), (x, y + h - fill_h, w, fill_h))
            pygame.draw.rect(screen, (44, 53, 64), (x, y, w, h), 3)
            pygame.draw.line(screen, (44, 53, 64), (x, y), (x + w, y), 5)
            
            name_txt = font_bold.render(node.name, True, (44, 62, 80))
            val_txt = font.render(f"{node.level:.1f} / {node.container.capacity:.0f} T", True, (70, 85, 105))
            screen.blit(name_txt, (x, y - 35))
            screen.blit(val_txt, (x, y - 18))

        # 4. DASHBOARD HEADER
        pygame.draw.rect(screen, (44, 62, 80), (0, 0, 1200, 60))
        screen.blit(font_title.render("Supply Chain Simulation", True, (255, 255, 255)), (25, 18))
        screen.blit(font_title.render(f"Time: {env.now} / {sim_duration} Hrs", True, (241, 196, 15)), (950, 18))

        # 5. KPI SUMMARY FOOTER CONTROL BLOCK
        pygame.draw.rect(screen, (222, 226, 233), (25, 625, 1155, 60), border_radius=8)
        t_out = logistics_outbound.total_trucks_dispatched
        t_in = logistics_inbound.total_trucks_dispatched
        
        screen.blit(font.render(f"Outbound Fleet Dispatches: {t_out} trucks", True, (44, 62, 80)), (45, 635))
        screen.blit(font.render(f"Inbound Return Fleet Dispatches: {t_in} trucks", True, (44, 62, 80)), (45, 655))
        
        final_stock = network_nodes['Tank6_Purified'].level
        screen.blit(font_title.render(f"Purified isostearic acid: {final_stock:.2f} Tons", True, (39, 174, 96)), (740, 642))

        pygame.display.flip()

    pygame.quit()
    telemetry.export_to_csv('enhanced_supply_chain_logbook.csv')
    print("\n[Simulation Configured] Hysteresis high-low cycle implemented successfully.")

if __name__ == "__main__":
    run_visual_simulation()
