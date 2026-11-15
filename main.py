"""Campus Crisis: playable Pygame vertical slice using CC0 Kenney artwork."""
import argparse
import math
import os
import random
from array import array
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--smoke-test', action='store_true', help='Render 120 frames without a window')
parser.add_argument('--screenshot', type=str, help='Save a frame and exit')
parser.add_argument('--preview-game', action='store_true', help='Open directly into a mission for visual review')
parser.add_argument('--state', type=str, help='Start on a given menu screen (menu/briefing/role_select/howto) for visual review')
parser.add_argument('--panel-tab', type=str, help='Open the Mission Control panel on a given tab (status/tactics/log)')
args = parser.parse_args()
HEADLESS = bool(args.smoke_test or args.screenshot)
if HEADLESS:
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
else:
    # Use the monitor's real pixels (Windows otherwise stretches a blurry
    # low-resolution window under display scaling) and scale the canvas smoothly.
    os.environ.setdefault('SDL_WINDOWS_DPI_AWARENESS', 'permonitorv2')
    os.environ.setdefault('SDL_RENDER_SCALE_QUALITY', 'linear')
import pygame
from world import Game, TILE, COLS, ROWS, BUILDINGS, SAFE, LANDMARKS, center
from fog import CloudFog
from sprites import build_character_sprites
from adaptive import recommend, report
from campaign import load_progress, record_completion, reset_progress

pygame.mixer.pre_init(44100, -16, 1, 512)
pygame.init()
WIDTH, HEIGHT = 1200, 760
# The game is laid out on a fixed 1200x760 canvas. SCALED stretches it over the
# whole monitor (or a resizable window) keeping its proportions, and maps mouse
# clicks back onto the canvas. It starts fullscreen; F11 switches to a window.
screen = (pygame.display.set_mode((WIDTH, HEIGHT)) if HEADLESS else
          pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.RESIZABLE | pygame.FULLSCREEN))
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
active_panel_tab = 'status'   # Mission Control tabs: status / tactics / log
PANEL_TABS = {}               # clickable tab-strip rects, re-registered each frame
TOASTS = []                   # map toasts: newest first, max 3 visible
CRITICAL_ACTORS = set()       # teammates whose critical toast is alive
LAST_TARGETS = {}             # zombie name -> last lock-on target (transition trigger)
STUDENT_LOCATED_SEEN = False
SEEN_PICKUPS = set()
last_log_message = ''
audio_muted = False
campaign_notice = ''
mission_outcome_processed = False
mute_button = pygame.Rect(1052, 45, 130, 32)
if args.preview_game:
    screen_state = 'game'
if args.state:
    screen_state = args.state
if args.panel_tab:
    active_panel_tab = args.panel_tab
ASSET_ROOT = Path(__file__).parent / 'assets' / 'kenney-top-down-shooter'
REALISTIC_MAP_PATH = Path(__file__).parent / 'assets' / 'generated' / 'campus-game-map-v4.png'


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


def clear_mission_trackers():
    """Toast/transition trackers are per-mission state."""
    global TOASTS, CRITICAL_ACTORS, LAST_TARGETS, STUDENT_LOCATED_SEEN, SEEN_PICKUPS
    TOASTS, CRITICAL_ACTORS, LAST_TARGETS = [], set(), {}
    STUDENT_LOCATED_SEEN, SEEN_PICKUPS = False, set()


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
    clear_mission_trackers()


def reset_campaign():
    """Clear saved sectors and prepare a fresh Sector 1 mission."""
    global campaign, game, campaign_notice, mission_outcome_processed
    campaign = reset_progress()
    game = Game(campaign_level=1, player_role=player_role)
    campaign_notice, mission_outcome_processed = 'Campaign reset. Sector 1 is ready.', False
    clear_mission_trackers()


GRASS = load_asset('PNG/Tiles/tile_01.png', (TILE, TILE))
REALISTIC_CAMPUS = (pygame.transform.smoothscale(pygame.image.load(REALISTIC_MAP_PATH).convert(), (COLS*TILE, ROWS*TILE))
                    if REALISTIC_MAP_PATH.exists() else None)
# Painted semi-realistic characters, drawn in code (see sprites.py). Each role
# has a standing frame and two walking steps, facing right and mirrored left.
CHARACTER_SPRITES = build_character_sprites()
ACTOR_IMAGES = {role: frames['right'][0] for role, frames in CHARACTER_SPRITES.items()}
FACING_LEFT = {}  # which way each character last walked, so it faces that way


def character_frame(a):
    """The sprite frame for a character: facing its walking direction, stepping while it moves."""
    if a.moving and abs(a.facing[0]) > .6:  # only clear sideways movement turns a character
        FACING_LEFT[a.name] = a.facing[0] < 0
    frames = CHARACTER_SPRITES[a.role]['left' if FACING_LEFT.get(a.name) else 'right']
    return frames[1 + int(game.elapsed * 6) % 2] if a.moving else frames[0]


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


# ---------------------------------------------------------------------------
# UI redesign toolkit: shared accents, text clipping and drawn icons.
# ---------------------------------------------------------------------------
AMBER, DANGER = (244, 195, 109), (218, 80, 77)
AMBER_TEXT, DANGER_TEXT = (244, 208, 104), (250, 148, 136)
MENU_CARD = pygame.Rect(244, 84, 712, 600)   # every menu screen shares one card


def clip_text(value, x, y, size, color, max_width):
    """Draw text truncated with an ellipsis so it never overflows its column."""
    font, value = fonts[size], str(value)
    if font.size(value)[0] > max_width:
        while value and font.size(value + '…')[0] > max_width:
            value = value[:-1]
        value += '…'
    text(value, x, y, size, color)


def wrap_line(line, max_chars):
    """Split a log line into screen-width-sized chunks, newest message first."""
    words, lines, current = line.split(), [], ''
    for word in words:
        if current and len(current + word) > max_chars:
            lines.append(current.rstrip())
            current = ''
        current += word + ' '
    if current:
        lines.append(current.rstrip())
    return lines


def draw_icon_person(x, y, color=(238, 238, 228)):
    pygame.draw.circle(screen, color, (x, y - 3), 3)
    pygame.draw.polygon(screen, color, [(x - 3, y + 6), (x + 3, y + 6), (x + 2, y), (x - 2, y)])


def draw_icon_skull(x, y, color=(236, 90, 84)):
    pygame.draw.circle(screen, color, (x, y - 2), 4)
    pygame.draw.rect(screen, color, (x - 2, y + 1, 4, 4), border_radius=1)
    pygame.draw.circle(screen, (16, 26, 32), (x - 1, y - 2), 1)
    pygame.draw.circle(screen, (16, 26, 32), (x + 1, y - 2), 1)


def draw_icon_clock(x, y, color=AMBER):
    pygame.draw.circle(screen, color, (x, y), 5, 1)
    pygame.draw.line(screen, color, (x, y), (x, y - 3), 1)
    pygame.draw.line(screen, color, (x, y), (x + 2, y + 1), 1)


def draw_icon_medkit(x, y):
    rect((218, 80, 77), (x - 7, y - 5, 14, 11), 2)
    rect((248, 242, 226), (x - 1, y - 3, 2, 7))
    rect((248, 242, 226), (x - 3, y - 1, 7, 3))


def draw_icon_ammo(x, y, color=(234, 180, 69)):
    for offset in (-4, 0, 4):
        rect((64, 49, 37), (x + offset - 1, y - 5, 3, 10), 1)
        rect(color, (x + offset - 1, y - 5, 3, 3), 1)


def draw_icon_fuel(x, y, color=(70, 160, 215)):
    rect((36, 53, 58), (x - 5, y - 5, 10, 11), 2)
    rect(color, (x - 3, y - 3, 6, 7), 1)
    rect(color, (x + 1, y - 7, 3, 3))


def draw_star(cx, cy, radius, color):
    points = []
    for i in range(10):
        ray = radius if i % 2 == 0 else radius * .45
        angle = -math.pi / 2 + i * math.pi / 5
        points.append((cx + ray * math.cos(angle), cy + ray * math.sin(angle)))
    pygame.draw.polygon(screen, color, points)


def draw_warning_icon(cx, cy, color=DANGER_TEXT):
    pygame.draw.polygon(screen, color, [(cx, cy - 6), (cx + 6, cy + 5), (cx - 6, cy + 5)])
    rect((16, 26, 32), (cx - 1, cy - 2, 2, 4))
    rect((16, 26, 32), (cx - 1, cy + 3, 2, 2))


def draw_divider(y, x=946, width=228):
    rect(PANEL_EDGE, (x, y, width, 1))


# ---------------------------------------------------------------------------
# Map toasts: urgent events appear just under the map's top edge, so the panel
# never has to carry transient alarms. Max 3 visible, newest on top.
# ---------------------------------------------------------------------------
def spawn_toast(message, color, persist=False, key=None, sound='radio'):
    global TOASTS
    TOASTS.insert(0, {'text': message, 'color': color, 'born': pygame.time.get_ticks(),
                      'persist': persist, 'key': key})
    while len(TOASTS) > 3:  # evict the oldest transient; never evict a persistent alert
        for i, toast in enumerate(TOASTS):
            if not toast['persist']:
                TOASTS.pop(i)
                break
        else:
            TOASTS.pop()
    play_sound(sound)


def drop_toast(key):
    global TOASTS
    TOASTS = [toast for toast in TOASTS if toast['key'] != key]


def update_toasts():
    """Spawn toasts on state transitions; retire persistent ones when resolved."""
    global STUDENT_LOCATED_SEEN
    team = (game.leader, game.rescuer, game.medic, *game.defenders, game.scout, game.student)
    for a in team:
        critical = a.alive and a.hp < .35 * game.max_hp(a)
        if critical and a.name not in CRITICAL_ACTORS:
            CRITICAL_ACTORS.add(a.name)
            spawn_toast(f'{actor_label(a).upper()} IS CRITICAL', DANGER_TEXT, True, ('critical', a.name), 'hit')
        elif not critical and a.name in CRITICAL_ACTORS:
            CRITICAL_ACTORS.discard(a.name)
            drop_toast(('critical', a.name))
    actors_by_name = {a.name: a for a in game.actors}
    for z in game.zombies:
        key = ('lockon', z.name)
        target = actors_by_name.get(z.target_name)
        valid = z.alive and target and target.alive and target.state != 'Rescued'
        if valid and LAST_TARGETS.get(z.name) != z.target_name:
            spawn_toast(f'{z.name} → {z.target_name}', DANGER_TEXT, True, key, 'hit')
        elif not valid:
            drop_toast(key)
        LAST_TARGETS[z.name] = z.target_name
    if game.discovered['Student'] and not STUDENT_LOCATED_SEEN:
        STUDENT_LOCATED_SEEN = True
        spawn_toast('STUDENT LOCATED', GREEN, False, ('located',), 'radio')
    for i, pickup in enumerate(game.pickups):
        if pickup.collected and i not in SEEN_PICKUPS:
            SEEN_PICKUPS.add(i)
            label = {'medkit': 'MEDKIT COLLECTED', 'ammo': 'AMMO COLLECTED', 'fuel': 'FUEL COLLECTED'}[pickup.kind]
            color = {'medkit': (218, 80, 77), 'ammo': (234, 180, 69), 'fuel': (70, 160, 215)}[pickup.kind]
            spawn_toast(label, color, False, ('pickup', i), 'pickup')


def draw_toasts():
    """Toast strip pinned under the map's top edge; transients fade, persistent wait."""
    now = pygame.time.get_ticks()
    for i, toast in enumerate(list(TOASTS)):
        if i >= 3:
            break
        age = (now - toast['born']) / 1000
        if not toast['persist'] and age > 4:
            TOASTS.remove(toast)
            continue
        alpha = 215
        if not toast['persist'] and age > 3.4:
            alpha = max(0, int(215 * (4 - age) / .6))
        if alpha <= 0:
            continue
        box = pygame.Surface((240, 24), pygame.SRCALPHA)
        pygame.draw.rect(box, (12, 25, 31, alpha), (0, 0, 240, 24), border_radius=6)
        pygame.draw.rect(box, (*toast['color'], alpha), (0, 0, 4, 24), border_radius=2)
        rendered = fonts[12].render(toast['text'], True, toast['color'])
        rendered.set_alpha(alpha)
        box.blit(rendered, (12, 6))
        screen.blit(box, (OX + 12, OY + 8 + i * 28))


# ---------------------------------------------------------------------------
# Menu atmosphere: layered backdrop, title glitch, role lineup, campaign strip.
# ---------------------------------------------------------------------------
def build_glow(color, radius, peak_alpha=26):
    """Soft radial light pool; brightest at the centre, fading to nothing."""
    surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for step in range(12):
        share = step / 11
        pygame.draw.circle(surf, (*color, int(peak_alpha * share * share)),
                           (radius, radius), max(2, int(radius * (1 - step / 12))))
    return surf


random.seed(11)
GLOWS = ((build_glow((36, 160, 118), 300, 30), (200, 170), 1.1, .9),
         (build_glow((30, 110, 150), 240, 24), (900, 540), -.9, 1.2),
         (build_glow((140, 120, 60), 210, 18), (640, 60), .7, -1.1))
FOG_MOTES = [{'x': random.uniform(0, WIDTH), 'y': random.uniform(0, HEIGHT),
              'v': random.uniform(9, 24), 'r': int(random.uniform(2, 5)),
              'a': random.randint(22, 52), 'phase': random.uniform(0, 6.3)} for _ in range(34)]
SCAN_OVERLAY = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
for scan_y in range(0, HEIGHT, 4):
    pygame.draw.line(SCAN_OVERLAY, (120, 220, 190, 9), (0, scan_y), (WIDTH, scan_y))
VIGNETTE = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
for vignette_step in range(12):
    inset = vignette_step * 12
    pygame.draw.rect(VIGNETTE, (3, 8, 12, 9 + vignette_step * 2),
                     (inset, inset, WIDTH - inset * 2, HEIGHT - inset * 2), width=14, border_radius=40)
LINEUP = (('Leader', 'COMMAND'), ('Rescuer', 'RESCUE'), ('Medic', 'HEAL'),
          ('Defender', 'DEFEND'), ('Scout', 'SCOUT'))


def draw_menu_backdrop(t):
    """Base darkness, drifting light pools, rising motes, scan lines, vignette."""
    screen.fill((12, 23, 29))
    for surf, (base_x, base_y), vx, vy in GLOWS:
        x = base_x + math.sin(t * vx) * 40
        y = base_y + math.cos(t * vy) * 30
        screen.blit(surf, (x - surf.get_width() // 2, y - surf.get_height() // 2))
    motes = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for mote in FOG_MOTES:
        y = (mote['y'] - t * mote['v']) % (HEIGHT + 20) - 10
        x = (mote['x'] + math.sin(t * .5 + mote['phase']) * 18) % WIDTH
        pygame.draw.circle(motes, (110, 220, 185, mote['a']), (int(x), int(y)), mote['r'])
    screen.blit(motes, (0, 0))
    offset = int(t * 26) % 4
    screen.blit(SCAN_OVERLAY, (0, offset - HEIGHT))
    screen.blit(SCAN_OVERLAY, (0, offset))
    screen.blit(VIGNETTE, (0, 0))


def draw_menu_card():
    rect((24, 38, 45), MENU_CARD, 14)
    rect((74, 129, 117), MENU_CARD, 14, 2)


def draw_menu_title(x, y):
    """CAMPUS / CRISIS with a brief RGB-split glitch on the slash every few seconds."""
    t = pygame.time.get_ticks() / 1000
    left, slash, right = 'CAMPUS ', '/', ' CRISIS'
    slash_x = x + fonts[48].size(left)[0]
    phase = t % 3.4
    if phase < .16:  # glitch window: channel-split copies with a jitter offset
        off = 2 if int(phase * 30) % 2 else -2
        text(left, x, y, 48)
        text(right, slash_x + fonts[48].size(slash)[0] + off // 2, y, 48)
        text(slash, slash_x + off - 2, y + off, 48, (236, 90, 84))
        text(slash, slash_x + off + 2, y - off, 48, (110, 231, 190))
        text(slash, slash_x + off // 2, y, 48)
    else:
        text(left, x, y, 48)
        text(slash, slash_x, y, 48)
        text(right, slash_x + fonts[48].size(slash)[0], y, 48)


def draw_scan_line(x, y, width, t):
    """Thin pulsing divider with a bright segment sweeping left to right."""
    pulse = .25 + .2 * math.sin(t * 2)
    dim = tuple(int(channel * pulse) for channel in GREEN)
    rect(dim, (x, y, width, 1))
    sweep = int((t * 90) % (width + 80)) - 40
    rect(GREEN, (x + sweep, y, 60, 1))


def draw_lineup(t):
    """The five playable roles on their colour rings, gently idling."""
    left, width, base_y = 314, 572, 368
    slot = width / len(LINEUP)
    mouse = pygame.mouse.get_pos()
    for i, (role, verb) in enumerate(LINEUP):
        cx = int(left + (i + .5) * slot)
        color = ROLE_COLORS[role]
        hovered = math.hypot(mouse[0] - cx, mouse[1] - (base_y - 34)) < 44
        bob = int(math.sin(t * 2 + i * .9) * 3)
        scale = 1.34 if hovered else 1.0
        sprite = CHARACTER_SPRITES[role]['right'][0]
        size = (int(sprite.get_width() * scale), int(sprite.get_height() * scale))
        shown = pygame.transform.smoothscale(sprite, size) if scale != 1 else sprite
        ring = 46 if hovered else 40
        pygame.draw.ellipse(screen, (16, 30, 36), (cx - ring // 2, base_y - 6, ring, 16))
        pygame.draw.ellipse(screen, color, (cx - ring // 2, base_y - 6, ring, 16), 2)
        screen.blit(shown, shown.get_rect(midbottom=(cx, base_y + 9 + bob)))
        label = fonts[12].render(verb, True, color)
        screen.blit(label, label.get_rect(midtop=(cx, base_y + 14)))


def draw_cta(key, label, bounds, play_icon=False):
    """Primary call-to-action: filled, tallest, with a breathing glow edge."""
    bounds = pygame.Rect(bounds)
    menu_buttons[key] = bounds
    hovered = menu_buttons[key].collidepoint(pygame.mouse.get_pos())
    t = pygame.time.get_ticks() / 1000
    pulse = int((46 if hovered else 22) * (.5 + .5 * math.sin(t * 3)))
    glow = pygame.Surface((bounds.width + 12, bounds.height + 12), pygame.SRCALPHA)
    pygame.draw.rect(glow, (*GREEN, (150 if hovered else 70) + pulse),
                     (0, 0, glow.get_width(), glow.get_height()), width=4, border_radius=14)
    screen.blit(glow, (bounds.x - 6, bounds.y - 6))
    rect((78, 152, 122) if hovered else (55, 130, 102), bounds, 10)
    rect(GREEN, bounds, 10, 2)
    rendered = fonts[18].render(label, True, (238, 250, 244))
    spot = rendered.get_rect(center=menu_buttons[key].center)
    if play_icon:  # a drawn play triangle beats a glyph that may not exist in the font
        pygame.draw.polygon(screen, (238, 250, 244),
                            [(spot.left - 26, spot.centery - 7), (spot.left - 26, spot.centery + 7), (spot.left - 12, spot.centery)])
    screen.blit(rendered, spot)


def draw_ghost(key, label, bounds, size=16):
    """Secondary action: half-width, outline-only, quiet until hovered."""
    menu_buttons[key] = pygame.Rect(bounds)
    hovered = menu_buttons[key].collidepoint(pygame.mouse.get_pos())
    rect((30, 48, 56) if hovered else (22, 36, 42), bounds, 7)
    rect((96, 124, 130) if hovered else (74, 100, 108), bounds, 7, 1)
    rendered = fonts[size].render(label, True, INK if hovered else MUTED)
    screen.blit(rendered, rendered.get_rect(center=menu_buttons[key].center))


def draw_campaign_strip(t):
    """Thin status bar under the menu card: sector progress and rescue record."""
    sector, rescued = campaign['unlocked_sector'], campaign['completed']
    progress = (sector - 1) / 3
    text(f'SECTOR {sector}/3', 250, 734, 12, AMBER)
    bar = pygame.Rect(340, 738, 300, 6)
    rect((30, 46, 52), bar, 3)
    rect(GREEN, (bar.x, bar.y, max(4, int(bar.width * progress)), bar.height), 3)
    pygame.draw.circle(screen, GREEN, (bar.x + int(bar.width * progress), bar.y + 3), 5)
    for mark in range(1, 3):
        rect((57, 83, 89), (bar.x + mark * bar.width // 3, bar.y - 2, 1, 10))
    text(f"RESCUED: {rescued}", 886, 734, 12, MUTED)


def draw_map_labels():
    """Building name tags, drawn above the fog so the campus stays readable."""
    if not REALISTIC_CAMPUS:
        return
    for label, tile, width in (('ADMIN BLOCK',(2,2),116),('LIBRARY',(15,2),92),('PARKING',(22,2),88),
                               ('SECURITY',(24,6),88),('SCIENCE LAB',(2,8),104),('LECTURE HALL',(16,8),112),
                               ('HOSTEL',(2,14),82),('CAFETERIA',(13,14),96),('SPORTS COURT',(22,14),110)):
        x, y = OX+tile[0]*TILE, OY+tile[1]*TILE
        tag = pygame.Surface((width, 24), pygame.SRCALPHA)
        tag.fill((12, 25, 31, 210))
        screen.blit(tag, (x, y))
        text(label, x+8, y+5, 12, (229, 239, 234))


def draw_map():
    if REALISTIC_CAMPUS:
        screen.blit(REALISTIC_CAMPUS, (OX, OY))
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


# One colour per role, used for the ground ring, the name and the team list.
ROLE_COLORS = {'Leader': (76, 162, 221), 'Rescuer': (240, 150, 60), 'Medic': (108, 224, 193),
               'Defender': (178, 132, 255), 'Scout': (246, 222, 90), 'Student': (238, 238, 228),
               'Zombie': (236, 72, 72)}


def actor_label(a):
    """Role name, numbered for the two Defenders ('Defender 1', 'Defender 2')."""
    return a.name.replace('-', ' ') if a.role == 'Defender' else a.role


def spot(a):
    """Screen position of a character: exactly where it is in the simulation."""
    return int(OX + a.x), int(OY + a.y)


def show_all_names():
    return debug or bool(pygame.key.get_mods() & pygame.KMOD_ALT)


def draw_actor(a):
    x, y = spot(a)
    if not a.alive:
        if a.role == 'Zombie':
            # A neutralized zombie sinks away instead of littering the map.
            fade = game.corpse_fade(a)
            if fade > 0:
                body = pygame.transform.smoothscale(ACTOR_IMAGES[a.role], (32, 22))
                body.set_alpha(int(125 * fade))
                screen.blit(body, body.get_rect(center=(x, y+5)))
            return
        body = pygame.transform.smoothscale(ACTOR_IMAGES[a.role], (32, 22))
        body.set_alpha(125)
        screen.blit(body, body.get_rect(center=(x, y+5)))
        pygame.draw.line(screen, (229, 87, 82), (x-16, y-9), (x+16, y+12), 2)
        text('DOWN', x-18, y+12, 12, (233, 134, 131))
        return
    color = ROLE_COLORS[a.role]
    # A coloured ring on the ground tells roles apart at a glance.
    pygame.draw.ellipse(screen, (23, 37, 34), (x-15, y+3, 30, 15))
    pygame.draw.ellipse(screen, color, (x-15, y+3, 30, 15), 3)
    if a is game.controlled_actor():
        pygame.draw.circle(screen, (244, 195, 109), (x, y+5), 24, 2)
        text('YOU', x-12, y-39, 12, (244, 195, 109))
    if a.moving:
        # Small dust puffs communicate movement without changing the stable
        # sprite orientation used by the Scout.
        pygame.draw.circle(screen, (119, 130, 112), (x-10, y+10), 2)
        pygame.draw.circle(screen, (119, 130, 112), (x+9, y+11), 2)
    if a.role == 'Rescuer' and selected and player_role == 'Commander':
        pygame.draw.circle(screen, (245, 201, 120), (x, y), 21, 2)
    # The rendered characters are upright 3D cutouts.  The former Kenney sprites
    # were top-down and needed directional rotation; applying that rule here made
    # people appear to lie down whenever they moved sideways.
    body = character_frame(a)
    if a.flash:
        body = body.copy()
        body.fill((105, 105, 105, 0), special_flags=pygame.BLEND_RGB_ADD)
    # The Scout frequently pauses to scan a sector. Keep that scan pose stable
    # so it never looks like it is vibrating while waiting for new information.
    bob = int(math.sin(game.elapsed * 14) * 2) if a.moving and a.role != 'Scout' else 0
    screen.blit(body, body.get_rect(midbottom=(x, y + 16 + bob)))
    # Health bars appear only once a character has been hurt.
    top = game.max_hp(a)
    if a.hp < top:
        rect((22, 32, 34), (x-17, y-28, 34, 4), 2)
        rect((224, 104, 100) if a.hp < .4 * top else GREEN, (x-17, y-28, int(34*a.hp/top), 4), 2)
    # Names: always yours and anybody in trouble; everybody while Alt is held.
    if game.named_on_map(a) or show_all_names():
        label = actor_label(a)
        text(label, x - fonts[12].size(label)[0]//2, y+21, 12, color)
    if a.role == 'Student' and a.state == 'Waiting':
        radius = 9 + int((math.sin(game.elapsed * 5) + 1) * 2)
        pygame.draw.circle(screen, (241, 99, 95), (x, y-42), radius, 2)
        text('HELP', x-17, y-49, 12, (255, 211, 154))
    if debug:
        text(a.state, x-23, y+36, 12)


buttons = [(pygame.Rect(946, 320, 228, 26), 'Rescue', '[E] RESCUE'),
           (pygame.Rect(946, 352, 111, 26), 'Follow', '[F] FOLLOW'),
           (pygame.Rect(1063, 352, 111, 26), 'Hold', '[H] HOLD')]


CAMPUS_FOG = CloudFog()


def draw_fog():
    """Drifting cloud fog over every part of campus the team has not scouted.

    Real time drives the drift, so the fog keeps moving while the game is
    paused; cleared areas roll back smoothly as the Scout reveals them.
    """
    CAMPUS_FOG.draw(screen, (OX, OY), game.revealed, pygame.time.get_ticks() / 1000)


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
        x, y = spot(target)
        # A compact warning reticle reads as a combat cue without hiding the sprite.
        pygame.draw.circle(screen, (238, 93, 88), (x, y), pulse, 2)
        pygame.draw.line(screen, (238, 93, 88), (x-11, y-30), (x+11, y-30), 2)
        text('ZOMBIE TARGET', x-38, y-47, 12, (250, 148, 136))


def draw_action_effects():
    """Short, role-specific cues that make autonomous actions readable."""
    actors = {actor.name: actor for actor in game.actors}
    pulse = int((math.sin(game.elapsed * 12) + 1) * 2)
    # A short amber tracer makes each Defender's shots visible without clutter.
    for defender in game.defenders:
        target = game.defender_targets.get(defender.name)
        if defender.state == 'Engage' and defender.cooldown > .35 and target and target.alive:
            start = spot(defender); start = (start[0], start[1] - 6)
            end = spot(target)
            pygame.draw.line(screen, (248, 211, 112), start, end, 2)
            pygame.draw.circle(screen, (255, 235, 168), start, 5 + pulse)
    # Healing is visible as a calm medical ring around the current patient.
    if game.medic.task.startswith('Heal '):
        patient = actors.get(game.medic.task.removeprefix('Heal '))
        if patient and patient.alive and math.dist(game.medic.pos, patient.pos) < 45:
            x, y = spot(patient)
            pygame.draw.circle(screen, (103, 235, 194), (x, y), 24 + pulse, 2)
            text('+', x-4, y-44, 18, (151, 248, 214))
    # An escort tether explains who is being extracted without adding a panel.
    if game.escort_student and game.escort_student.alive:
        student, rescuer = game.escort_student, game.rescuer
        start, end = spot(rescuer), spot(student)
        pygame.draw.line(screen, (244, 197, 112), start, end, 1)
        pygame.draw.circle(screen, (244, 197, 112), end, 23 + pulse, 2)
    # Bite arcs show that a zombie is actively dealing damage, not merely close.
    for zombie in game.zombies:
        target = actors.get(zombie.target_name)
        if zombie.alive and zombie.state == 'Attack' and target and target.alive:
            x, y = spot(target)
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
    draw_map_labels()
    for pickup in game.pickups:
        draw_pickup(pickup)
    visible_actors = [a for a in game.actors if a.role not in ('Student', 'Zombie') or game.discovered[a.name]]
    draw_threat_markers()
    draw_action_effects()
    # Back to front, with your own character always drawn last so it is never hidden.
    player = game.controlled_actor()
    for actor in sorted(visible_actors, key=lambda actor: (actor is player, actor.y)):
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
    t = pygame.time.get_ticks() / 1000
    text('CAMPUS / CRISIS', 22, 17, 32)
    text('FIRST RESPONSE     /     PLAYABLE PROTOTYPE 01', 24, 58, 12, MUTED)
    text(f'{game.rescued_count:02}/{len(game.students):02}  STUDENTS EXTRACTED', 555, 29, 16, GREEN)
    text(f'YOU: {player_role.upper()}', 555, 51, 12, (244, 195, 109))
    text(f'{int(game.time)//60:02}:{int(game.time)%60:02}', 811, 22, 32, (243, 190, 119))
    rect((76, 101, 107) if audio_muted else (51, 92, 81), mute_button, 6)
    text('MUTED [M]' if audio_muted else 'SOUND ON [M]', 1061, 53, 12, INK)
    draw_world()
    update_toasts()
    # ---- Mission Control side panel: pinned header + threat, tabbed body ----
    rect(PANEL, (932, 94, 256, 640), 8)
    rect(PANEL_EDGE, (932, 94, 256, 640), 8, 1)
    rect((29, 54, 58), (932, 94, 256, 40), 8)
    pygame.draw.circle(screen, GREEN if not game.result else AMBER, (950, 114), 4)
    text('MISSION CONTROL', 962, 104, 18, (220, 235, 230))
    draw_divider(135)
    # Pinned: mission identity and the fight's core numbers.
    text(f"SECTOR {game.campaign_level} / 3", 946, 144, 12, AMBER)
    clip_text(game.mission['title'].upper(), 946, 160, 14, GREEN, 228)
    draw_icon_person(950, 188)
    text(str(len(game.students)), 960, 182, 12)
    draw_icon_skull(994, 188)
    text(str(len(game.zombies)), 1004, 182, 12)
    draw_icon_clock(1040, 188)
    text(f'{int(game.time)}s', 1050, 182, 12, AMBER)
    intel = 'STUDENT LOCATED' if game.discovered['Student'] else 'SCOUT SEARCHING FOR STUDENT'
    clip_text(intel, 946, 202, 12, GREEN if game.discovered['Student'] else AMBER_TEXT, 228)
    draw_divider(218)
    # Pinned: ongoing pursuit state (toasts announce the event; this is the state).
    active_targets = [f'{z.name} → {z.target_name}' for z in game.zombies if z.target_name]
    if active_targets:
        rect((60, 25, 25), (940, 224, 240, 30), 4)
        draw_warning_icon(954, 239)
        text('THREAT', 968, 228, 12, DANGER_TEXT)
        clip_text(', '.join(active_targets), 946, 242, 12, DANGER_TEXT, 224)
    else:
        draw_warning_icon(954, 239, (120, 140, 142))
        text('THREAT', 968, 228, 12, MUTED)
        text('No active pursuit', 946, 242, 12, MUTED)
    draw_divider(260)
    # Tab strip: STATUS | TACTICS | LOG.
    tab_labels = (('status', 'STATUS'), ('tactics', 'TACTICS'), ('log', 'LOG'))
    for index, (tab_key, tab_label) in enumerate(tab_labels):
        tab_bounds = pygame.Rect(940 + index * 79, 266, 76, 26)
        PANEL_TABS[tab_key] = tab_bounds
        current = active_panel_tab == tab_key
        rect((55, 105, 92) if current else (30, 48, 56), tab_bounds, 5)
        rect(GREEN if current else (52, 75, 80), tab_bounds, 5, 1)
        rendered = fonts[12].render(tab_label, True, INK if current else MUTED)
        screen.blit(rendered, rendered.get_rect(center=tab_bounds.center))
    draw_divider(298)
    if active_panel_tab == 'status':
        text('TEAM STATUS', 946, 308, 12, MUTED)
        for i, a in enumerate((game.leader, game.rescuer, game.medic, *game.defenders, game.scout, game.student)):
            y = 328 + i * 28
            top = game.max_hp(a)
            low = a.hp < .35 * top
            pygame.draw.circle(screen, ROLE_COLORS[a.role], (952, y + 9), 4)
            clip_text(actor_label(a), 962, y + 2, 12, INK, 66)
            rect((46, 60, 63), (1036, y + 4, 120, 10), 5)
            rect(DANGER if low else GREEN, (1036, y + 4, max(6, int(120 * a.hp / top)), 10), 5)
            if low:  # a breathing outline makes critical teammates unmissable
                glow = pygame.Surface((126, 16), pygame.SRCALPHA)
                pygame.draw.rect(glow, (*DANGER, int(70 + 60 * math.sin(t * 6))), (0, 0, 126, 16), width=2, border_radius=8)
                screen.blit(glow, (1033, y + 1))
    elif active_panel_tab == 'tactics':
        text('YOUR CONTROLS: '+player_role.upper() if player_role != 'Commander' else 'COMMAND PANEL', 946, 308, 12, AMBER)
        if player_role == 'Commander':
            for bounds, order, label in buttons:
                active = game.order == order
                rect((54, 100, 90) if active else (31, 46, 55), bounds, 5)
                rect(GREEN if active else (52, 75, 80), bounds, 5, 1)
                text(label, bounds.x + 9, bounds.y + 6, 12, INK if active else MUTED)
        else:
            action_help = {
                'Rescuer': '[E] Start escort / collect nearby item',
                'Medic': '[E] Treat nearby teammate / collect item',
                'Defender': '[E] Engage zombie / collect ammo',
                'Scout': '[E] Scan nearby sector / collect item',
            }[player_role]
            rect((24, 38, 46), (946, 320, 228, 58), 5)
            rect((52, 75, 80), (946, 320, 228, 58), 5, 1)
            text(action_help, 956, 330, 12, INK)
            text('WASD move  |  Shift run', 956, 350, 12, MUTED)
        draw_divider(394)
        text('AI DECISIONS', 946, 404, 12, MUTED)
        for i, a in enumerate((game.scout, game.medic, *game.defenders)):
            y = 424 + i * 18
            task = 'You are in control' if a is game.controlled_actor() else a.task
            controlled = a is game.controlled_actor()
            clip_text(f'{actor_label(a)}: {task}', 946, y, 12, AMBER if controlled else MUTED, 228)
        draw_divider(500)
        text('RESOURCES', 946, 510, 12, MUTED)
        draw_icon_medkit(954, 532)
        text('Medkits', 966, 526, 12)
        text(str(game.medkits), 1174 - fonts[12].size(str(game.medkits))[0], 526, 12)
        draw_icon_ammo(954, 558)
        text('Ammo', 966, 552, 12)
        text(str(game.ammo), 1174 - fonts[12].size(str(game.ammo))[0], 552, 12)
        draw_icon_fuel(954, 584)
        text('Fuel secured', 966, 578, 12)
        fuel_text = f'{game.fuel}/{game.fuel_required}'
        text(fuel_text, 1174 - fonts[12].size(fuel_text)[0], 578, 12, (70, 160, 215))
    else:
        y, first_line = 310, True
        rect((74, 129, 117), (940, 310, 2, min(30, len(wrap_line(game.logs[-1], 34)[:2]) * 15)))
        for message in reversed(game.logs):
            for line in wrap_line(message, 34)[:2]:
                if y > 718:
                    break
                text(('› ' if first_line else '  ')+line, 948, y, 12,
                     MUTED if first_line else (120, 140, 142))
                first_line = False
                y += 15
            y += 8
            if y > 718:
                break
    draw_toasts()
    controls = ('WASD Move  |  Shift Run  |  Space Strike  |  E Rescue/Command  |  Alt Names  |  F4 Full Map  |  F5-F7 Panel  |  F11 Window  |  P Pause  |  R Restart'
                if player_role == 'Commander' else 'WASD Move  |  Shift Run  |  E Context Action  |  Alt Names  |  F4 Full Map  |  F5-F7 Panel  |  F11 Window  |  P Pause  |  R Restart')
    text(controls, 22, 742, 12, MUTED)
    if game.shove_cooldown > .4:
        pygame.draw.circle(screen, (221, 233, 202), (int(OX+game.leader.x), int(OY+game.leader.y)), 38, 2)
    if paused or game.result:
        draw_state_overlay()


def draw_menu():
    """All pre-game screens share the animated backdrop and menu card."""
    menu_buttons.clear()
    t = pygame.time.get_ticks() / 1000
    draw_menu_backdrop(t)
    draw_menu_card()
    if screen_state == 'menu':
        draw_menu_title(314, 128)
        text('MULTI-AGENT ZOMBIE RESCUE', 318, 190, 18, GREEN)
        draw_scan_line(318, 224, 568, t)
        text('A rescue team is waiting for your command.', 318, 244, 14, MUTED)
        draw_lineup(t)
        draw_cta('briefing', 'DEPLOY RESCUE TEAM  [ENTER]', (314, 424, 572, 56), True)
        draw_ghost('howto', 'HOW TO PLAY  [H]', (314, 500, 278, 44))
        draw_ghost('quit', 'QUIT  [ESC]', (608, 500, 278, 44))
        rect(PANEL_EDGE, (314, 596, 572, 1))
        text('FIRST RESPONSE  •  PLAYABLE PROTOTYPE 01', 314, 614, 12, MUTED)
        draw_campaign_strip(t)
    elif screen_state == 'briefing':
        draw_menu_title(314, 116)
        text('MULTI-AGENT ZOMBIE RESCUE', 318, 178, 18, GREEN)
        rect((74, 129, 117), (314, 226, 572, 1))
        # Left column: mission story and difficulty.
        text('MISSION BRIEFING', 314, 250, 18, GREEN)
        text('Your rescue team adapts to', 314, 280, 14, MUTED)
        text('your play style, mission by mission.', 314, 300, 14, MUTED)
        text('CHOOSE DIFFICULTY', 314, 344, 12, MUTED)
        for index, (label, stars) in enumerate((('Easy', 1), ('Normal', 2), ('Hard', 3))):
            bounds = pygame.Rect(314 + index * 96, 364, 88, 46)
            menu_buttons['difficulty_' + label] = bounds
            active = difficulty == label
            hovered = bounds.collidepoint(pygame.mouse.get_pos())
            rect((55, 105, 92) if active else (44, 66, 74) if hovered else (30, 48, 56), bounds, 7)
            rect(GREEN if active else (91, 117, 125), bounds, 7, 1)
            rendered = fonts[13].render(label, True, INK if active else MUTED)
            screen.blit(rendered, rendered.get_rect(midtop=(bounds.centerx, bounds.y + 7)))
            for star in range(3):
                if star < stars:
                    draw_star(bounds.x + 26 + star * 18, bounds.y + 33, 6, AMBER if active else (120, 140, 142))
                else:
                    draw_star(bounds.x + 26 + star * 18, bounds.y + 33, 6, (48, 66, 70))
        text('Every incident varies students, zombies,', 314, 434, 12, MUTED)
        text('resources and the time you have left.', 314, 450, 12, MUTED)
        draw_ghost('reset_campaign', 'RESET CAMPAIGN  [X]', (314, 496, 220, 42), 14)
        # Right column: campaign progress and AI readiness, minus the jargon.
        text(f"SECTOR {campaign['unlocked_sector']} / 3", 624, 250, 24, INK)
        bar = pygame.Rect(624, 286, 292, 10)
        progress = (campaign['unlocked_sector'] - 1) / 3
        rect((30, 46, 52), bar, 5)
        rect(GREEN, (bar.x, bar.y, max(4, int(bar.width * progress)), bar.height), 5)
        for mark in range(1, 3):
            rect((57, 83, 89), (bar.x + mark * bar.width // 3, bar.y - 2, 1, 14))
        text(f"Successful rescues: {campaign['completed']}", 624, 306, 12, MUTED)
        text('AI READINESS', 624, 346, 12, MUTED)
        if adaptive_data['trained']:
            readiness, ready_label = adaptive_data['accuracy'], 'HIGH' if adaptive_data['accuracy'] > .8 else 'STABLE'
        else:
            readiness, ready_label = adaptive_data['missions'] / 15, f"LEARNING {adaptive_data['missions']}/15"
        text(ready_label, 916 - fonts[12].size(ready_label)[0], 346, 12, GREEN)
        ready_bar = pygame.Rect(624, 366, 292, 10)
        rect((30, 46, 52), ready_bar, 5)
        rect(GREEN, (ready_bar.x, ready_bar.y, max(3, int(ready_bar.width * readiness)), ready_bar.height), 5)
        friendly = (adaptive_plan['reason'].replace('ML predicts', 'The team predicts')
                    .replace('chance of success from recent play', 'success from your recent play'))
        for row, line in enumerate(wrap_line(friendly, 34)[:2]):
            text(line, 624, 396 + row * 16, 12, MUTED)
        text('TEAM MODE: '+adaptive_plan['label'].replace('ML ', ''), 624, 442, 12, AMBER)
        text(f"PLAYER SETTING: {difficulty}", 624, 460, 12, INK)
        draw_cta('deploy', 'CHOOSE PLAYABLE ROLE  [ENTER]', (314, 596, 380, 52))
        draw_ghost('back', 'BACK  [ESC]', (724, 600, 192, 44))
    elif screen_state == 'role_select':
        draw_menu_title(314, 116)
        text('MULTI-AGENT ZOMBIE RESCUE', 318, 178, 18, GREEN)
        text('CHOOSE YOUR ROLE', 314, 236, 24, GREEN)
        text('You control this role. The rest of the rescue team uses AI decisions.', 318, 270, 14, MUTED)
        roles = (
            ('Commander', 'Coordinate the team and issue rescue orders.'),
            ('Rescuer', 'Reach located students and escort them to safety.'),
            ('Medic', 'Move to injured teammates and use medkits.'),
            ('Defender', 'Engage zombies alongside an AI Defender partner.'),
            ('Scout', 'Explore fog and scan nearby campus sectors.'),
        )
        for index, (role, description) in enumerate(roles):
            y = 306 + index * 48
            active = player_role == role
            menu_button('role_'+role, f'[{index+1}]  {role.upper()}  —  {description}', (314, y, 572, 40), active)
            sprite = pygame.transform.smoothscale(CHARACTER_SPRITES['Leader' if role == 'Commander' else role]['right'][0], (14, 34))
            screen.blit(sprite, (328, y + 4))
        draw_cta('launch_role', f'DEPLOY AS {player_role.upper()}  [ENTER]', (314, 560, 380, 52))
        draw_ghost('back', 'BACK', (724, 564, 192, 44))
    else:
        draw_menu_title(314, 116)
        text('MULTI-AGENT ZOMBIE RESCUE', 318, 178, 18, GREEN)
        text('HOW TO PLAY', 314, 236, 24, GREEN)
        for i, line in enumerate((
                'Choose Commander or a field role before each mission.',
                'WASD moves your role. E performs its context action.',
                'Resources help the team, but every Safe Zone tile releases an escort.',
                'F11 switches between fullscreen and a window.',
                'Hold Alt to show every name. Ring colours mark each role; zombies are red.')):
            text(line, 318, 280 + i * 34, 14, MUTED)
        draw_cta('back', 'BACK TO MENU  [ESC]', (314, 560, 380, 52))


running, frames = True, 0
while running:
    dt = 1/60 if args.smoke_test or args.screenshot else clock.tick(60)/1000
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                if not HEADLESS:
                    pygame.display.toggle_fullscreen()
            elif event.key == pygame.K_ESCAPE:
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
            elif event.key == pygame.K_F5:
                active_panel_tab = 'status'
            elif event.key == pygame.K_F6:
                active_panel_tab = 'tactics'
            elif event.key == pygame.K_F7:
                active_panel_tab = 'log'
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
                for tab_key, tab_bounds in PANEL_TABS.items():
                    if tab_bounds.collidepoint(event.pos):
                        active_panel_tab = tab_key
                        break
                if math.dist((mx-OX, my-OY), game.rescuer.pos) < 28:
                    selected = True
                for bounds, order, _ in buttons:
                    if player_role == 'Commander' and selected and active_panel_tab == 'tactics' and bounds.collidepoint(event.pos):
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
