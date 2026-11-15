import math
import unittest
from unittest import mock
import pygame
from adaptive import train
from fog import ALL_CELLS, BUILDING_FOOTPRINTS, CloudFog, FogField, visual_clear_cells
from sprites import GAME_HEIGHT, DEFAULT_HEIGHT, ROLES, build_character_sprites
from world import (Game, WALLS, SAFE, ROWS, COLS, TILE, LANDMARKS, ZOMBIE_PATROL, SCOUT_EVADE_RANGE,
                   SAFE_KEEP_OUT, center, cell, in_safe_zone, pathfind, safe_gap, walkable)

class MissionTests(unittest.TestCase):
    def test_ml_model_trains_after_fifteen_completed_missions(self):
        history = []
        for index in range(16):
            won = index % 2 == 0
            history.append({'students_rescued': 3 if won else 1, 'time_remaining': 150 if won else 25,
                            'fuel': 1 if won else 0, 'ammo': 4 if won else 0,
                            'zombies_neutralized': 3 if won else 1, 'medkits_used': 2 if won else 4,
                            'outcome': 'Mission complete' if won else 'Time expired'})
        model = train(history)
        self.assertIsNotNone(model)
        self.assertEqual(model['samples'], 16)

    def test_astar_avoids_buildings(self):
        route = pathfind((10, 6), (13, 6))
        self.assertEqual(route[-1], (13, 6))
        self.assertTrue(all(point not in WALLS for point in route))

    def test_generated_mission_has_expanded_team_and_threats(self):
        game = Game(seed=7)
        self.assertIn(len(game.students), (4, 5))
        self.assertIn(len(game.zombies), (3, 4))
        self.assertEqual(len(game.pickups), 6)
        self.assertGreaterEqual(game.time, 270)
        self.assertEqual(game.rescued_count, 0)

    def test_higher_sector_random_layouts_always_fit_all_students(self):
        for seed in range(1, 81):
            game = Game(seed=seed, campaign_level=3)
            self.assertEqual(len(game.students), game.mission['students'])
            self.assertEqual(len(game.zombies), game.mission['zombies'])

    def test_rescuer_waits_for_intel(self):
        game = Game(seed=7)
        # Keep survivors outside the starting Scout/Commander visibility range.
        for student in game.students:
            student.x, student.y = center((24, 4))
        game.command('Rescue'); game.update(1/60)
        self.assertEqual(game.rescuer.task, 'Await Scout Intel')

    def test_scout_reveals_and_reports_a_student(self):
        game = Game(seed=7); before = len(game.revealed)
        for zombie in game.zombies:
            zombie.hp = 0
        game.student.x, game.student.y = center((24, 4))
        game.scout.x, game.scout.y = center((25, 8)); game.update(1/60)
        self.assertGreater(len(game.revealed), before)
        self.assertTrue(game.discovered['Student-1'])
        self.assertTrue(any('survivor found' in line for line in game.logs))

    def test_medic_heals_lowest_health_patient(self):
        game = Game(seed=7); game.leader.hp = 40; game.medic.x = game.leader.x + 20; game.medic.y = game.leader.y
        game.update(1/60)
        self.assertEqual(game.leader.hp, 78)
        self.assertEqual(game.medkits, 2)

    def test_defender_engages_a_threat(self):
        game = Game(seed=7); game.discovered['Zombie-1'] = True; game.zombie.x = game.defender.x + 20; game.zombie.y = game.defender.y
        game.update(1/60)
        self.assertLess(game.zombie.hp, 100)
        self.assertEqual(game.defender.state, 'Engage')

    def test_zombie_targets_player_defender_when_they_close_distance(self):
        game = Game(seed=7, player_role='Defender')
        for zombie in game.zombies[1:]:
            zombie.hp = 0
        game.defender.x, game.defender.y = center((10, 16))
        game.zombie.x, game.zombie.y = game.defender.x + 20, game.defender.y
        before = game.defender.hp
        game.update(1 / 60)
        self.assertEqual(game.zombie.target_name, game.defender.name)
        self.assertEqual(game.zombie.state, 'Attack')
        self.assertLess(game.defender.hp, before)

    def test_safe_zone_prevents_zombie_damage_to_the_leader(self):
        game = Game(seed=7, player_role='Rescuer')
        game.leader.x, game.leader.y = center((5, 18))
        game.zombie.x, game.zombie.y = game.leader.x + 20, game.leader.y
        before = game.leader.hp
        game.update(1 / 60)
        self.assertEqual(game.leader.hp, before)
        self.assertNotEqual(game.zombie.state, 'Attack')

    def test_each_sector_has_one_fewer_zombie_than_before(self):
        for sector, (low, high) in ((1, (3, 4)), (2, (4, 5)), (3, (5, 6))):
            counts = {len(Game(seed=seed, campaign_level=sector).zombies) for seed in range(40)}
            self.assertEqual((min(counts), max(counts)), (low, high), sector)

    def test_zombie_health_bar_scale_matches_its_tougher_sectors(self):
        game = Game(seed=7, campaign_level=3)
        self.assertEqual(game.max_hp(game.zombie), 124)
        self.assertEqual(game.zombie.hp, 124)
        self.assertEqual(game.max_hp(game.rescuer), 100)

    def test_neutralized_zombie_fades_away_in_two_seconds(self):
        game = Game(seed=7)
        zombie = game.zombie
        zombie.hp = 0
        game.update(1 / 60)
        self.assertAlmostEqual(game.corpse_fade(zombie), 1.0, places=1)
        for _ in range(60):
            game.update(1 / 60)
        self.assertAlmostEqual(game.corpse_fade(zombie), 0.5, places=1)
        for _ in range(61):
            game.update(1 / 60)
        self.assertEqual(game.corpse_fade(zombie), 0.0)

    def test_nobody_jumps_aside_when_you_walk_past(self):
        # Characters only ever walk; none is shoved sideways when another passes.
        game = Game(seed=7, player_role='Defender')
        game.defender.x, game.defender.y = center((2, 18))
        fastest = 158 / 60 + 0.01  # a sprinting player covers the most ground per frame
        last = {a.name: a.pos for a in game.actors}
        for frame in range(60 * 6):
            game.update(1 / 60, movement=(1, 0) if frame < 60 * 3 else (-1, 0))  # through the team and back
            for actor in game.actors:
                self.assertLessEqual(math.dist(actor.pos, last[actor.name]), fastest, actor.name)
                last[actor.name] = actor.pos

    def test_names_show_for_you_students_calling_for_help_and_zombie_targets(self):
        game = Game(seed=7, player_role='Medic')
        self.assertTrue(game.named_on_map(game.medic))  # you
        self.assertTrue(game.named_on_map(game.student))  # waiting for rescue
        self.assertFalse(game.named_on_map(game.scout))
        game.zombie.target_name = game.scout.name
        self.assertTrue(game.named_on_map(game.scout))  # hunted

    def test_zombie_cannot_walk_into_the_safe_zone(self):
        game = Game(seed=7)
        zombie = game.zombie
        zombie.x, zombie.y = center((10, 18))
        for _ in range(120):
            game.move(zombie, -3, 0)  # keep pushing west towards the Safe Zone gate
        self.assertFalse(in_safe_zone(zombie.pos))
        self.assertGreaterEqual(safe_gap(zombie.pos), SAFE_KEEP_OUT)
        rescuer = game.rescuer
        rescuer.x, rescuer.y = center((10, 18))
        for _ in range(60):
            game.move(rescuer, -3, 0)
        self.assertTrue(in_safe_zone(rescuer.pos))  # the team walks straight in

    def test_zombie_gives_up_when_its_prey_reaches_the_safe_zone(self):
        game = Game(seed=7, player_role='Rescuer')
        for zombie in game.zombies[1:]:
            zombie.hp = 0
        for defender in game.defenders:
            defender.hp = 0  # nobody shoots the zombie during the check
        zombie, student, earlier = game.zombie, game.students[0], game.students[1]
        earlier.state = 'Rescued'; earlier.x, earlier.y = center((8, 17))  # standing by the gate
        student.state = 'Following'; game.escort_student = student
        game.rescuer.x, game.rescuer.y = center((13, 18))
        student.x, student.y = center((14, 18))
        zombie.x, zombie.y = center((17, 18))
        states_after_rescue = []
        for _ in range(60 * 8):
            walking = (-1, 0) if cell(game.rescuer.pos)[0] > 4 else (0, 0)
            game.update(1 / 60, movement=walking)
            self.assertFalse(in_safe_zone(zombie.pos))
            if student.state == 'Rescued':
                states_after_rescue.append(zombie.state)
        self.assertEqual(student.state, 'Rescued')
        self.assertNotIn('Search', states_after_rescue)  # no waiting at the gate
        self.assertEqual(states_after_rescue[0], 'Patrol')
        self.assertGreater(safe_gap(zombie.pos), 4 * TILE)  # it went off to look elsewhere

    def test_zombie_does_not_search_right_outside_the_safe_zone(self):
        game = Game(seed=7)
        for zombie in game.zombies[1:]:
            zombie.hp = 0
        zombie = game.zombie
        zombie.x, zombie.y = center((11, 18))
        zombie.last_seen, zombie.search_time = center((8, 18)), 3  # someone slipped through the gate
        game.update(1 / 60)
        self.assertEqual(zombie.state, 'Patrol')
        self.assertIsNone(zombie.last_seen)

    def test_downed_defender_stays_in_place(self):
        game = Game(seed=7)
        game.defender.hp = 0
        position = game.defender.pos
        for _ in range(30):
            game.update(1 / 60)
        self.assertEqual(game.defender.pos, position)
        self.assertEqual(game.defender.task, 'Down')

    def test_defender_role_controls_one_defender_and_ai_runs_the_other(self):
        game = Game(seed=7, player_role='Defender')
        self.assertEqual([d.name for d in game.defenders], ['Defender-1', 'Defender-2'])
        self.assertIs(game.controlled_actor(), game.defender)
        self.assertIn(game.defender2, game.actors)
        before = game.defender.pos
        game.update(1 / 30, movement=(1, 0))
        self.assertGreater(game.defender.x, before[0])  # the player moves Defender-1
        self.assertEqual(game.defender.task, 'Idle')  # and no AI overrides it
        self.assertNotEqual(game.defender2.task, 'Idle')  # Defender-2 makes its own decisions

    def test_both_defenders_are_ai_for_every_other_role(self):
        for role in ('Commander', 'Rescuer', 'Medic', 'Scout'):
            game = Game(seed=7, player_role=role)
            game.update(1 / 30)
            self.assertNotIn(game.controlled_actor(), game.defenders)
            self.assertTrue(all(d.task != 'Idle' for d in game.defenders), role)

    def test_defenders_split_up_two_threats(self):
        game = Game(seed=7)
        for zombie in game.zombies[2:]:
            zombie.hp = 0
        first, second = game.zombies[:2]
        for zombie, tile in ((first, (11, 17)), (second, (10, 15))):
            zombie.x, zombie.y = center(tile); zombie.stun = 5; game.discovered[zombie.name] = True
        for _ in range(30):
            game.update(1 / 60)
        targets = {game.defender_targets[d.name].name for d in game.defenders}
        self.assertEqual(targets, {first.name, second.name})

    def test_second_defender_covers_the_rescuer_while_a_zombie_is_at_large(self):
        game = Game(seed=7)
        for zombie in game.zombies[1:]:
            zombie.hp = 0
        game.zombie.x, game.zombie.y = center((24, 3))  # alive, far away and not yet sighted
        game.rescuer.x, game.rescuer.y = center((12, 11))
        game.command('Hold')
        game.update(1 / 30)
        self.assertFalse(game.discovered[game.zombie.name])
        self.assertEqual(game.defender.task, 'Guard Safe Zone')
        self.assertEqual(game.defender2.task, 'Cover Rescuer')

    def test_defenders_stand_down_once_every_zombie_is_dead(self):
        game = Game(seed=7)
        for zombie in game.zombies:
            zombie.hp = 0
        game.rescuer.x, game.rescuer.y = center((12, 11))
        game.command('Hold')
        game.update(1 / 30)
        self.assertEqual(game.defender.task, 'Guard Safe Zone')
        self.assertEqual(game.defender2.task, 'Guard Safe Zone')  # no longer trails the Rescuer

    def test_full_generated_mission_completes(self):
        game = Game(seed=7); game.command('Rescue')
        for _ in range(60 * 360):
            game.update(1/60)
            if game.result:
                break
        self.assertEqual(game.result, 'Mission complete')
        self.assertEqual(game.rescued_count, len(game.students))

    def test_missions_vary_objective_and_time(self):
        missions = [Game(seed=seed).mission for seed in range(1, 12)]
        self.assertGreater(len({mission['title'] for mission in missions}), 1)
        self.assertGreater(len({mission['time'] for mission in missions}), 1)

    def test_zombie_spawns_vary_between_missions(self):
        layouts = {tuple(sorted(cell(zombie.pos) for zombie in Game(seed=seed).zombies)) for seed in range(1, 10)}
        self.assertGreater(len(layouts), 1)

    def test_campaign_sectors_increase_rescue_pressure(self):
        sector_one = Game(seed=1, campaign_level=1)
        sector_three = Game(seed=1, campaign_level=3)
        self.assertEqual(sector_three.campaign_level, 3)
        self.assertGreater(sector_three.time, 0)
        self.assertGreater(len(sector_three.students), len(sector_one.students))
        self.assertGreater(len(sector_three.zombies), len(sector_one.zombies))
        self.assertLess(sector_three.time, sector_one.time)
        self.assertGreater(sector_three.zombies[0].hp, sector_one.zombies[0].hp)

    def test_zombie_attacks_student_during_escort(self):
        game = Game(seed=7); student = game.student
        student.state = 'Following'; game.escort_student = student
        student.x, student.y = center((12, 11))  # open road, whatever the random layout
        game.zombie.x, game.zombie.y = student.x + 20, student.y
        before = student.hp; game.update(1/60)
        self.assertEqual(game.zombie.state, 'Attack')
        self.assertEqual(game.zombie.target_name, student.name)
        self.assertLess(student.hp, before)

    def test_scout_sidesteps_a_close_zombie_then_resumes_the_sweep(self):
        game = Game(seed=7)
        for zombie in game.zombies:
            zombie.hp = 0
        for defender in game.defenders:
            defender.hp = 0  # nobody shoots the zombie during the check
        threat = game.zombie
        threat.hp = 100; threat.stun = 10  # a stunned zombie stays where it is put
        start = center((12, 5))
        game.scout.x, game.scout.y = start
        threat.x, threat.y = center((13, 5))

        tasks = []
        for _ in range(30):
            game.update(1 / 60)
            tasks.append(game.scout.task)
        # One committed sidestep: no task flipping and no run back to the Commander.
        self.assertEqual(set(tasks), {f'Evade {threat.name}'})
        self.assertGreater(math.dist(game.scout.pos, threat.pos), SCOUT_EVADE_RANGE)
        self.assertLess(math.dist(game.scout.pos, start), 3.5 * TILE)

        for _ in range(240):
            game.update(1 / 60)
            if game.scout.task.startswith('Explore'):
                break
        self.assertTrue(game.scout.task.startswith('Explore'), game.scout.task)

    def test_scout_routes_around_a_sighted_zombie(self):
        game = Game(seed=7)
        for zombie in game.zombies:
            zombie.hp = 0
        threat = game.zombie
        threat.hp = 100
        threat.x, threat.y = center((15, 5))
        self.assertEqual(game.zombie_danger(), {})  # an unseen zombie cannot be avoided
        game.discovered[threat.name] = True

        direct = pathfind((10, 5), (22, 5))
        detour = pathfind((10, 5), (22, 5), game.zombie_danger())
        closest = lambda route: min(math.dist(tile, (15, 5)) for tile in route)
        self.assertEqual(closest(direct), 0)  # the straight road runs through the zombie
        self.assertGreaterEqual(closest(detour), 3)  # the Scout goes round the Lecture Hall
        self.assertEqual(detour[-1], (22, 5))

    def test_scout_searches_unguarded_fog_first_but_never_skips_fog(self):
        game = Game(seed=7)
        for zombie in game.zombies:
            zombie.hp = 0
        everything = [(x, y) for y in range(ROWS) for x in range(COLS)]
        patch = lambda point: [(x, y) for y in range(point[1] - 3, point[1] + 4) for x in range(point[0] - 3, point[0] + 4)]
        north, south = (11, 2), (11, 15)
        game.revealed.update(everything)
        game.revealed.difference_update(patch(north) + patch(south))
        pick = lambda: game.scout_points[game.choose_scout_sector(game.scout.pos)]
        first = pick()
        guarded, other = (north, south) if math.dist(first, north) < math.dist(first, south) else (south, north)

        threat = game.zombie
        threat.hp = 100
        threat.x, threat.y = center(guarded)
        game.discovered[threat.name] = True
        choice = pick()
        self.assertLess(math.dist(choice, other), math.dist(choice, guarded))

        # Once the guarded fog is all that is left, the Scout still goes for it.
        game.revealed.update(patch(other))
        self.assertGreater(game.scout_unseen_coverage(pick()), 0)

    def test_scout_is_not_pinned_by_a_zombie_at_the_safe_zone_exit(self):
        # The only way out of the Safe Zone is the corridor past (9,18), where
        # zombies pushed out of the sanctuary used to wait and pin the Scout.
        game = Game(seed=4, player_role='Defender')
        for zombie in game.zombies[1:]:
            zombie.hp = 0
        game.defender2.hp = 0  # the AI Defender would otherwise shoot the guard
        guard = game.zombie
        evading = 0.0; farthest = 0.0
        for _ in range(60 * 20):
            guard.x, guard.y = center((9, 18)); guard.stun = 1
            game.update(1 / 60)
            evading += (1 / 60) * game.scout.task.startswith('Evade')
            farthest = max(farthest, math.dist(game.scout.pos, center((5, 18))))
        self.assertGreater(farthest, 8 * TILE)  # it got out and went scouting
        self.assertLess(evading, 3.0)

    def test_scout_prioritizes_the_remaining_fog(self):
        game = Game(seed=7)
        for zombie in game.zombies:
            zombie.hp = 0
        # Simulate a campus already explored except for the final sector.
        game.revealed.update((x, y) for y in range(20) for x in range(28))
        fog_sector = game.scout_points[-1]
        for y in range(fog_sector[1] - 3, fog_sector[1] + 4):
            for x in range(fog_sector[0] - 3, fog_sector[0] + 4):
                if 0 <= x < 28 and 0 <= y < 20 and (x, y) not in WALLS:
                    game.revealed.discard((x, y))

        game.scout_point = 0
        game.update(1 / 60)

        self.assertEqual(game.scout_point, len(game.scout_points) - 1)

    def test_scout_reports_back_when_all_sectors_are_clear(self):
        game = Game(seed=7)
        for zombie in game.zombies:
            zombie.hp = 0
        game.revealed.update((x, y) for y in range(20) for x in range(28))
        # A few isolated edge tiles are visually indistinguishable from clear map.
        game.revealed.discard((3, 3))
        for _ in range(10):
            game.update(1 / 60)

        self.assertEqual(game.scout.task, 'Report to Commander')

    def test_scout_keeps_searching_when_outdoor_fog_remains(self):
        game = Game(seed=7)
        for zombie in game.zombies:
            zombie.hp = 0
        game.revealed.update((x, y) for y in range(20) for x in range(28))
        # This road tile is a valid unsearched campus route, not a building.
        game.revealed.discard((2, 5))
        game.update(1 / 60)
        self.assertNotEqual(game.scout.task, 'Report to Commander')

    def test_player_controlled_rescuer_moves_without_rescuer_ai(self):
        game = Game(seed=7, player_role='Rescuer')
        before = game.rescuer.pos
        game.update(1 / 30, movement=(1, 0))
        self.assertGreater(game.rescuer.x, before[0])
        self.assertNotEqual(game.rescuer.task, 'Follow Commander')

    def test_player_rescuer_can_begin_a_discovered_escort(self):
        game = Game(seed=7, player_role='Rescuer')
        student = game.student
        game.discovered[student.name] = True
        game.rescuer.x, game.rescuer.y = student.x - 20, student.y
        game.player_action()
        self.assertEqual(student.state, 'Following')
        self.assertIs(game.escort_student, student)

    def test_player_medic_treats_nearby_injured_teammate(self):
        game = Game(seed=7, player_role='Medic')
        game.leader.hp = 35
        game.medic.x, game.medic.y = game.leader.x + 20, game.leader.y
        before_kits = game.medkits
        game.player_action()
        self.assertGreater(game.leader.hp, 35)
        self.assertEqual(game.medkits, before_kits - 1)

    def test_player_defender_attack_sets_active_threat(self):
        game = Game(seed=7, player_role='Defender')
        game.zombie.x, game.zombie.y = game.defender.x + 40, game.defender.y
        before_hp = game.zombie.hp
        game.player_action()
        self.assertLess(game.zombie.hp, before_hp)
        self.assertIs(game.defender_targets[game.defender.name], game.zombie)

    def test_player_scout_scan_discovers_visible_student(self):
        game = Game(seed=7, player_role='Scout')
        for zombie in game.zombies:
            zombie.hp = 0
        game.student.x, game.student.y = center((24, 4))
        game.scout.x, game.scout.y = center((25, 8))
        game.player_action()
        self.assertTrue(game.discovered['Student-1'])

    def test_player_scout_reveals_fog_while_moving(self):
        game = Game(seed=7, player_role='Scout')
        before = set(game.revealed)
        game.update(1 / 20, movement=(1, 0))
        self.assertGreater(len(game.revealed), len(before))

    def test_field_role_mission_keeps_ai_team_on_rescue_tasks(self):
        game = Game(seed=7, player_role='Scout')
        for zombie in game.zombies:
            zombie.hp = 0
        game.student.x, game.student.y = center((24, 4))
        game.scout.x, game.scout.y = center((25, 8))
        game.update(1 / 30)
        self.assertEqual(game.order, 'Rescue')
        self.assertTrue(game.discovered['Student-1'])
        self.assertIn('Rescue', game.rescuer.task)
        self.assertEqual(game.leader.task, 'Coordinate Team')

    def test_player_rescuer_evacuates_last_escort_anywhere_in_safe_zone(self):
        corners = ((SAFE[0], SAFE[1]), (SAFE[0]+SAFE[2]-1, SAFE[1]),
                   (SAFE[0], SAFE[1]+SAFE[3]-1), (SAFE[0]+SAFE[2]-1, SAFE[1]+SAFE[3]-1))
        for safe_tile in corners:
            game = Game(seed=7, player_role='Rescuer')
            student = game.student
            student.state = 'Following'
            game.escort_student = student
            game.fuel = 0
            game.rescuer.x, game.rescuer.y = center(safe_tile)
            student.x, student.y = game.rescuer.x + 42, game.rescuer.y
            game.player_rescuer_update(0)
            self.assertEqual(student.state, 'Rescued')
            self.assertIsNone(game.escort_student)

    def test_field_team_stages_instead_of_trailing_player_rescuer(self):
        game = Game(seed=7, player_role='Rescuer')
        for zombie in game.zombies:
            zombie.hp = 0
        game.update(1 / 30)
        self.assertEqual(game.leader.task, 'Coordinate Team')
        self.assertEqual(game.medic.task, 'Stage at Clinic')
        self.assertEqual(game.defender.task, 'Guard Safe Zone')

    def test_zombie_patrol_stops_are_reachable_outdoor_tiles(self):
        areas = {name: bounds for name, bounds, _ in LANDMARKS}
        def inside(point, bounds):
            x, y, w, h = bounds
            return x <= point[0] < x + w and y <= point[1] < y + h
        for stop in ZOMBIE_PATROL:
            self.assertTrue(walkable(stop), stop)
            self.assertTrue(pathfind((22, 11), stop), stop)
            for bounds in (areas['PARKING'], areas['SECURITY'], SAFE):
                self.assertFalse(inside(stop, bounds), stop)

    def test_patrolling_zombies_never_freeze(self):
        game = Game(seed=4)
        game.command('Hold')
        for defender in game.defenders:
            defender.hp = 0  # nobody provokes the zombies, so they only patrol
        last = {z.name: z.pos for z in game.zombies}
        still = {z.name: 0 for z in game.zombies}
        longest = 0
        for _ in range(60 * 45):
            game.update(1 / 60)
            for zombie in game.zombies:
                still[zombie.name] = still[zombie.name] + 1 if zombie.state == 'Patrol' and zombie.pos == last[zombie.name] else 0
                last[zombie.name] = zombie.pos
                longest = max(longest, still[zombie.name])
        self.assertLess(longest, 60 * 2)

    def test_zombie_skips_a_patrol_stop_it_cannot_reach(self):
        with mock.patch('world.ZOMBIE_PATROL', ((14, 2), (13, 2))):  # (14, 2) is inside the Library
            game = Game(seed=4)
            for zombie in game.zombies[1:]:
                zombie.hp = 0
            for defender in game.defenders:
                defender.hp = 0
            game.zombie.x, game.zombie.y = center((22, 11))
            game.update(1 / 60)
            self.assertEqual(game.zombie.state, 'Patrol')
            self.assertEqual(game.zombie.patrol, 1)

    def test_no_road_tile_can_be_left_in_fog_after_search_complete(self):
        # Sixteen west-side road tiles, (1,11)-(7,12) and (17,11)-(18,12), used to
        # lie outside every Scout sector: with only them still fogged, the Scout
        # saw no remaining fog and reported "search complete".
        game = Game(seed=7)
        everything = {(x, y) for y in range(ROWS) for x in range(COLS)}
        missed = []
        for tile in (c for c in sorted(everything) if walkable(c)):
            game.revealed = everything - {tile}
            if max(game.scout_unseen_coverage(point) for point in game.scout_points) == 0:
                missed.append(tile)
        self.assertEqual(missed, [])

    def test_scout_sweeps_the_whole_campus_and_reports_back(self):
        game = Game(seed=4)
        game.command('Hold')  # keep the mission running while the Scout searches
        for zombie in game.zombies:
            zombie.hp = 0
        for _ in range(60 * 120):
            game.update(1 / 60)
            if game.scout.task == 'Report to Commander':
                break
        self.assertEqual(game.scout.task, 'Report to Commander')
        unsearched = [c for c in ALL_CELLS if walkable(c) and c not in game.revealed]
        self.assertEqual(unsearched, [])
        self.assertEqual([c for c in ALL_CELLS if c not in visual_clear_cells(game.revealed)], [])


class SpriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sprites = build_character_sprites()

    def test_every_role_has_standing_and_walking_frames_at_game_size(self):
        self.assertEqual(set(self.sprites), set(ROLES))
        for role, sides in self.sprites.items():
            for side in ('right', 'left'):
                frames = sides[side]
                self.assertEqual(len(frames), 3, role)
                self.assertEqual({f.get_size() for f in frames}, {frames[0].get_size()}, role)  # no jitter between frames
                self.assertEqual(frames[0].get_height(), GAME_HEIGHT.get(role, DEFAULT_HEIGHT), role)

    def test_feet_stay_on_the_ground_while_walking(self):
        for role, sides in self.sprites.items():
            for frame in sides['right']:
                bottom = frame.get_height() - 1
                self.assertTrue(any(frame.get_at((x, bottom)).a > 24 for x in range(frame.get_width())), role)

    def test_walking_frames_actually_move_the_legs(self):
        for role, sides in self.sprites.items():
            standing, left_step, right_step = (pygame.image.tobytes(f, 'RGBA') for f in sides['right'])
            self.assertNotEqual(standing, left_step, role)
            self.assertNotEqual(left_step, right_step, role)

    def test_left_facing_frames_mirror_the_right_facing_ones(self):
        for role, sides in self.sprites.items():
            mirrored = pygame.transform.flip(sides['right'][0], True, False)
            self.assertEqual(pygame.image.tobytes(mirrored, 'RGBA'), pygame.image.tobytes(sides['left'][0], 'RGBA'), role)


class FogTests(unittest.TestCase):
    def test_only_scouted_ground_is_clear(self):
        revealed = {(10, 5), (11, 5)}
        clear = visual_clear_cells(revealed)
        self.assertTrue(revealed <= clear)
        self.assertNotIn((20, 12), clear)

    def test_building_roof_clears_once_every_route_around_it_is_scouted(self):
        cells, around = BUILDING_FOOTPRINTS[0]
        self.assertFalse(cells & visual_clear_cells(set(around) - {next(iter(around))}))
        self.assertTrue(cells <= visual_clear_cells(set(around)))

    def test_fog_rolls_back_smoothly_instead_of_popping(self):
        revealed = set()
        field = FogField()
        field.update(revealed, 0)
        revealed.add((14, 9))
        field.update(revealed, .1)
        self.assertGreater(field.density[(14, 9)], 0)
        self.assertLess(field.density[(14, 9)], 1)
        for _ in range(40):
            field.update(revealed, .1)
        self.assertEqual(field.density[(14, 9)], 0)
        self.assertEqual(field.density[(20, 12)], 1)

    def test_new_mission_starts_with_fresh_fog(self):
        field = FogField()
        field.update({(14, 9)}, 0)
        field.update({(3, 3)}, .1)  # a new mission has a new revealed set
        self.assertEqual(field.density[(14, 9)], 1)
        self.assertEqual(field.density[(3, 3)], 0)

    def test_fog_hides_unscouted_campus_and_leaves_scouted_ground_clear(self):
        fog = CloudFog()
        revealed = {(x, y) for x in range(2, 9) for y in range(15, 20)}
        surface = pygame.Surface((COLS * TILE, ROWS * TILE))
        surface.fill((0, 0, 0))
        fog.draw(surface, (0, 0), revealed, 0.0)
        clear_pixel = surface.get_at((int(center((5, 17))[0]), int(center((5, 17))[1])))
        fog_pixel = surface.get_at((int(center((20, 5))[0]), int(center((20, 5))[1])))
        self.assertLess(max(clear_pixel[:3]), 10)
        self.assertGreater(min(fog_pixel[:3]), 90)

if __name__ == '__main__': unittest.main()
