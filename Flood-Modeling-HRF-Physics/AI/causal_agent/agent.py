import random
from collections import defaultdict
import config
import numpy as np
import itertools
from qcia_integration import QCIA
from grounded_intelligence import generate_grounded_embedding, generate_action_embedding

class Agent:
    """
    Represents the AI agent in the world, driven by core needs.
    """
    def __init__(self, world_engine):
        self.world = world_engine
        self.pos = (self.world.width // 2, self.world.height // 2)
        self.inventory = []
        
        # Core Attributes
        self.warmth = config.INITIAL_WARMTH
        
        # State & Goals
        self.current_goal = "Wander"
        self.current_plan = []
        self.plan_purpose = None # What is the high-level goal of the current plan?
        self.log = []
        self.is_traumatized_by_cold = False
        self.investigation_target = None
        self.stuck_counter = 0
        self.last_pos = self.pos
        self.inspected_object_ids = set()

        # Phase 3: Experimentation
        self.tested_crafting_pairs = set()

        # Phase 4: QCIA Integration
        self.qcia = QCIA()

        # Phase 2: Memory and Learning
        self.memory = []
        self.learned_correlations = {}  # e.g. {'fire': {'warmth_impact': 9.5}}

    def update_state(self, perception: dict):
        """
        Updates the agent's internal state based on perception.
        """
        # Check for immediate environmental effects, like standing in fire
        sensed_objects = perception.get('objects_sensed', [])
        if any('fire' in obj for obj in sensed_objects):
            self.warmth = config.MAX_WARMTH
            # Being saved from desperation is a traumatic/salvific event
            if self.current_goal == "Get Warm (Desperate)":
                self.is_traumatized_by_cold = True 
                self.log.append("FIRE! It saved me! I must remember this feeling.")
            else:
                self.log.append("I'm standing in a fire! My warmth is fully restored!")
            return # No warmth loss this tick

        # The primary driver is warmth loss from the cold environment
        temp_diff = config.INITIAL_WARMTH / 2 - perception['temperature']
        warmth_loss = config.BASE_WARMTH_LOSS_PER_TICK + (temp_diff * 0.05)
        self.warmth -= warmth_loss
        
        # If agent becomes critically cold, it becomes traumatized.
        if self.warmth < config.CRITICAL_WARMTH_THRESHOLD:
            if not self.is_traumatized_by_cold:
                self.log.append("This cold is terrifying. I must never feel this again.")
                self.is_traumatized_by_cold = True

        # Clamp the warmth value to be within [0, MAX_WARMTH]
        self.warmth = max(0, min(self.warmth, config.MAX_WARMTH))

    def find_nearest_object_pos(self, object_base_name: str | None, ignore_ids: set = None) -> tuple | None:
        """
        Finds the coordinates of the nearest object.
        If object_base_name is provided, it looks for a specific type.
        If None, it finds the nearest of any object.
        """
        found_positions = []
        all_positions = list(self.world.state['objects'].keys())

        if not all_positions:
            return None

        # Build a list of valid positions and their corresponding full item names
        valid_positions_and_items = []
        for pos, items in self.world.state['objects'].items():
            for item in items:
                # Filter by base name if provided
                if object_base_name and object_base_name not in item:
                    continue
                # Filter by ignored IDs
                if ignore_ids and item in ignore_ids:
                    continue
                valid_positions_and_items.append((pos, item))
        
        if not valid_positions_and_items:
            return None

        # Find the one with the minimum distance among the valid items
        agent_pos_np = np.array(self.pos)
        distances = [np.linalg.norm(agent_pos_np - np.array(p[0])) for p in valid_positions_and_items]
        nearest_index = np.argmin(distances)
        return valid_positions_and_items[nearest_index][0]

    def get_direction_towards(self, target_pos: tuple) -> str:
        """Returns the single best cardinal direction to move towards a target."""
        if target_pos is None:
            return random.choice(['north', 'south', 'east', 'west'])

        dx = target_pos[0] - self.pos[0]
        dy = target_pos[1] - self.pos[1]
        
        # Avoid getting stuck oscillating
        if abs(dx) > abs(dy):
            return "east" if dx > 0 else "west"
        elif abs(dy) > 0:
            return "south" if dy > 0 else "north"
        else: # Agent is already at the target
            return 'stay' 

    def decide_action(self, perception_before: dict):
        """
        The core decision-making loop. Returns a dictionary describing the action.
        """
        self.log.clear()

        # 0. Highest Priority: Investigate startling events
        if self.current_goal == "Investigate":
            if self.investigation_target:
                # Re-implement is_pos_valid logic here
                x, y = self.investigation_target
                if 0 <= x < self.world.width and 0 <= y < self.world.height:
                    if self.pos == self.investigation_target:
                        self.log.append("I have arrived at the site of the event. What happened here?")
                        self.investigation_target = None
                        self.current_goal = "Wander" # Reset state
                        return self.decide_action(perception_before) # Re-evaluate goals immediately
                    else:
                        self.log.append(f"Moving to investigate {self.investigation_target}.")
                        return {'action': 'move', 'direction': self.get_direction_towards(self.investigation_target)}
                else:
                    self.log.append("The site of the event is gone. I will stop investigating.")
                    self.current_goal = "Wander"
                    self.investigation_target = None
                    return self.decide_action(perception_before) # Re-evaluate goals immediately
        
        # 1. Execute a plan if one exists
        elif self.current_plan:
            self.current_goal = "Executing Plan"

            # Improved Stuck Detector
            is_stuck = False
            if self.pos == self.last_pos:
                is_stuck = True
            # NEW: If the plan is to get warm but we are getting colder, it's a bad plan.
            if self.plan_purpose == 'Get Warm' and self.warmth < perception_before['temperature']:
                is_stuck = True

            if is_stuck:
                self.stuck_counter += 1
            else:
                self.stuck_counter = 0

            if self.stuck_counter > 5:
                self.log.append("I seem to be stuck. This plan is not working. I'll try something else.")
                self.current_plan.clear()
                self.plan_purpose = None
                self.stuck_counter = 0
                return self.decide_action(perception_before) # Re-evaluate goals immediately

            next_action = self.current_plan.pop(0)
            self.log.append(f"Executing next step in plan: {next_action}")
            return next_action
        
        # 2. Primary Drive: Survival
        elif self.warmth < config.CRITICAL_WARMTH_THRESHOLD:
            self.current_goal = "Get Warm (Desperate)"
            self.log.append("I am critically cold! I must find warmth now!")

            try:
                current_state_vector = np.zeros(7)
                predicted_plan = self.qcia.predict_action_sequence(current_state_vector)
                if predicted_plan:
                    self.log.append(f"My QCIA has formulated a plan to get warm!")
                    self.current_plan = predicted_plan
                    self.plan_purpose = 'Get Warm' # Set the purpose of the plan
                    return self.decide_action(perception_before) # Re-evaluate goals immediately
            except Exception as e:
                self.log.append(f"QCIA prediction error: {e}")

            if 'fire' in self.learned_correlations:
                self.log.append("QCIA failed. I know 'fire' is warm. Looking for one...")
                fire_pos = self.find_nearest_object_pos('fire')
                if fire_pos and self.pos != fire_pos:
                    return {'action': 'move', 'direction': self.get_direction_towards(fire_pos)}

            # --- NEW LOGIC: EUREKA MOMENT ---
            # If I can't find fire, can I make it?
            # This requires having learned that some items are "useful" (e.g., wood)
            # and having items in inventory to experiment with.
            self.current_goal = "Experiment for Warmth"
            self.log.append("I can't find fire. I must try to create warmth myself.")
            
            if len(self.inventory) < 2:
                # Not enough items to experiment, find some known useful ones first.
                useful_items = self.get_known_useful_items()
                item_to_find = None
                if useful_items:
                    item_to_find = random.choice(useful_items)
                    self.log.append(f"I need more items to experiment. I'll look for something useful like {item_to_find}.")
                
                # If we don't know what's useful, just find anything we haven't seen.
                item_pos = self.find_nearest_object_pos(item_to_find, ignore_ids=self.inspected_object_ids)

                if item_pos:
                    if self.pos == item_pos:
                        return {'action': 'pickup'}
                    else:
                        return {'action': 'move', 'direction': self.get_direction_towards(item_pos)}
            else:
                # I have items, let's try crafting the most promising pair
                items_to_craft = self.prioritize_crafting_items()
                if items_to_craft:
                    self.log.append(f"My best guess is to try crafting {items_to_craft[0]} and {items_to_craft[1]}.")
                    return {'action': 'craft', 'items': items_to_craft}

            self.log.append("I need to experiment but don't know what to do. I will wander desperately.")
            return {'action': 'move', 'direction': random.choice(['north', 'south', 'east', 'west'])}
            
        # 3. Proactive Goal: Prevent Future Cold (if traumatized)
        elif self.is_traumatized_by_cold:
            self.current_goal = "Prevent Future Cold"
            self.log.append("I remember the terrible cold. I must master warmth to prevent it.")

            # --- EUREKA: Plan to create fire from sparks ---
            if self.learned_correlations.get('crafting_result_spark'):
                self.log.append("I know how to make sparks. I can use this to make fire!")
                
                inventory_item_names = [item for item in self.inventory]
                stone_items = [item for item in inventory_item_names if 'stone' in item]
                fuel_item_name = next((item for item in inventory_item_names if 'wood' in item or 'leaf' in item), None)

                # If we have all the ingredients, execute the plan to make fire.
                if len(stone_items) >= 2 and fuel_item_name:
                    self.log.append("I have stones and fuel! I will try to make fire.")
                    self.current_goal = "Executing Plan (Eureka!)"
                    self.plan_purpose = "Create Fire"
                    self.current_plan = [
                        {'action': 'drop', 'item': fuel_item_name},
                        {'action': 'craft', 'items': [stone_items[0], stone_items[1]]}
                    ]
                    # Re-enter decide_action to immediately start executing this new plan
                    return self.decide_action(perception_before)

                # Otherwise, gather the missing ingredients.
                else:
                    self.log.append("I need the right materials to create fire.")
                    if not fuel_item_name:
                        self.log.append("I'll look for some fuel (wood or leaf).")
                        # Prioritize wood as it's better fuel
                        item_pos = self.find_nearest_object_pos('wood') or self.find_nearest_object_pos('leaf')
                        if item_pos:
                            if self.pos == item_pos: return {'action': 'pickup'}
                            else: return {'action': 'move', 'direction': self.get_direction_towards(item_pos)}
                    elif len(stone_items) < 2:
                        self.log.append(f"I have fuel. Now I need {2 - len(stone_items)} more stone(s).")
                        item_pos = self.find_nearest_object_pos('stone')
                        if item_pos:
                            if self.pos == item_pos: return {'action': 'pickup'}
                            else: return {'action': 'move', 'direction': self.get_direction_towards(item_pos)}
            # --- END EUREKA LOGIC ---

            if len(self.inventory) >= 2:
                items_to_craft = self.prioritize_crafting_items()
                if items_to_craft:
                    self.log.append(f"I will test crafting {items_to_craft[0]} and {items_to_craft[1]}.")
                    return {'action': 'craft', 'items': items_to_craft}
            
            useful_items = self.get_known_useful_items()
            if useful_items:
                self.log.append(f"I know these items might be useful: {useful_items}. I will look for them.")
                for item_name in useful_items:
                    item_pos = self.find_nearest_object_pos(item_name)
                    if item_pos:
                        self.log.append(f"Found a {item_name} at {item_pos}. Moving to collect it.")
                        if self.pos == item_pos:
                            return {'action': 'pickup'}
                        else:
                            return {'action': 'move', 'direction': self.get_direction_towards(item_pos)}

            self.log.append("I will wander to find more clues about fire.")
            return {'action': 'move', 'direction': random.choice(['north', 'south', 'east', 'west'])}

        # 4. Default Behavior: Idle Wandering
        else:
            self.current_goal = "Wander (Curious)"
            self.log.append("I am safe and have no pressing goals. I will explore my surroundings.")
            
            # If we just picked something up, drop it to continue exploring.
            if len(self.inventory) > 0:
                item_to_drop = self.inventory[0]
                self.log.append(f"I've learned what I can from the {item_to_drop}. Dropping it.")
                return {'action': 'drop', 'item': item_to_drop}

            # Find the nearest uninspected object to investigate
            nearest_object_pos = self.find_nearest_object_pos(None, ignore_ids=self.inspected_object_ids)
            if nearest_object_pos:
                if self.pos == nearest_object_pos:
                    # We are at the object, pick it up to analyze it
                    self.log.append("This looks interesting. I'll pick it up.")
                    return {'action': 'pickup'}
                else:
                    # Move towards the object
                    self.log.append(f"Something is at {nearest_object_pos}. I'll go see.")
                    direction = self.get_direction_towards(nearest_object_pos)
                    return {'action': 'move', 'direction': direction}
            
            # If there's nothing new to investigate, reset curiosity and wander.
            self.log.append("I've seen everything nearby. I will look again with fresh eyes.")
            self.inspected_object_ids.clear()
            return {'action': 'move', 'direction': random.choice(['north', 'south', 'east', 'west'])}

        # Fallback action if no other decision is made
        return {'action': 'move', 'direction': 'stay'}

    def perform_action(self, action_dict: dict):
        """
        Executes the action decided upon. 
        Returns a tuple of (reward, outcome_dict).
        """
        action = action_dict.get('action')
        reward = 0
        outcome = {}

        if action == "move":
            direction = action_dict.get('direction')
            if direction == 'stay':
                self.log.append("I am staying put.")
                return reward, outcome

            # Calculate reward for moving based on temperature change
            temp_before = self.world.get_temperature_at_pos(self.pos)
            
            x, y = self.pos
            if direction == "north": y = max(0, y - 1)
            elif direction == "south": y = min(self.world.height - 1, y + 1)
            elif direction == "east": x = min(self.world.width - 1, x + 1)
            elif direction == "west": x = max(0, x - 1)
            self.pos = (x, y)

            temp_after = self.world.get_temperature_at_pos(self.pos)
            reward = temp_after - temp_before

            self.log.append(f"I performed the action: move {direction}.")
        
        elif action == 'pickup':
            objects_at_pos = self.world.state['objects'].get(self.pos, [])
            if objects_at_pos:
                item_to_pickup = objects_at_pos[0] # Pick up the first item
                base_item_name = item_to_pickup.split('_')[0]

                if base_item_name in config.UNPICKUPABLE_ITEMS:
                    self.log.append(f"I cannot pick up {item_to_pickup}.")
                    # Still mark it as inspected to avoid getting stuck
                    self.inspected_object_ids.add(item_to_pickup)
                    return reward, outcome

                self.world.remove_object(item_to_pickup, self.pos)
                self.inventory.append(item_to_pickup)
                self.inspected_object_ids.add(item_to_pickup)
                self.log.append(f"I picked up a {item_to_pickup}. I will remember I've seen it.")
                # Learn material properties on pickup
                self.learn_material_properties(item_to_pickup.split('_')[0])
        
        elif action == 'drop':
            if self.inventory:
                item_to_drop = action_dict.get('item')
                if item_to_drop in self.inventory:
                    self.inventory.remove(item_to_drop)
                    self.world.add_object(item_to_drop, self.pos)
                    self.log.append(f"I dropped a {item_to_drop}.")

        elif action == 'craft':
            items = action_dict.get('items', [])
            if len(items) == 2 and all(item in self.inventory for item in items):
                item1, item2 = items
                # Mark this pair as tested
                self.tested_crafting_pairs.add(tuple(sorted((item1, item2))))
                
                outcome = self.world.do_craft(item1, item2)
                self.log.append(f"I crafted {item1} and {item2}. Outcome: {outcome}")
                
                # The reward for crafting is the heat generated
                reward = outcome.get('heat', 0)

                # Add the outcome to the world if it's a new object
                result_obj = outcome.get('result')
                if result_obj:
                    # Give the object a lifespan if specified in the recipe
                    lifespan = outcome.get('lifespan')
                    if lifespan:
                        self.world.state['object_lifespans'][(self.pos, result_obj)] = lifespan
                    self.world.add_object(result_obj, self.pos)
                    # Agent learns what action creates what result
                    self.learned_correlations[f'crafting_result_{result_obj}'] = True

                return reward, outcome

        elif action == 'rub_hands':
            self.warmth += config.WARMTH_FROM_HAND_RUBBING
            self.warmth = min(self.warmth, config.MAX_WARMTH) # Clamp after adding
            self.log.append("I performed the action: rub hands.")

        return reward, outcome

    def remember(self, perception_before, action, perception_after, reward):
        """Stores an experience into the agent's memory and learns from it."""
        # Update position for stuck detector BEFORE the real logic
        if self.pos != self.last_pos:
            self.stuck_counter = 0
        else:
            self.stuck_counter += 1
        self.last_pos = self.pos

        memory_entry = {
            'perception_before': perception_before,
            'action': action,
            'perception_after': perception_after,
            'reward': reward
        }
        self.memory.append(memory_entry)
        self.log.append("I have stored a new memory.")

        # --- QCIA Integration: Learn from this event ---
        try:
            # We need to represent the "state" and "action" as vectors.
            # For now, let's represent the state by the most salient object.
            # This is a simplification we can improve later.
            
            # Before state: what was sensed?
            sensed_before = perception_before.get('objects_sensed', [])
            # For now, let's just use the first object sensed as the 'cause' context.
            # A more advanced model would consider all objects.
            if sensed_before:
                cause_object_name = sensed_before[0].split('_')[0] # e.g., 'fire_1' -> 'fire'
                cause_vector = generate_grounded_embedding(cause_object_name, self.learned_correlations)
            else:
                cause_vector = np.zeros(7) # Empty environment

            # Action vector: use the new function to create a meaningful representation
            action_vector = generate_action_embedding(action, self)

            # After state: what was the result?
            sensed_after = perception_after.get('objects_sensed', [])
            if sensed_after:
                effect_object_name = sensed_after[0].split('_')[0]
                effect_vector = generate_grounded_embedding(effect_object_name, self.learned_correlations)
            else:
                effect_vector = np.zeros(7) # Empty environment

            # The QCIA learns the relationship
            self.qcia.learn_from_event(cause_vector, action_vector, effect_vector, reward, action)
            self.log.append("My QCIA has processed the event.")

        except Exception as e:
            self.log.append(f"QCIA learning error: {e}")
        # ----------------------------------------------

        # Periodically review memory to learn simple correlations (the old way)
        if len(self.memory) % 5 == 0:
            self.review_memory()

    def review_memory(self):
        """
        Analyzes memory to find correlations, e.g., what causes warmth.
        """
        self.log.append("I am reviewing my memories to learn...")

        # Find memories with significant reward (i.e., a large temperature increase)
        significant_memories = [
            mem for mem in self.memory 
            if mem['reward'] > 10.0 # Look for non-trivial temperature gains
        ]

        if not significant_memories:
            self.log.append("My review found nothing significant to learn yet.")
            return

        # Simple correlation: What objects were present in the AFTER state that gave the reward?
        for mem in significant_memories:
            present_objects = mem['perception_after']['objects_sensed']
            for obj in present_objects:
                if 'fire' in obj:
                    # Strengthen the correlation for 'fire'
                    if 'fire' not in self.learned_correlations:
                        self.learned_correlations['fire'] = {'warmth_impact': 0, 'count': 0}
                    
                    self.learned_correlations['fire']['warmth_impact'] += mem['reward']
                    self.learned_correlations['fire']['count'] += 1
                    self.log.append(f"I've updated my understanding of 'fire'. It seems to provide warmth.")
        
        # New: Learn from crafting experiments
        crafting_memories = [mem for mem in self.memory if mem['action']['action'] == 'craft']
        for mem in crafting_memories:
            reward = mem['reward'] # Here, reward is heat_generated
            if reward > 0:
                # Correlate hardness with heat
                items = mem['action']['items']
                try:
                    hardness1 = self.learned_correlations.get(items[0], {}).get('hardness', 0)
                    hardness2 = self.learned_correlations.get(items[1], {}).get('hardness', 0)
                    avg_hardness = (hardness1 + hardness2) / 2
                    
                    if 'crafting_hardness_reward' not in self.learned_correlations:
                        self.learned_correlations['crafting_hardness_reward'] = {'total_hardness': 0, 'total_reward': 0, 'count': 0}
                    
                    entry = self.learned_correlations['crafting_hardness_reward']
                    entry['total_hardness'] += avg_hardness
                    entry['total_reward'] += reward
                    entry['count'] += 1
                    self.log.append(f"Learned that crafting with hardness {avg_hardness:.2f} yielded {reward:.2f} heat.")
                except (KeyError, IndexError):
                    continue

    def learn_material_properties(self, item_name: str):
        """Learns and stores the properties of a material."""
        base_name = item_name.split('_')[0]
        if base_name in config.MATERIAL_PROPERTIES and base_name not in self.learned_correlations:
            properties = config.MATERIAL_PROPERTIES[base_name]
            self.learned_correlations[base_name] = properties
            self.log.append(f"I have learned the properties of {base_name}: {properties}")

    def get_known_useful_items(self) -> list:
        """Identifies items seen in high-reward (warmth) events."""
        useful_items = set()
        for mem in self.memory:
            if mem['reward'] > config.REWARD_THRESHOLD_FOR_GOAL:
                # What objects were present BEFORE the action that gave a good reward?
                # (e.g., wood was there, then lightning struck, then fire appeared)
                for obj in mem['perception_before'].get('objects_sensed', []):
                    base_name = obj.split('_')[0]
                    if base_name in ['wood', 'leaf', 'stone']:
                        useful_items.add(base_name)
        return list(useful_items)

    def prioritize_crafting_items(self) -> list | None:
        """A more intelligent way to decide what to craft."""
        # Simple strategy: find the hardest pair of items in inventory.
        if len(self.inventory) < 2:
            return None

        best_pair = None
        max_hardness = -1

        all_possible_pairs = list(itertools.combinations(self.inventory, 2))
        untested_pairs = [pair for pair in all_possible_pairs if tuple(sorted(pair)) not in self.tested_crafting_pairs]

        if not untested_pairs:
            return None

        for pair in untested_pairs:
            try:
                h1 = self.learned_correlations.get(pair[0], {}).get('hardness', 0)
                h2 = self.learned_correlations.get(pair[1], {}).get('hardness', 0)
                avg_hardness = (h1 + h2) / 2
                if avg_hardness > max_hardness:
                    max_hardness = avg_hardness
                    best_pair = pair
            except Exception:
                continue
        
        return list(best_pair) if best_pair else None

    def observe_lightning_strike(self, pos: tuple, ignited_object: str | None):
        """The agent observes a lightning strike and forms a causal memory."""
        self.log.append(f"I saw lightning strike at {pos}! A fire appeared.")
        
        # Define a vector for the "lightning" event itself.
        lightning_action_vec = np.array([0,0,0,0,1,0,0]) # One-hot for lightning
        fire_effect_vec = generate_grounded_embedding('fire', self.learned_correlations)
        reward = 50.0 # This observation is highly salient
        
        # If a specific object was ignited, learn that precise causal link
        if ignited_object:
            base_obj_name = ignited_object.split('_')[0]
            # The "cause" is the object that was there BEFORE the event
            cause_vec = generate_grounded_embedding(base_obj_name, self.learned_correlations)
            
            self.qcia.learn_from_event(
                cause_vec, lightning_action_vec, fire_effect_vec, reward, 
                {'action': 'observe', 'event': 'lightning', 'object': base_obj_name}
            )
            self.log.append(f"My QCIA noted that lightning + {base_obj_name} -> fire.")
        else: # Lightning struck empty ground
            cause_vec = np.zeros(7) # Vector for "nothing"
            self.qcia.learn_from_event(
                cause_vec, lightning_action_vec, fire_effect_vec, reward,
                {'action': 'observe', 'event': 'lightning', 'object': 'ground'}
            )
            self.log.append(f"My QCIA noted that lightning on empty ground -> fire.")

        # This event is important! It grabs the agent's attention.
        self.current_goal = "Investigate"
        self.investigation_target = pos
        self.current_plan.clear()
        self.log.append(f"That was startling! I must go investigate {pos}.")
