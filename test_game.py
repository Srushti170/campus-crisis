import unittest
from world import Game, WALLS, center, cell, pathfind

class MissionTests(unittest.TestCase):
    def test_astar_avoids_buildings(self):
        route = pathfind((4, 4), (12, 4))
        self.assertEqual(route[-1], (12, 4))
        self.assertTrue(all(point not in WALLS for point in route))

    def test_mission_starts_with_three_students_and_zombies(self):
        game = Game()
        self.assertEqual(len(game.students), 3)
        self.assertEqual(len(game.zombies), 3)
        self.assertEqual(game.rescued_count, 0)

    def test_rescuer_waits_for_intel(self):
        game = Game(); game.command('Rescue'); game.update(1/60)
        self.assertEqual(game.rescuer.task, 'Await Scout Intel')

    def test_scout_reveals_and_reports_a_student(self):
        game = Game(); before = len(game.revealed); game.zombies[0].hp = 0
        game.scout.x, game.scout.y = center((25, 8)); game.update(1/60)
        self.assertGreater(len(game.revealed), before)
        self.assertTrue(game.discovered['Student-1'])
        self.assertTrue(any('survivor found' in line for line in game.logs))

    def test_medic_heals_lowest_health_patient(self):
        game = Game(); game.leader.hp = 40; game.medic.x = game.leader.x + 20; game.medic.y = game.leader.y
        game.update(1/60)
        self.assertEqual(game.leader.hp, 78)
        self.assertEqual(game.medkits, 2)

    def test_defender_engages_a_threat(self):
        game = Game(); game.discovered['Zombie-1'] = True; game.zombie.x = game.defender.x + 20; game.zombie.y = game.defender.y
        game.update(1/60)
        self.assertLess(game.zombie.hp, 100)
        self.assertEqual(game.defender.state, 'Engage')

    def test_full_three_student_mission_completes(self):
        game = Game(); game.command('Rescue')
        for _ in range(60 * 90):
            game.update(1/60)
            if game.result:
                break
        self.assertEqual(game.result, 'Mission complete')
        self.assertEqual(game.rescued_count, 3)

    def test_zombie_attacks_student_during_escort(self):
        game = Game(); student = game.student
        student.state = 'Following'; game.escort_student = student
        game.zombie.x, game.zombie.y = student.x + 20, student.y
        before = student.hp; game.update(1/60)
        self.assertEqual(game.zombie.state, 'Attack')
        self.assertLess(student.hp, before)

if __name__ == '__main__': unittest.main()
