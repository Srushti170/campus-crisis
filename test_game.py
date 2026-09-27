import math
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
        route = pathfind((4, 4), (12, 4))
        self.assertEqual(route[-1], (12, 4))
        self.assertTrue(all(point not in WALLS for point in route))

    def test_mission_starts_with_three_students_and_zombies(self):
        game = Game(seed=7)
        self.assertEqual(len(game.students), 3)
        self.assertEqual(len(game.zombies), 3)
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

    def test_full_three_student_mission_completes(self):
        game = Game(seed=7); game.command('Rescue')
        for _ in range(60 * 90):
            game.update(1/60)
            if game.result:
                break
        self.assertEqual(game.result, 'Mission complete')
        self.assertEqual(game.rescued_count, 3)

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
        threat.x, threat.y = game.scout.x, game.scout.y - 80

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
        distance_before = math.dist(game.scout.pos, game.leader.pos)

        for _ in range(10):
            game.update(1 / 60)

        self.assertEqual(game.scout.task, 'Report to Commander')
        self.assertLess(math.dist(game.scout.pos, game.leader.pos), distance_before)

if __name__ == '__main__': unittest.main()
