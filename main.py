"""Campus Crisis: playable Pygame vertical slice using CC0 Kenney artwork."""
import argparse
import math
import os
from array import array
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--smoke-test', action='store_true', help='Render 120 frames without a window')
parser.add_argument('--screenshot', type=str, help='Save a frame and exit')
parser.add_argument('--preview-game', action='store_true', help='Open directly into a mission for visual review')
args = parser.parse_args()
if args.smoke_test or args.screenshot:
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
import pygame
from world import Game, TILE, COLS, ROWS, BUILDINGS, SAFE, LANDMARKS, center, walkable
from adaptive import recommend, report
from campaign import load_progress, record_completion, reset_progress

pygame.mixer.pre_init(44100, -16, 1, 512)
pygame.init()
WIDTH, HEIGHT = 1200, 760
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption('Campus Crisis | First Response')
clock = pygame.time.Clock()
fonts = {size: pygame.font.SysFont('segoeui', size, bold=size >= 24) for size in (12, 13, 14, 16, 18, 24, 32, 48)}
INK, MUTED, GREEN = (224, 235, 233), (143, 164, 166), (100, 231, 174)
PANEL, PANEL_EDGE, ROAD, ROAD_EDGE = (18, 31, 38), (57, 83, 89), (58, 70, 73), (105, 124, 121)
OX, OY = 20, 94
campaign = load_progress()
player_role = 'Commander'
game = Game(campaign_level=campaign['unlocked_sector'], player_role=player_role)
selected, paused, debug, full_map = True, False, False, False
screen_state, difficulty = 'menu', 'Normal'
adaptive_plan = recommend()
adaptive_data = report()
menu_buttons = {}
last_log_message = ''
audio_muted = False
campaign_notice = ''
mission_outcome_processed = False
mute_button = pygame.Rect(1052, 45, 130, 32)
if args.preview_game:
    screen_state = 'game'
ASSET_ROOT = Path(__file__).parent / 'assets' / 'kenney-top-down-shooter'
REALISTIC_MAP_PATH = Path(__file__).parent / 'assets' / 'generated' / 'campus-game-map-v4.png'
GENERATED_CHARACTER_ROOT = Path(__file__).parent / 'assets' / 'generated'


def load_asset(relative_path, size=None):
    """Load a transparent pack image once, optionally at game-grid scale."""
    image = pygame.image.load(ASSET_ROOT / relative_path).convert_alpha()
    return pygame.transform.smoothscale(image, size) if size else image


def load_generated_character(filename, height=56):
    """Load an original rendered character cutout, cropping its transparent canvas.

    The source artwork is deliberately high resolution.  Cropping before scaling
    keeps the actual character sharp and large enough to read over the campus map.
    """
    image = pygame.image.load(GENERATED_CHARACTER_ROOT / filename).convert_alpha()
    parts = pygame.mask.from_surface(image).get_bounding_rects()
    if parts:
        # The largest connected region is the character; tiny isolated pixels are
        # anti-aliasing remnants at the edge of the generated transparent canvas.
        bounds = max(parts, key=lambda item: item.width * item.height)
        image = image.subsurface(bounds).copy()
    width = max(18, round(image.get_width() * height / image.get_height()))
    return pygame.transform.smoothscale(image, (width, height))


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


def start_campaign_mission():
    """Create the currently unlocked sector and apply optional difficulty aid."""
    global game, paused, mission_outcome_processed, campaign_notice, last_log_message
    game = Game(campaign_level=campaign['unlocked_sector'], player_role=player_role)
    manual_time = {'Easy': 60, 'Normal': 0, 'Hard': -60}[difficulty]
    game.time = max(150, game.time + manual_time + adaptive_plan['time'])
    game.medkits = max(1, game.medkits + adaptive_plan['medkits'])
    for zombie in game.zombies:
        zombie.hp = max(30, zombie.hp + adaptive_plan['zombie_hp'])
    game.log(f"Sector {game.campaign_level}: adaptive setting {adaptive_plan['label']}.")
    last_log_message = game.logs[-1]
    paused, mission_outcome_processed, campaign_notice = False, False, ''


def reset_campaign():
    """Clear saved sectors and prepare a fresh Sector 1 mission."""
    global campaign, game, campaign_notice, mission_outcome_processed
    campaign = reset_progress()
    game = Game(campaign_level=1, player_role=player_role)
    campaign_notice, mission_outcome_processed = 'Campaign reset. Sector 1 is ready.', False


GRASS = load_asset('PNG/Tiles/tile_01.png', (TILE, TILE))
REALISTIC_CAMPUS = (pygame.transform.smoothscale(pygame.image.load(REALISTIC_MAP_PATH).convert(), (COLS*TILE, ROWS*TILE))
                    if REALISTIC_MAP_PATH.exists() else None)
ACTOR_IMAGES = {
    # Each specialist has a distinct silhouette and role equipment, so the player
    # can identify the team on the map before reading their name label.
    'Leader': load_generated_character('leader-3d.png'),
    'Rescuer': load_generated_character('rescuer-3d.png'),
    'Medic': load_generated_character('medic-3d.png'),
    'Defender': load_generated_character('defender-3d.png'),
    'Scout': load_generated_character('scout-3d.png'),
    'Student': load_generated_character('student-3d.png', 54),
    'Zombie': load_generated_character('zombie-3d.png', 58),
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
    if REALISTIC_CAMPUS:
        screen.blit(REALISTIC_CAMPUS, (OX, OY))
        for label, tile, width in (('ADMIN BLOCK',(2,2),116),('LIBRARY',(15,2),92),('PARKING',(22,2),88),
                                   ('SECURITY',(24,6),88),('SCIENCE LAB',(2,8),104),('LECTURE HALL',(16,8),112),
                                   ('HOSTEL',(2,14),82),('CAFETERIA',(13,14),96),('SPORTS COURT',(22,14),110)):
            x, y = OX+tile[0]*TILE, OY+tile[1]*TILE
            tag = pygame.Surface((width, 24), pygame.SRCALPHA)
            tag.fill((12, 25, 31, 210))
            screen.blit(tag, (x, y))
            text(label, x+8, y+5, 12, (229, 239, 234))
        # The generated environment is decorative; this overlay keeps the
        # playable extraction point unambiguous above the realistic art.
        sx, sy, sw, sh = SAFE
        safe = pygame.Rect(OX+sx*TILE, OY+sy*TILE, sw*TILE, sh*TILE)
        safe_overlay = pygame.Surface(safe.size, pygame.SRCALPHA)
        safe_overlay.fill((35, 142, 104, 105))
        screen.blit(safe_overlay, safe)
        rect((111, 238, 186), safe, 7, 2)
        text('SAFE ZONE', safe.x+16, safe.y+10, 16, (177, 246, 209))
        text('EVAC', safe.x+10, safe.bottom-22, 12, (177, 246, 209))
        return
    rect((20, 43, 40), (OX, OY, COLS * TILE, ROWS * TILE), 8)
    for y in range(ROWS):
        for x in range(COLS):
            screen.blit(GRASS, (OX + x*TILE, OY + y*TILE))
    # A muted night wash makes the campus feel like an emergency scene rather
    # than a bright board-game map, while leaving landmarks readable.
    night_wash = pygame.Surface((COLS*TILE, ROWS*TILE), pygame.SRCALPHA)
    night_wash.fill((7, 22, 27, 72))
    screen.blit(night_wash, (OX, OY))
    for bounds in [(0, 9, 28, 2), (12, 0, 3, 20), (24, 0, 3, 20), (1, 0, 3, 20)]:
        x, y, w, h = bounds
        road = pygame.Rect(OX+x*TILE, OY+y*TILE, w*TILE, h*TILE)
        rect(ROAD_EDGE, road, 0)
        rect(ROAD, road.inflate(-6, -6), 0)
    for x in range(10, COLS*TILE, 42):
        rect((175, 187, 166), (OX+x, OY+10*TILE-2, 18, 3))
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
    # Evacuation tent and school bus make the Safe Zone immediately readable.
    rect((232, 184, 66), (safe.x+58, safe.y+42, 55, 27), 5)
    rect((66, 109, 135), (safe.x+65, safe.y+47, 31, 11), 2)
    pygame.draw.circle(screen, (35, 43, 45), (safe.x+69, safe.y+70), 5)
    pygame.draw.circle(screen, (35, 43, 45), (safe.x+102, safe.y+70), 5)
    pygame.draw.polygon(screen, (226, 235, 221), [(safe.x+7, safe.y+92), (safe.x+27, safe.y+72), (safe.x+47, safe.y+92)])
    text('EVAC', safe.x+12, safe.y+93, 12, GREEN)
    for i, (x, y, w, h, label) in enumerate(BUILDINGS):
        box = pygame.Rect(OX+x*TILE, OY+y*TILE, w*TILE, h*TILE)
        rect((9, 19, 22), box.move(7, 10), 5)
        rect((79, 101, 105), box, 4)
        rect((45, 61, 67) if i % 2 == 0 else (67, 64, 61), box.inflate(-12, -12), 3)
        for wx in range(box.x+17, box.right-15, 34):
            rect((114, 180, 183), (wx, box.y+16, 21, 13), 2)
            rect((114, 180, 183), (wx, box.bottom-29, 21, 13), 2)
        compact = box.height < 110
        header_y, header_h = box.y + (18 if compact else 50), (24 if compact else 35)
        rect((22, 34, 39), (box.x+12, header_y, box.width-24, header_h), 3)
        text(label, box.x+18, header_y+5, 12 if compact else 14, (211, 224, 219))
        interior = pygame.Rect(box.x+22, box.y+102, box.width-44, box.height-126)
        if label == 'ADMIN BLOCK':
            for wx in range(box.x+18, box.right-12, 22):
                rect((121, 178, 190), (wx, box.y+36, 12, 10), 1)
        elif label == 'LIBRARY':
            for shelf_x in range(interior.x, interior.right, 32):
                rect((113, 73, 43), (shelf_x, interior.y, 20, interior.height), 2)
                for book_y in range(interior.y+4, interior.bottom, 10):
                    rect((205, 151, 68), (shelf_x+3, book_y, 14, 4), 1)
        elif label == 'SCIENCE':
            for bench_x in range(interior.x, interior.right, 46):
                rect((180, 191, 187), (bench_x, interior.y+4, 35, 13), 2)
                pygame.draw.circle(screen, (106, 207, 210), (bench_x+10, interior.y+10), 4)
                pygame.draw.circle(screen, (209, 135, 176), (bench_x+24, interior.y+10), 4)
        elif label == 'LECTURE HALL':
            for row in range(2):
                for desk_x in range(interior.x, interior.right, 30):
                    rect((170, 123, 70), (desk_x, interior.y+row*19, 21, 11), 2)
        elif label == 'HOSTEL':
            for door_x in range(box.x+18, box.right-15, 28):
                rect((107, 74, 58), (door_x, box.y+50, 18, 28), 2)
                rect((224, 184, 91), (door_x+12, box.y+64, 3, 3), 1)
        elif label == 'SPORTS COURT':
            court = pygame.Rect(box.x+14, box.y+48, box.width-28, max(18, box.height-62))
            rect((62, 113, 104), court, 2)
            rect((213, 227, 207), court, 2, 1)
            pygame.draw.line(screen, (213, 227, 207), (court.centerx, court.y+2), (court.centerx, court.bottom-2), 1)
        else:
            for table_x in range(interior.x+8, interior.right, 50):
                pygame.draw.circle(screen, (211, 188, 143), (table_x, interior.y+14), 12)
                pygame.draw.circle(screen, (73, 88, 87), (table_x-16, interior.y+14), 5)
                pygame.draw.circle(screen, (73, 88, 87), (table_x+16, interior.y+14), 5)
        rect((129, 145, 139), (box.centerx-18, box.bottom-6, 36, 6))
        rect((230, 185, 80), (box.centerx-13, box.bottom-9, 26, 5), 2)
    for label, (x, y, w, h), kind in LANDMARKS:
        box = pygame.Rect(OX+x*TILE, OY+y*TILE, w*TILE, h*TILE)
        if kind == 'parking':
            rect((57, 67, 70), box, 4)
            for lane in range(box.x+12, box.right-8, 24):
                pygame.draw.line(screen, (155, 163, 151), (lane, box.y+7), (lane, box.bottom-7), 2)
            text('P', box.centerx-5, box.centery-12, 24, (222, 228, 210))
        else:
            roof = {'medkit': (192, 76, 74), 'ammo': (194, 143, 55), 'fuel': (57, 129, 177)}[kind]
            rect((26, 42, 43), box.move(4, 6), 4)
            rect(roof, box, 4)
            rect((222, 232, 221), box.inflate(-12, -12), 3)
            if kind == 'medkit':
                rect((207, 77, 79), (box.centerx-4, box.centery-12, 8, 24))
                rect((207, 77, 79), (box.centerx-12, box.centery-4, 24, 8))
            elif kind == 'ammo':
                for offset in (-8, 0, 8):
                    pygame.draw.rect(screen, (64, 49, 37), (box.centerx+offset-2, box.centery-10, 4, 20), border_radius=2)
            else:
                rect((47, 92, 120), (box.centerx-12, box.centery-11, 24, 22), 3)
                text('⚡', box.centerx-7, box.centery-9, 14, (239, 226, 135))
        text(label, box.x, box.bottom+3, 12, roof if kind != 'parking' else (205, 216, 206))
    for x, y in [(1, 2), (1, 6), (8, 1), (20, 1), (16, 15), (16, 18), (27, 15), (9, 18)]:
        px, py = OX+x*TILE+16, OY+y*TILE+16
        pygame.draw.circle(screen, (26, 45, 38), (px+4, py+6), 18)
        pygame.draw.circle(screen, (54, 97, 67), (px, py), 17)
        pygame.draw.circle(screen, (72, 115, 76), (px-5, py-5), 10)
    # Lockers and evacuation arrows give the roads the feel of school hallways.
    for x, y in [(4, 9), (8, 9), (16, 9), (20, 9), (24, 9)]:
        rect((80, 121, 137), (OX+x*TILE, OY+y*TILE+4, 23, 24), 2)
        pygame.draw.line(screen, (161, 206, 216), (OX+x*TILE+5, OY+y*TILE+7), (OX+x*TILE+5, OY+y*TILE+25), 1)
    text('← SAFE EXIT', OX+4*TILE, OY+10*TILE+6, 12, (221, 232, 207))
    text('EAST CAMPUS', OX+750, OY+18, 12, (180, 192, 173))


def draw_ambient_lights():
    """Subtle pools of campus light keep important areas readable at night."""
    lights = pygame.Surface((COLS*TILE, ROWS*TILE), pygame.SRCALPHA)
    for x, y, radius, color in ((3, 17, 82, (76, 226, 170, 34)), (3, 13, 56, (226, 92, 86, 24)),
                                (26, 4, 52, (231, 181, 81, 24)), (14, 18, 54, (74, 161, 220, 28))):
        pygame.draw.circle(lights, color, (int(x*TILE+TILE/2), int(y*TILE+TILE/2)), radius)
    screen.blit(lights, (OX, OY))


def draw_actor(a):
    x, y = int(OX+a.x), int(OY+a.y)
    if a is game.controlled_actor() and a.alive:
        pygame.draw.circle(screen, (244, 195, 109), (x, y+5), 24, 2)
        text('YOU', x-12, y-39, 12, (244, 195, 109))
    if not a.alive:
        body = pygame.transform.smoothscale(ACTOR_IMAGES[a.role], (32, 22))
        body.set_alpha(125)
        screen.blit(body, body.get_rect(center=(x, y+5)))
        pygame.draw.line(screen, (229, 87, 82), (x-16, y-9), (x+16, y+12), 2)
        text('DOWN', x-18, y+12, 12, (233, 134, 131))
        return
    colors = {'Leader': (76, 162, 221), 'Rescuer': (232, 168, 75),
              'Medic': (108, 224, 193), 'Defender': (239, 119, 94),
              'Scout': (244, 208, 104),
              'Student': (174, 140, 224), 'Zombie': (138, 171, 90)}
    color = colors[a.role]
    pygame.draw.ellipse(screen, (23, 37, 34), (x-13, y+4, 26, 13))
    if a.moving:
        # Small dust puffs communicate movement without changing the stable
        # sprite orientation used by the Scout.
        pygame.draw.circle(screen, (119, 130, 112), (x-10, y+10), 2)
        pygame.draw.circle(screen, (119, 130, 112), (x+9, y+11), 2)
    if a.role == 'Rescuer' and selected:
        pygame.draw.circle(screen, (245, 201, 120), (x, y), 21, 2)
    # The rendered characters are upright 3D cutouts.  The former Kenney sprites
    # were top-down and needed directional rotation; applying that rule here made
    # people appear to lie down whenever they moved sideways.
    body = ACTOR_IMAGES[a.role]
    if a.flash:
        body = body.copy()
        body.fill((105, 105, 105, 0), special_flags=pygame.BLEND_RGB_ADD)
    # The Scout frequently pauses to scan a sector. Keep that scan pose stable
    # so it never looks like it is vibrating while waiting for new information.
    bob = int(math.sin(game.elapsed * 14) * 2) if a.moving and a.role != 'Scout' else 0
    screen.blit(body, body.get_rect(midbottom=(x, y + 16 + bob)))
    if a.role == 'Rescuer':
        pygame.draw.circle(screen, (252, 233, 187), (x, y + bob), 3)
    rect((22, 32, 34), (x-17, y-28, 34, 4), 2)
    rect((224, 104, 100) if a.hp < 40 else GREEN, (x-17, y-28, int(34*a.hp/100), 4), 2)
    text(a.role, x-23, y+21, 12, color)
    if a.role == 'Student' and a.state == 'Waiting':
        radius = 9 + int((math.sin(game.elapsed * 5) + 1) * 2)
        pygame.draw.circle(screen, (241, 99, 95), (x, y-42), radius, 2)
        text('HELP', x-17, y-49, 12, (255, 211, 154))
    if debug:
        text(a.state, x-23, y+36, 12)


buttons = [(pygame.Rect(944, 370+i*43, 232, 35), order, label)
           for i, (order, label) in enumerate([('Rescue', '[E]  Rescue student'), ('Follow', '[F]  Follow Commander'), ('Hold', '[H]  Hold position')])]


def draw_fog():
    fog = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    fog.fill((5, 13, 20, 125 if REALISTIC_CAMPUS else 188))
    for y in range(ROWS):
        for x in range(COLS):
            # The fenced perimeter and building interiors are not searchable
            # terrain, so they should never look like unexplored campus fog.
            if walkable((x, y)) and (x, y) not in game.revealed:
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


def draw_threat_markers():
    """Show the exact person an active zombie is hunting."""
    actors_by_name = {actor.name: actor for actor in game.actors}
    pulse = 23 + int((math.sin(game.elapsed * 7) + 1) * 3)
    for zombie in game.zombies:
        target = actors_by_name.get(zombie.target_name)
        if not zombie.alive or not target or not target.alive or target.state == 'Rescued':
            continue
        x, y = int(OX + target.x), int(OY + target.y)
        # A compact warning reticle reads as a combat cue without hiding the sprite.
        pygame.draw.circle(screen, (238, 93, 88), (x, y), pulse, 2)
        pygame.draw.line(screen, (238, 93, 88), (x-11, y-30), (x+11, y-30), 2)
        text('ZOMBIE TARGET', x-38, y-47, 12, (250, 148, 136))


def draw_action_effects():
    """Short, role-specific cues that make autonomous actions readable."""
    actors = {actor.name: actor for actor in game.actors}
    pulse = int((math.sin(game.elapsed * 12) + 1) * 2)
    # A short amber tracer makes the Defender's shots visible without clutter.
    defender, target = game.defender, game.defender_target
    if defender.state == 'Engage' and defender.cooldown > .35 and target and target.alive:
        start = (int(OX + defender.x), int(OY + defender.y - 6))
        end = (int(OX + target.x), int(OY + target.y))
        pygame.draw.line(screen, (248, 211, 112), start, end, 2)
        pygame.draw.circle(screen, (255, 235, 168), start, 5 + pulse)
    # Healing is visible as a calm medical ring around the current patient.
    if game.medic.task.startswith('Heal '):
        patient = actors.get(game.medic.task.removeprefix('Heal '))
        if patient and patient.alive and math.dist(game.medic.pos, patient.pos) < 45:
            x, y = int(OX + patient.x), int(OY + patient.y)
            pygame.draw.circle(screen, (103, 235, 194), (x, y), 24 + pulse, 2)
            text('+', x-4, y-44, 18, (151, 248, 214))
    # An escort tether explains who is being extracted without adding a panel.
    if game.escort_student and game.escort_student.alive:
        student, rescuer = game.escort_student, game.rescuer
        start, end = (int(OX + rescuer.x), int(OY + rescuer.y)), (int(OX + student.x), int(OY + student.y))
        pygame.draw.line(screen, (244, 197, 112), start, end, 1)
        pygame.draw.circle(screen, (244, 197, 112), end, 23 + pulse, 2)
    # Bite arcs show that a zombie is actively dealing damage, not merely close.
    for zombie in game.zombies:
        target = actors.get(zombie.target_name)
        if zombie.alive and zombie.state == 'Attack' and target and target.alive:
            x, y = int(OX + target.x), int(OY + target.y)
            pygame.draw.arc(screen, (240, 89, 84), (x-28, y-28, 56, 56), .3, 2.8, 3)
    # A pickup leaves a quick collection pulse after it disappears.
    for pickup in game.pickups:
        if pickup.pulse > 0:
            x, y = int(OX + pickup.x), int(OY + pickup.y)
            radius = 12 + int((.45-pickup.pulse) * 45)
            pygame.draw.circle(screen, (121, 226, 196), (x, y), radius, 2)


def draw_world():
    """Render the campus layer; reused by normal and full-map views."""
    draw_map()
    if debug:
        for role, route in game.routes.items():
            points = [(OX+center(p)[0], OY+center(p)[1]) for p in route]
            if len(points) > 1:
                pygame.draw.lines(screen, (220, 121, 101) if role == 'Zombie' else (103, 211, 224), False, points, 2)
    draw_ambient_lights()
    draw_fog()
    for pickup in game.pickups:
        draw_pickup(pickup)
    visible_actors = [a for a in game.actors if a.role not in ('Student', 'Zombie') or game.discovered[a.name]]
    draw_threat_markers()
    draw_action_effects()
    for actor in sorted(visible_actors, key=lambda actor: actor.y):
        draw_actor(actor)


def draw_full_map():
    """Use the whole screen for the rescue area without changing simulation coordinates."""
    global screen, OX, OY
    display, old_ox, old_oy = screen, OX, OY
    campus = pygame.Surface((COLS*TILE, ROWS*TILE))
    screen, OX, OY = campus, 0, 0
    draw_world()
    screen, OX, OY = display, old_ox, old_oy
    scale = min(WIDTH/(COLS*TILE), HEIGHT/(ROWS*TILE))
    size = (int(COLS*TILE*scale), int(ROWS*TILE*scale))
    left, top = (WIDTH-size[0])//2, (HEIGHT-size[1])//2
    display.fill((9, 18, 23))
    display.blit(pygame.transform.smoothscale(campus, size), (left, top))
    overlay = pygame.Surface((WIDTH, 64), pygame.SRCALPHA)
    overlay.fill((8, 17, 23, 206)); display.blit(overlay, (0, 0))
    text('CAMPUS / CRISIS', 22, 14, 24)
    text(game.mission['title'].upper()+'  |  '+game.mission['objective'], 22, 43, 12, MUTED)
    text(f'{game.rescued_count:02}/{len(game.students):02} STUDENTS  •  {int(game.time)//60:02}:{int(game.time)%60:02}', 805, 22, 16, GREEN)
    text('[F4] COMMAND PANEL', 1015, 45, 12, MUTED)


def draw_state_overlay():
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((8, 17, 23, 200)); screen.blit(overlay, (0, 0))
    rect((28, 45, 51), (300, 257, 600, 220), 14)
    title = game.result or 'Mission paused'
    text(title.upper(), 338, 290, 32, GREEN if title == 'Mission complete' else INK)
    report = f"Rescued: {game.rescued_count}/{len(game.students)}   Kills: {game.stats['zombies_neutralized']}   Medkits used: {game.stats['medkits_used']}"
    text(report, 338, 348, 16, MUTED)
    text(f"Fuel: {game.fuel}/{game.fuel_required}   Ammo left: {game.ammo}   Time left: {int(game.time)}s", 338, 378, 16, MUTED)
    if campaign_notice:
        text(campaign_notice, 338, 405, 14, GREEN if game.result == 'Mission complete' else (244, 195, 109))
    text('R  Start next rescue  |  X Reset campaign  |  Esc Quit' if game.result else 'P Resume  |  R Restart  |  Esc Quit', 338, 438, 16)


def draw():
    if screen_state != 'game':
        draw_menu()
        return
    if full_map:
        draw_full_map()
        if paused or game.result:
            draw_state_overlay()
        return
    screen.fill((16, 26, 32))
    text('CAMPUS / CRISIS', 22, 17, 32)
    text('FIRST RESPONSE     /     PLAYABLE PROTOTYPE 01', 24, 58, 12, MUTED)
    text(f'{game.rescued_count:02}/{len(game.students):02}  STUDENTS EXTRACTED', 555, 29, 16, GREEN)
    text(f'YOU: {player_role.upper()}', 555, 51, 12, (244, 195, 109))
    text(f'{int(game.time)//60:02}:{int(game.time)%60:02}', 811, 22, 32, (243, 190, 119))
    rect((76, 101, 107) if audio_muted else (51, 92, 81), mute_button, 6)
    text('MUTED [M]' if audio_muted else 'SOUND ON [M]', 1061, 53, 12, INK)
    draw_world()
    rect(PANEL, (932, 94, 256, 640), 8)
    rect(PANEL_EDGE, (932, 94, 256, 640), 8, 1)
    rect((29, 54, 58), (932, 94, 256, 48), 8)
    text('MISSION CONTROL', 946, 110, 18, (220, 235, 230))
    text(f"SECTOR {game.campaign_level}  /  3", 946, 140, 12, (244, 195, 109))
    text(game.mission['title'].upper(), 946, 157, 14, GREEN)
    text(game.mission['objective'], 946, 175, 12, MUTED)
    text(f"{len(game.students)} students  |  {len(game.zombies)} zombies  |  {int(game.time)} sec", 946, 191, 12, MUTED)
    for i, a in enumerate((game.leader, game.rescuer, game.medic, game.defender, game.scout, game.student)):
        y = 208+i*21
        text(a.role, 946, y, 14)
        rect((46, 60, 63), (1040, y+5, 100, 8), 4)
        rect(GREEN if a.hp > 35 else (237, 119, 110), (1040, y+5, int(a.hp), 8), 4)
    intel = 'STUDENT LOCATED' if game.discovered['Student'] else 'SCOUT SEARCHING FOR STUDENT'
    text(intel, 946, 327, 12, GREEN if game.discovered['Student'] else (244, 208, 104))
    text('COMMAND PANEL' if player_role == 'Commander' else f'PLAYER CONTROLS: {player_role.upper()}', 946, 342, 12, (244, 195, 109))
    if player_role == 'Commander':
        for bounds, order, label in buttons:
            rect((54, 100, 90) if game.order == order else (31, 46, 55), bounds, 5)
            rect(GREEN if game.order == order else (52, 75, 80), bounds, 5, 1)
            text(label, bounds.x+12, bounds.y+7, 14)
    else:
        action_help = {
            'Rescuer': '[E] Start escort / collect nearby item',
            'Medic': '[E] Treat nearby teammate / collect item',
            'Defender': '[E] Engage zombie / collect ammo',
            'Scout': '[E] Scan nearby sector / collect item',
        }[player_role]
        rect((31, 46, 55), (944, 370, 232, 72), 5)
        text(action_help, 956, 385, 12, INK)
        text('WASD move  |  Shift run', 956, 412, 12, MUTED)
    text('AI TASK ALLOCATION', 946, 513, 14, GREEN)
    text(f'Scout: {game.scout.task}  [{game.scout.task_score}]', 946, 535, 12, MUTED)
    text(f'Medic: {game.medic.task}  [{game.medic.task_score}]', 946, 553, 12, MUTED)
    text(f'Defender: {game.defender.task}  [{game.defender.task_score}]', 946, 571, 12, MUTED)
    text(f'Medkits: {game.medkits}  |  Ammo: {game.ammo}', 946, 589, 12, (126, 224, 195))
    text(f'Fuel secured: {game.fuel}/{game.fuel_required}', 946, 604, 12, (70, 160, 215))
    active_targets = [f'{z.name} -> {z.target_name}' for z in game.zombies if z.target_name]
    text('THREAT: '+(', '.join(active_targets) if active_targets else 'No active pursuit'), 946, 619, 12, (244, 143, 133))
    text('FIELD COMMS', 946, 636, 14, GREEN)
    y = 659
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
    controls = ('WASD Move  |  Shift Run  |  Space Strike  |  E Rescue/Command  |  F4 Full Map  |  P Pause  |  R Restart'
                if player_role == 'Commander' else 'WASD Move  |  Shift Run  |  E Context Action  |  F4 Full Map  |  P Pause  |  R Restart')
    text(controls, 22, 742, 12, MUTED)
    if game.shove_cooldown > .4:
        pygame.draw.circle(screen, (221, 233, 202), (int(OX+game.leader.x), int(OY+game.leader.y)), 38, 2)
    if paused or game.result:
        draw_state_overlay()


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
        text(f"CAMPAIGN: Sector {campaign['unlocked_sector']} / 3   |   Successful rescues: {campaign['completed']}", 319, 315, 13, (244, 195, 109))
        model_status = (f"ML MODEL: trained on {adaptive_data['missions']} missions  |  Training fit: {adaptive_data['accuracy']:.0%}"
                        if adaptive_data['trained'] else f"ML MODEL: collecting data ({adaptive_data['missions']}/15 missions)")
        text(model_status, 319, 340, 13, MUTED)
        text('ADAPTIVE: '+adaptive_plan['label']+' — '+adaptive_plan['reason'], 319, 365, 12, GREEN)
        base_time = {'Easy': 300, 'Normal': 240, 'Hard': 180}[difficulty]
        text(f"PLAYER SETTING: {difficulty}   |   ML adjustment: {adaptive_plan['label']}", 319, 391, 12, INK)
        text('Each campus incident varies its students, zombies, resources, objective, and time limit.', 319, 415, 14, MUTED)
        text('CHOOSE DIFFICULTY', 319, 438, 14, MUTED)
        for index, label in enumerate(('Easy', 'Normal', 'Hard')):
            menu_button('difficulty_'+label, label+('  ✓' if difficulty == label else ''), (319+index*170, 463, 150, 38), difficulty == label)
        menu_button('deploy', 'CHOOSE PLAYABLE ROLE  [ENTER]', (319, 525, 330, 42), True)
        menu_button('back', 'BACK  [ESC]', (664, 525, 180, 42))
        menu_button('reset_campaign', 'RESET CAMPAIGN  [X]', (319, 580, 330, 38))
    elif screen_state == 'role_select':
        text('CHOOSE YOUR ROLE', 319, 270, 24, GREEN)
        text('You control this role. The rest of the rescue team uses AI decisions.', 319, 302, 14, MUTED)
        roles = (
            ('Commander', 'Coordinate the team and issue rescue orders.'),
            ('Rescuer', 'Reach located students and escort them to safety.'),
            ('Medic', 'Move to injured teammates and use medkits.'),
            ('Defender', 'Protect the team and engage visible zombies.'),
            ('Scout', 'Explore fog and scan nearby campus sectors.'),
        )
        for index, (role, description) in enumerate(roles):
            y = 338 + index*43
            active = player_role == role
            menu_button('role_'+role, f'[{index+1}]  {role.upper()}  —  {description}', (319, y, 550, 35), active)
        menu_button('launch_role', f'DEPLOY AS {player_role.upper()}  [ENTER]', (319, 565, 330, 42), True)
        menu_button('back', 'BACK', (664, 565, 180, 42))
    else:
        text('HOW TO PLAY', 319, 290, 24, GREEN)
        text('Choose Commander or a field role before each mission.', 319, 332, 16, MUTED)
        text('WASD moves your role. E performs its context action.', 319, 364, 16, MUTED)
        text('Resources help the team, but every Safe Zone tile releases an escort.', 319, 396, 16, MUTED)
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
                screen_state = 'role_select'
            elif screen_state == 'role_select' and event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                player_role = ('Commander', 'Rescuer', 'Medic', 'Defender', 'Scout')[event.key-pygame.K_1]
            elif screen_state == 'role_select' and event.key == pygame.K_RETURN:
                start_campaign_mission(); screen_state = 'game'
            elif screen_state == 'briefing' and event.key == pygame.K_x:
                reset_campaign()
            elif screen_state != 'game':
                continue
            elif event.key == pygame.K_m:
                audio_muted = not audio_muted
            elif event.key == pygame.K_r:
                start_campaign_mission()
            elif event.key == pygame.K_x and game.result:
                reset_campaign(); screen_state = 'menu'
            elif event.key == pygame.K_p:
                paused = not paused
            elif event.key == pygame.K_F3:
                debug = not debug
            elif event.key == pygame.K_F4:
                full_map = not full_map
            elif event.key == pygame.K_TAB:
                selected = not selected
            elif not paused:
                if event.key in (pygame.K_SPACE, pygame.K_e):
                    if player_role == 'Commander':
                        game.shove() if event.key == pygame.K_SPACE else game.command('Rescue')
                    elif event.key == pygame.K_e:
                        game.player_action()
                elif player_role == 'Commander' and selected and event.key in (pygame.K_f, pygame.K_h):
                    game.command({pygame.K_e: 'Rescue', pygame.K_f: 'Follow', pygame.K_h: 'Hold'}[event.key])
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if screen_state != 'game':
                for key, bounds in menu_buttons.items():
                    if bounds.collidepoint(event.pos):
                        if key == 'briefing': screen_state = 'briefing'
                        elif key == 'howto': screen_state = 'howto'
                        elif key == 'quit': running = False
                        elif key == 'back': screen_state = 'menu'
                        elif key == 'deploy': screen_state = 'role_select'
                        elif key == 'launch_role': start_campaign_mission(); screen_state = 'game'
                        elif key == 'reset_campaign': reset_campaign()
                        elif key.startswith('difficulty_'): difficulty = key.removeprefix('difficulty_')
                        elif key.startswith('role_'): player_role = key.removeprefix('role_')
            elif not paused:
                mx, my = event.pos
                if mute_button.collidepoint(event.pos):
                    audio_muted = not audio_muted
                    continue
                if math.dist((mx-OX, my-OY), game.rescuer.pos) < 28:
                    selected = True
                for bounds, order, _ in buttons:
                    if player_role == 'Commander' and selected and bounds.collidepoint(event.pos):
                        game.command(order)
    keys = pygame.key.get_pressed()
    if screen_state == 'game' and not paused:
        game.update(dt, (int(keys[pygame.K_d])-int(keys[pygame.K_a]), int(keys[pygame.K_s])-int(keys[pygame.K_w])), keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
        if game.result and not mission_outcome_processed:
            mission_outcome_processed = True
            if game.result == 'Mission complete':
                previous_sector = campaign['unlocked_sector']
                campaign = record_completion(campaign)
                campaign_notice = (f"Sector {campaign['unlocked_sector']} unlocked: the next rescue intensifies."
                                   if campaign['unlocked_sector'] > previous_sector else 'All campaign sectors are unlocked. Keep improving your rescue record.')
            else:
                campaign_notice = f"Sector {game.campaign_level} remains active. Adjust your plan and retry."
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
