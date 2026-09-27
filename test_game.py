import unittest
from adaptive import train
from world import Game, WALLS, center, cell, pathfind

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
        self.assertIn(len(game.zombies), (4, 5))
        self.assertEqual(len(game.pickups), 6)
        self.assertGreaterEqual(game.time, 270)
        self.assertEqual(game.rescued_count, 0)

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

    def test_downed_defender_stays_in_place(self):
        game = Game(seed=7)
        game.defender.hp = 0
        position = game.defender.pos
        for _ in range(30):
            game.update(1 / 60)
        self.assertEqual(game.defender.pos, position)
        self.assertEqual(game.defender.task, 'Down')

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
        game.zombie.x, game.zombie.y = student.x + 20, student.y
        before = student.hp; game.update(1/60)
        self.assertEqual(game.zombie.state, 'Attack')
        self.assertEqual(game.zombie.target_name, student.name)
        self.assertLess(student.hp, before)

    def test_scout_commits_to_a_retreat_instead_of_flipping_tasks(self):
        game = Game(seed=7)
        for zombie in game.zombies:
            zombie.hp = 0
        threat = game.zombie
        threat.hp = 100
        threat.x, threat.y = game.scout.x + 80, game.scout.y

        tasks = []
        for _ in range(45):
            game.update(1 / 60)
            tasks.append(game.scout.task)

        self.assertEqual(set(tasks), {'Avoid Zombie'})

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

if __name__ == '__main__': unittest.main()
