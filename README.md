# Campus Crisis — First Response

A standalone desktop Python/Pygame game prototype. Command one rescue agent,
protect a stranded student from a patrolling zombie, and escort the student to
the green Safe Zone within three minutes.

## Run on this computer (PowerShell)

```powershell
cd "C:\Users\Srushti Maurya\OneDrive\WebDevlopment Projects\AI PROJECT"
.\.venv\Scripts\python.exe main.py
```

Or double-click `run.bat`. No environment activation is required.

## Setup on another computer

Install Python 3.10 or newer, then run in this project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Play

| Input | Action |
| --- | --- |
| WASD | Move the blue Commander |
| Shift + WASD | Run (increases zombie detection distance) |
| Space | Strike a nearby zombie; three hits defeat it |
| Click gold Rescuer / Tab | Select / toggle teammate selection |
| E | Send selected Rescuer to the student, then escort home |
| F | Selected Rescuer follows Commander |
| H | Selected Rescuer holds position |
| P | Pause / resume |
| F3 | Toggle AI paths and state labels |
| R | Restart |
| Esc | Quit |

The Rescuer starts selected. Press E to dispatch, then head east along the
central road to protect them. The purple student waits just east of Science.
Stay close and use Space against the zombie. The student follows the Rescuer
once contacted. The Commander, Rescuer, and student must survive; the Medic
and Defender support the mission autonomously.

## Multi-agent behavior

The Commander assigns the rescue task. The Medic and Defender make their own
choices with the shared scoring rule `priority + role suitability - distance -
risk`, displayed in **AI TASK ALLOCATION** on the right side of the game.

- The **Scout** explores a route through the fog-covered campus, reveals nearby
  map tiles, and broadcasts the first survivor and zombie sightings. A rescue
  order can be queued at any time, but the Rescuer waits until the Scout has
  found the student.
- The **Medic** selects the most urgent nearby patient, uses up to three
  medkits, and returns to supporting the escort when nobody needs treatment.
- The **Defender** selects the teammate facing the largest zombie threat,
  moves to intercept, attacks at close range, and deliberately draws the
  zombie's attention away from the rescue party.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe main.py --smoke-test
.\.venv\Scripts\python.exe main.py --screenshot preview.png
```

The smoke test uses SDL's headless driver to run 120 update/render frames.
Unit tests cover navigation, collisions, rescue completion, combat, zombie
search, orders, and mission failure. They do not replace human playtesting.

## Implementation and current scope

- `world.py`: deterministic simulation, A*, collision and line-of-sight checks,
  zombie states and rescue/follow/hold behavior. No rendering dependency.
- `main.py`: desktop window, input, Kenney asset rendering, animation, HUD and overlays.
- `test_game.py`: automated simulation tests.

The game uses the CC0-licensed **Topdown (Shooter) Pack** by Kenney for its
team, student, zombie and ground artwork. The original downloaded ZIP is in
`assets/source/`, its extracted files are in `assets/kenney-top-down-shooter/`,
and the license is preserved as `assets/LICENSE-KENNEY-TOP-DOWN-SHOOTER.txt`.
See `CREDITS.md`. Pygame Community Edition supplies the `pygame` module.

This first slice has one mission, one teammate, one student and one zombie.
Buildings are solid obstacles; interiors, audio, inventory, specialized team
roles, task auctions, advanced crowd avoidance and external sprite sheets are
future work. Agents use distance and line of sight, not directional vision
cones. Characters may overlap; this is not yet cooperative pathfinding.
