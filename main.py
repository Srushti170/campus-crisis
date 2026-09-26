"""Campus Crisis: playable Pygame vertical slice using CC0 Kenney artwork."""
import argparse
import math
import os
from array import array
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--smoke-test', action='store_true', help='Render 120 frames without a window')
parser.add_argument('--screenshot', type=str, help='Save a frame and exit')
args = parser.parse_args()
if args.smoke_test or args.screenshot:
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
import pygame
from world import Game, TILE, COLS, ROWS, BUILDINGS, SAFE, center

pygame.mixer.pre_init(44100, -16, 1, 512)
pygame.init()
WIDTH, HEIGHT = 1200, 760
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption('Campus Crisis | First Response')
clock = pygame.time.Clock()
fonts = {size: pygame.font.SysFont('segoeui', size, bold=size >= 24) for size in (12, 14, 16, 18, 24, 32, 48)}
INK, MUTED, GREEN = (224, 235, 233), (143, 164, 166), (100, 231, 174)
OX, OY = 20, 94
game = Game()
selected, paused, debug = True, False, False
screen_state, difficulty = 'menu', 'Normal'
menu_buttons = {}
last_log_message = ''
audio_muted = False
mute_button = pygame.Rect(1052, 45, 130, 32)
ASSET_ROOT = Path(__file__).parent / 'assets' / 'kenney-top-down-shooter'


def load_asset(relative_path, size=None):
    """Load a transparent pack image once, optionally at game-grid scale."""
    image = pygame.image.load(ASSET_ROOT / relative_path).convert_alpha()
    return pygame.transform.smoothscale(image, size) if size else image


def make_tone(frequency, duration, volume=.22):
    """Small dependency-free procedural sound effect."""
    samples = array('h', (int(32767 * volume * math.sin(2 * math.pi * frequency * i / 44100))
                          for i in range(int(44100 * duration))))
    return pygame.mixer.Sound(buffer=samples.tobytes())


try:
    SOUNDS = {'radio': make_tone(880, .10), 'pickup': make_tone(660, .12),
              'hit': make_tone(120, .08), 'win': make_tone(1040, .24), 'loss': make_tone(180, .30)}
except pygame.error:
    SOUNDS = {}


def play_sound(name):
    if not audio_muted and name in SOUNDS:
        SOUNDS[name].play()


GRASS = load_asset('PNG/Tiles/tile_01.png', (TILE, TILE))
ACTOR_IMAGES = {
    'Leader': load_asset('PNG/Man Blue/manBlue_stand.png'),
    'Rescuer': load_asset('PNG/Soldier 1/soldier1_hold.png'),
    'Medic': load_asset('PNG/Man Old/manOld_hold.png'),
    'Defender': load_asset('PNG/Hitman 1/hitman1_hold.png'),
    'Scout': load_asset('PNG/Survivor 1/survivor1_hold.png'),
    'Student': load_asset('PNG/Man Brown/manBrown_stand.png'),
    'Zombie': load_asset('PNG/Zombie 1/zoimbie1_hold.png'),
}


def text(value, x, y, size=16, color=INK):
    screen.blit(fonts[size].render(value, True, color), (x, y))


def rect(color, bounds, radius=0, width=0):
    pygame.draw.rect(screen, color, bounds, width, border_radius=radius)


def menu_button(key, label, bounds, accent=False):
    menu_buttons[key] = pygame.Rect(bounds)
    hovered = menu_buttons[key].collidepoint(pygame.mouse.get_pos())
    fill = (55, 105, 92) if accent else (38, 58, 66)
    if hovered:
        fill = (78, 142, 117) if accent else (55, 82, 92)
    rect(fill, bounds, 7)
    rect(GREEN if accent else (91, 117, 125), bounds, 7, 1)
    rendered = fonts[16].render(label, True, INK)
    screen.blit(rendered, rendered.get_rect(center=menu_buttons[key].center))


def draw_map():
    rect((35, 62, 53), (OX, OY, COLS * TILE, ROWS * TILE), 8)
    for y in range(ROWS):
        for x in range(COLS):
            screen.blit(GRASS, (OX + x*TILE, OY + y*TILE))
    for bounds in [(0, 9, 28, 2), (12, 0, 3, 20), (24, 0, 3, 20), (1, 0, 3, 20)]:
        x, y, w, h = bounds
        rect((65, 78, 78), (OX+x*TILE, OY+y*TILE, w*TILE, h*TILE))
    for x in range(10, COLS*TILE, 42):
        rect((130, 142, 128), (OX+x, OY+10*TILE-2, 18, 3))
    sx, sy, sw, sh = SAFE
    safe = pygame.Rect(OX+sx*TILE, OY+sy*TILE, sw*TILE, sh*TILE)
    rect((33, 104, 81), safe, 6)
    rect(GREEN, safe, 6, 2)
    text('SAFE ZONE', safe.x+16, safe.y+10, 16, GREEN)
    rect((218, 229, 211), (safe.x+20, safe.y+49, 84, 48), 5)
    rect((207, 77, 79), (safe.x+56, safe.y+57, 12, 30))
    rect((207, 77, 79), (safe.x+47, safe.y+66, 30, 12))
    generator_color = (100, 231, 174) if game.fuel >= game.fuel_required else (218, 80, 77)
    rect((36, 53, 58), (safe.x+13, safe.bottom-37, 39, 22), 3)
    rect(generator_color, (safe.x+18, safe.bottom-32, 29, 12), 2)
    text('GEN ON' if game.fuel >= game.fuel_required else 'NEEDS FUEL', safe.x+6, safe.bottom-14, 12, generator_color)
    for i, (x, y, w, h, label) in enumerate(BUILDINGS):
        box = pygame.Rect(OX+x*TILE, OY+y*TILE, w*TILE, h*TILE)
        rect((23, 39, 36), box.move(7, 9), 5)
        rect((116, 134, 134), box, 4)
        rect((63, 84, 89) if i % 2 == 0 else (91, 86, 81), box.inflate(-12, -12), 3)
        for wx in range(box.x+17, box.right-15, 34):
            rect((114, 180, 183), (wx, box.y+16, 21, 13), 2)
            rect((114, 180, 183), (wx, box.bottom-29, 21, 13), 2)
        rect((46, 60, 64), (box.x+18, box.y+50, w*TILE-36, 44), 3)
        text(label, box.x+27, box.y+61, 14)
        rect((129, 145, 139), (box.centerx-18, box.bottom-6, 36, 6))
    for x, y in [(1, 2), (1, 6), (8, 1), (20, 1), (16, 15), (16, 18), (27, 15), (9, 18)]:
        px, py = OX+x*TILE+16, OY+y*TILE+16
        pygame.draw.circle(screen, (26, 45, 38), (px+4, py+6), 18)
        pygame.draw.circle(screen, (54, 97, 67), (px, py), 17)
        pygame.draw.circle(screen, (72, 115, 76), (px-5, py-5), 10)
    text('EAST CAMPUS', OX+750, OY+18, 12, (180, 192, 173))


def draw_actor(a):
    x, y = int(OX+a.x), int(OY+a.y)
    if not a.alive:
        body = pygame.transform.smoothscale(ACTOR_IMAGES[a.role], (36, 26))
        body.set_alpha(125)
        screen.blit(body, body.get_rect(center=(x, y+5)))
        text('DOWN', x-18, y+10, 12, (233, 134, 131))
        return
    colors = {'Leader': (76, 162, 221), 'Rescuer': (232, 168, 75),
              'Medic': (108, 224, 193), 'Defender': (239, 119, 94),
              'Scout': (244, 208, 104),
              'Student': (174, 140, 224), 'Zombie': (138, 171, 90)}
    color = colors[a.role]
    pygame.draw.ellipse(screen, (23, 37, 34), (x-13, y+4, 26, 13))
    if a.role == 'Rescuer' and selected:
        pygame.draw.circle(screen, (245, 201, 120), (x, y), 21, 2)
    # The source Scout art is asymmetrical; rotating it at tiny steering changes
    # makes it visibly flicker. Keep a consistent top-down orientation instead.
    angle = 0 if a.role == 'Scout' else round(math.degrees(math.atan2(a.facing[1], a.facing[0])) / 90) * 90 - 90
    body = pygame.transform.rotate(ACTOR_IMAGES[a.role], angle)
    if a.flash:
        body = body.copy()
        body.fill((105, 105, 105, 0), special_flags=pygame.BLEND_RGB_ADD)
    # The Scout frequently pauses to scan a sector. Keep that scan pose stable
    # so it never looks like it is vibrating while waiting for new information.
    bob = int(math.sin(game.elapsed * 14) * 2) if a.moving and a.role != 'Scout' else 0
    screen.blit(body, body.get_rect(center=(x, y + bob)))
    if a.role == 'Rescuer':
        pygame.draw.circle(screen, (252, 233, 187), (x, y + bob), 3)
    rect((22, 32, 34), (x-17, y-28, 34, 4), 2)
    rect((224, 104, 100) if a.hp < 40 else GREEN, (x-17, y-28, int(34*a.hp/100), 4), 2)
    text(a.role, x-23, y+21, 12, color)
    if debug:
        text(a.state, x-23, y+36, 12)


buttons = [(pygame.Rect(944, 370+i*43, 232, 35), order, label)
           for i, (order, label) in enumerate([('Rescue', '[E]  Rescue student'), ('Follow', '[F]  Follow Commander'), ('Hold', '[H]  Hold position')])]


def draw_fog():
    fog = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    fog.fill((7, 14, 19, 210))
    for y in range(ROWS):
        for x in range(COLS):
            if (x, y) not in game.revealed:
                screen.blit(fog, (OX + x*TILE, OY + y*TILE))


def draw_pickup(pickup):
    """Visible, role-readable pickups; undiscovered items remain under fog."""
    if pickup.collected or not pickup.discovered:
        return
    x, y = int(OX + pickup.x), int(OY + pickup.y)
    colors = {'medkit': (218, 80, 77), 'ammo': (234, 180, 69), 'fuel': (70, 160, 215)}
    pulse = 1 + int((math.sin(game.elapsed * 5) + 1) * 2)
    pygame.draw.circle(screen, (*colors.get(pickup.kind, (255, 255, 255)), 90) if False else colors.get(pickup.kind, (255, 255, 255)), (x, y), 14 + pulse, 1)
    pygame.draw.ellipse(screen, (22, 37, 34), (x-13, y+7, 26, 9))
    pygame.draw.rect(screen, colors[pickup.kind], (x-12, y-12, 24, 21), border_radius=3)
    if pickup.kind == 'medkit':
        pygame.draw.rect(screen, (250, 241, 222), (x-2, y-7, 4, 12))
        pygame.draw.rect(screen, (250, 241, 222), (x-6, y-3, 12, 4))
    elif pickup.kind == 'ammo':
        for offset in (-6, 0, 6):
            pygame.draw.rect(screen, (49, 40, 31), (x+offset-2, y-7, 4, 12), border_radius=1)
            pygame.draw.circle(screen, (247, 222, 149), (x+offset, y-7), 2)
    else:
        pygame.draw.rect(screen, (218, 239, 245), (x-6, y-7, 12, 13), border_radius=1)
        pygame.draw.rect(screen, (218, 239, 245), (x-2, y-10, 7, 4), border_radius=1)
        text('F', x-3, y-5, 12, (38, 89, 125))
    label = {'medkit': 'MEDKIT', 'ammo': 'AMMO x3', 'fuel': 'FUEL CAN'}[pickup.kind]
    text(label, x-24, y+14, 12, colors[pickup.kind])


def draw():
    if screen_state != 'game':
        draw_menu()
        return
    screen.fill((16, 26, 32))
    text('CAMPUS / CRISIS', 22, 17, 32)
    text('FIRST RESPONSE     /     PLAYABLE PROTOTYPE 01', 24, 58, 12, MUTED)
    text(f'{game.rescued_count:02}/{len(game.students):02}  STUDENTS EXTRACTED', 555, 29, 16, GREEN)
    text(f'{int(game.time)//60:02}:{int(game.time)%60:02}', 811, 22, 32, (243, 190, 119))
    rect((76, 101, 107) if audio_muted else (51, 92, 81), mute_button, 6)
    text('🔇 MUTED' if audio_muted else '🔊 SOUND ON', 1061, 53, 12, INK)
    draw_map()
    if debug:
        for role, route in game.routes.items():
            points = [(OX+center(p)[0], OY+center(p)[1]) for p in route]
            if len(points) > 1:
                pygame.draw.lines(screen, (220, 121, 101) if role == 'Zombie' else (103, 211, 224), False, points, 2)
    draw_fog()
    for pickup in game.pickups:
        draw_pickup(pickup)
    visible_actors = [a for a in game.actors if a.role not in ('Student', 'Zombie') or game.discovered[a.name]]
    for a in sorted(visible_actors, key=lambda a: a.y):
        draw_actor(a)
    rect((24, 38, 45), (932, 94, 256, 640), 8)
    text('MISSION CONTROL', 946, 110, 18)
    text('Extract the stranded student.', 946, 140, 14, MUTED)
    text('AI agents coordinate the rescue.', 946, 162, 14, MUTED)
    for i, a in enumerate((game.leader, game.rescuer, game.medic, game.defender, game.scout, game.student)):
        y = 185+i*23
        text(a.role, 946, y, 14)
        rect((46, 60, 63), (1040, y+5, 100, 8), 4)
        rect(GREEN if a.hp > 35 else (237, 119, 110), (1040, y+5, int(a.hp), 8), 4)
    intel = 'STUDENT LOCATED' if game.discovered['Student'] else 'SCOUT SEARCHING FOR STUDENT'
    text(intel, 946, 327, 12, GREEN if game.discovered['Student'] else (244, 208, 104))
    text('RESCUER SELECTED' if selected else 'SELECT RESCUER TO COMMAND', 946, 342, 12, (244, 195, 109))
    for bounds, order, label in buttons:
        rect((60, 87, 87) if game.order == order else (36, 52, 61), bounds, 5)
        text(label, bounds.x+12, bounds.y+7, 14)
    text('AI TASK ALLOCATION', 946, 513, 14, GREEN)
    text(f'Scout: {game.scout.task}  [{game.scout.task_score}]', 946, 535, 12, MUTED)
    text(f'Medic: {game.medic.task}  [{game.medic.task_score}]', 946, 553, 12, MUTED)
    text(f'Defender: {game.defender.task}  [{game.defender.task_score}]', 946, 571, 12, MUTED)
    text(f'Medkits: {game.medkits}  |  Ammo: {game.ammo}', 946, 589, 12, (126, 224, 195))
    text(f'Fuel: {game.fuel}/{game.fuel_required} for final evacuation', 946, 604, 12, (70, 160, 215))
    text('FIELD COMMS', 946, 610, 14, GREEN)
    y = 633
    for line in game.logs[-2:]:
        words, current = line.split(), ''
        for word in words:
            if len(current + word) > 31:
                text(current, 946, y, 12, MUTED)
                y += 17
                current = ''
            current += word+' '
        text(current, 946, y, 12, MUTED)
        y += 26
    text('WASD Move  |  Shift Run  |  Space Strike  |  E Rescue  |  Tab Select  |  P Pause  |  F3 AI paths  |  R Restart', 22, 742, 12, MUTED)
    if game.shove_cooldown > .4:
        pygame.draw.circle(screen, (221, 233, 202), (int(OX+game.leader.x), int(OY+game.leader.y)), 38, 2)
    if paused or game.result:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 17, 23, 200))
        screen.blit(overlay, (0, 0))
        rect((28, 45, 51), (300, 257, 600, 220), 14)
        title = game.result or 'Mission paused'
        text(title.upper(), 338, 290, 32, GREEN if title == 'Mission complete' else INK)
        report = f"Rescued: {game.rescued_count}/{len(game.students)}   Kills: {game.stats['zombies_neutralized']}   Medkits used: {game.stats['medkits_used']}"
        text(report, 338, 348, 16, MUTED)
        text(f"Fuel: {game.fuel}/{game.fuel_required}   Ammo left: {game.ammo}   Time left: {int(game.time)}s", 338, 378, 16, MUTED)
        text('R  Restart mission     |     Esc  Quit' if game.result else 'P  Resume     |     R  Restart     |     Esc  Quit', 338, 430, 16)


def draw_menu():
    menu_buttons.clear()
    screen.fill((12, 23, 29))
    for y in range(0, HEIGHT, 32):
        for x in range(0, WIDTH, 32):
            screen.blit(GRASS, (x, y))
    shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); shade.fill((7, 16, 22, 210)); screen.blit(shade, (0, 0))
    rect((24, 38, 45), (244, 106, 712, 548), 14)
    rect((74, 129, 117), (244, 106, 712, 548), 14, 2)
    text('CAMPUS / CRISIS', 315, 175, 48)
    text('MULTI-AGENT ZOMBIE RESCUE', 319, 235, 18, GREEN)
    if screen_state == 'menu':
        text('A rescue team is waiting for your command.', 319, 294, 18, MUTED)
        menu_button('briefing', 'START MISSION  [ENTER]', (355, 350, 490, 48), True)
        menu_button('howto', 'HOW TO PLAY  [H]', (355, 412, 490, 44))
        menu_button('quit', 'QUIT  [ESC]', (355, 470, 490, 44))
    elif screen_state == 'briefing':
        text('MISSION BRIEFING', 319, 290, 24, GREEN)
        text('Find and evacuate all three students. Scout reveals threats and supplies.', 319, 332, 16, MUTED)
        text('Fuel powers the Safe Zone generator before the final evacuation.', 319, 364, 16, MUTED)
        text('CHOOSE DIFFICULTY', 319, 407, 14, MUTED)
        for index, label in enumerate(('Easy', 'Normal', 'Hard')):
            menu_button('difficulty_'+label, label+('  ✓' if difficulty == label else ''), (319+index*170, 435, 150, 42), difficulty == label)
        menu_button('deploy', 'DEPLOY TEAM  [ENTER]', (319, 515, 330, 48), True)
        menu_button('back', 'BACK  [ESC]', (664, 515, 180, 48))
    else:
        text('HOW TO PLAY', 319, 290, 24, GREEN)
        text('WASD moves the Commander. Press E to queue rescues.', 319, 332, 16, MUTED)
        text('Scout explores; Medic heals; Defender intercepts zombies.', 319, 364, 16, MUTED)
        text('Collect fuel before the final evacuation.', 319, 396, 16, MUTED)
        menu_button('back', 'BACK TO MENU  [ESC]', (319, 515, 330, 48), True)


running, frames = True, 0
while running:
    dt = 1/60 if args.smoke_test or args.screenshot else clock.tick(60)/1000
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if screen_state == 'game':
                    running = False
                else:
                    screen_state = 'menu'
            elif screen_state == 'menu' and event.key == pygame.K_RETURN:
                screen_state = 'briefing'
            elif screen_state == 'menu' and event.key == pygame.K_h:
                screen_state = 'howto'
            elif screen_state == 'briefing' and event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                difficulty = {pygame.K_1: 'Easy', pygame.K_2: 'Normal', pygame.K_3: 'Hard'}[event.key]
            elif screen_state == 'briefing' and event.key == pygame.K_RETURN:
                game = Game(); game.time = {'Easy': 300, 'Normal': 240, 'Hard': 180}[difficulty]; last_log_message = game.logs[-1]; screen_state = 'game'
            elif screen_state != 'game':
                continue
            elif event.key == pygame.K_m:
                audio_muted = not audio_muted
            elif event.key == pygame.K_r:
                game, paused = Game(), False
            elif event.key == pygame.K_p:
                paused = not paused
            elif event.key == pygame.K_F3:
                debug = not debug
            elif event.key == pygame.K_TAB:
                selected = not selected
            elif not paused:
                if event.key == pygame.K_SPACE:
                    game.shove()
                elif selected and event.key in (pygame.K_e, pygame.K_f, pygame.K_h):
                    game.command({pygame.K_e: 'Rescue', pygame.K_f: 'Follow', pygame.K_h: 'Hold'}[event.key])
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if screen_state != 'game':
                for key, bounds in menu_buttons.items():
                    if bounds.collidepoint(event.pos):
                        if key == 'briefing': screen_state = 'briefing'
                        elif key == 'howto': screen_state = 'howto'
                        elif key == 'quit': running = False
                        elif key == 'back': screen_state = 'menu'
                        elif key == 'deploy': game = Game(); game.time = {'Easy': 300, 'Normal': 240, 'Hard': 180}[difficulty]; last_log_message = game.logs[-1]; screen_state = 'game'
                        elif key.startswith('difficulty_'): difficulty = key.removeprefix('difficulty_')
            elif not paused:
                mx, my = event.pos
                if mute_button.collidepoint(event.pos):
                    audio_muted = not audio_muted
                    continue
                if math.dist((mx-OX, my-OY), game.rescuer.pos) < 28:
                    selected = True
                for bounds, order, _ in buttons:
                    if selected and bounds.collidepoint(event.pos):
                        game.command(order)
    keys = pygame.key.get_pressed()
    if screen_state == 'game' and not paused:
        game.update(dt, (int(keys[pygame.K_d])-int(keys[pygame.K_a]), int(keys[pygame.K_s])-int(keys[pygame.K_w])), keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
        if game.logs[-1] != last_log_message:
            last_log_message = game.logs[-1]
            event_text = game.logs[-1]
            play_sound('radio' if event_text.startswith('Scout:') else 'pickup' if 'collected' in event_text else 'hit' if 'engaging' in event_text else 'win' if game.result == 'Mission complete' else 'loss' if game.result else 'radio')
    draw()
    pygame.display.flip()
    frames += 1
    if args.screenshot:
        pygame.image.save(screen, str(Path(args.screenshot)))
        running = False
    elif args.smoke_test and frames >= 120:
        print('PASS: 120 game update/render frames completed.')
        running = False
pygame.quit()
