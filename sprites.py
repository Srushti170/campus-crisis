"""Painted semi-realistic character sprites, drawn in code.

Every character is built from simple shapes at a high drawing resolution and
then scaled down to game size. The look sits between realistic and cartoon:
adult proportions (about 6.5 heads tall), muted clothes, soft shading, and the
role colour used as an accent (the Rescuer's hi-vis vest, the Defenders' violet
shoulder pads, the Scout's yellow cap) so roles stay readable at a glance.

Each role has three frames: standing, then two walking steps. Frames are also
mirrored so a character can face the way it walks.
"""
import pygame

UNIT = 4                      # drawing pixels per design unit
CANVAS_UNITS = (48, 86)       # the design canvas a figure is drawn on
ROLES = ('Leader', 'Rescuer', 'Medic', 'Defender', 'Scout', 'Student', 'Zombie')
GAME_HEIGHT = {'Student': 54, 'Zombie': 58}   # everybody else is 56 px tall
DEFAULT_HEIGHT = 56
STEP_LIFT = 2.6               # how far a foot rises during a walking step (units)

PALETTE = {
    #            skin             top / jacket      trousers          footwear          hair
    'Leader':   ((214, 166, 130), (46, 60, 94),     (40, 44, 58),     (36, 32, 30),     (40, 32, 28)),
    'Rescuer':  ((214, 166, 130), (72, 76, 86),     (48, 54, 66),     (36, 32, 30),     (60, 44, 32)),
    'Medic':    ((176, 124, 92),  (78, 168, 146),   (60, 132, 116),   (40, 40, 44),     (24, 22, 22)),
    'Defender': ((214, 166, 130), (58, 60, 72),     (50, 52, 62),     (36, 32, 30),     (30, 28, 26)),
    'Scout':    ((198, 150, 116), (102, 114, 74),   (122, 114, 88),   (36, 32, 30),     (70, 50, 34)),
    'Student':  ((226, 180, 146), (204, 204, 200),  (66, 96, 150),    (226, 226, 222),  (98, 64, 40)),
    'Zombie':   ((150, 166, 128), (96, 74, 82),     (60, 58, 68),     (36, 32, 30),     (58, 60, 52)),
}
ROLE_ACCENT = {'Leader': (76, 162, 221), 'Rescuer': (236, 132, 46), 'Defender': (150, 110, 225), 'Scout': (232, 204, 72)}


def darker(color, factor=.7):
    return tuple(int(v * factor) for v in color)


def lighter(color, amount=.3):
    return tuple(int(v + (255 - v) * amount) for v in color)


def mirror(points):
    """Mirror design-unit points across the figure's vertical centre line."""
    return [(CANVAS_UNITS[0] - x, y) for x, y in points]


class Painter:
    """Draws shapes in design units, with soft painted shading (light from the left)."""

    def __init__(self):
        self.surface = pygame.Surface((CANVAS_UNITS[0] * UNIT, CANVAS_UNITS[1] * UNIT), pygame.SRCALPHA)

    def _shade(self, draw, box, color):
        draw(color)
        x0, y0, x1, y1 = (v * UNIT for v in box)
        for start, factor in ((.46, .88), (.68, .74)):           # mid-tone, then shadow side
            cut = x0 + (x1 - x0) * start
            self.surface.set_clip(pygame.Rect(int(cut), int(y0), int(x1 - cut) + 2, int(y1 - y0) + 2))
            draw(darker(color, factor))
        self.surface.set_clip(pygame.Rect(int(x0), int(y0), int((x1 - x0) * .2) + 1, int(y1 - y0) + 2))
        draw(lighter(color, .16))                                 # lit edge
        self.surface.set_clip(None)

    def poly(self, points, color, shade=True):
        scaled = [(x * UNIT, y * UNIT) for x, y in points]
        draw = lambda c: pygame.draw.polygon(self.surface, c, scaled)
        if shade:
            xs, ys = [x for x, _ in points], [y for _, y in points]
            self._shade(draw, (min(xs), min(ys), max(xs), max(ys)), color)
        else:
            draw(color)

    def ellipse(self, x, y, w, h, color, shade=True):
        draw = lambda c: pygame.draw.ellipse(self.surface, c, (x * UNIT, y * UNIT, w * UNIT, h * UNIT))
        if shade:
            self._shade(draw, (x, y, x + w, y + h), color)
        else:
            draw(color)

    def rect(self, x, y, w, h, color, radius=0):
        pygame.draw.rect(self.surface, color, (x * UNIT, y * UNIT, w * UNIT, h * UNIT), border_radius=int(radius * UNIT))

    def line(self, start, end, color):
        pygame.draw.line(self.surface, color, (start[0] * UNIT, start[1] * UNIT), (end[0] * UNIT, end[1] * UNIT), max(1, UNIT // 2))

    def circle(self, x, y, r, color):
        pygame.draw.circle(self.surface, color, (x * UNIT, y * UNIT), r * UNIT)

    def cross(self, x, y, size, color):
        """A small red-cross mark centred on (x, y)."""
        bar = size * .23
        self.rect(x - bar / 2, y - size / 2, bar, size, color)
        self.rect(x - size / 2, y - bar / 2, size, bar, color)


def draw_figure(role, step=0):
    """Draw one frame. step 0 stands; +1 lifts the left foot, -1 the right."""
    paint = Painter()
    skin, top, trousers, footwear, hair = PALETTE[role]
    zombie = role == 'Zombie'
    left_lift = STEP_LIFT if step > 0 else 0
    right_lift = STEP_LIFT if step < 0 else 0

    # Legs and footwear (a lifted foot is drawn higher, which reads as a step).
    leg = [(14.5, 51), (23.5, 51), (22, 77), (14.8, 77)]
    boot = [(14.4, 76), (22.4, 76), (23.4, 83), (12.6, 83)]
    for points, lift in ((leg, left_lift), (mirror(leg), right_lift)):
        paint.poly([(x, y - lift if y > 60 else y) for x, y in points], trousers)
    for points, lift in ((boot, left_lift), (mirror(boot), right_lift)):
        paint.poly([(x, y - lift) for x, y in points], footwear)
    if zombie:
        paint.poly([(16, 58), (19, 61), (22, 57), (22, 64), (16, 64)], darker(trousers, .6), shade=False)  # torn knee
    paint.poly([(15, 45), (33, 45), (33.5, 52), (14.5, 52)], darker(trousers, .9))

    # Backpacks sit behind the body.
    if role in ('Student', 'Scout'):
        paint.poly([(13, 22), (35, 22), (34, 44), (14, 44)], (120, 82, 54) if role == 'Student' else (78, 88, 60))

    # Torso, with an open coat for the Commander.
    if role == 'Leader':
        flap = [(15, 44), (23.6, 44), (22.5, 60), (13, 60)]
        paint.poly(flap, top)
        paint.poly(mirror(flap), top)
    paint.poly([(13.5, 19.5), (34.5, 19.5), (33, 46), (15, 46)], top)
    if role == 'Rescuer':
        paint.poly([(14.5, 20), (33.5, 20), (32.5, 46), (15.5, 46)], ROLE_ACCENT['Rescuer'])   # hi-vis vest
        for y in (32, 39):
            paint.poly([(15, y), (33, y), (33, y + 2.4), (15, y + 2.4)], (226, 228, 214), shade=False)
    elif role == 'Defender':
        paint.poly([(15, 22), (33, 22), (32, 42), (16, 42)], (72, 74, 88))                      # body armour
        paint.poly([(16, 30), (32, 30), (32, 33), (16, 33)], ROLE_ACCENT['Defender'], shade=False)
    elif role == 'Medic':
        paint.rect(17.5, 24, 6, 6, (250, 250, 250))
        paint.cross(20.5, 27, 4, (220, 60, 60))
    elif role == 'Student':
        for x in (17, 30):
            paint.poly([(x, 20), (x + 2, 20), (x + 2, 38), (x, 38)], (120, 82, 54), shade=False)  # backpack straps
        paint.poly([(19, 18), (29, 18), (30, 22), (18, 22)], darker(top, .85), shade=False)      # hood
    elif role == 'Scout':
        paint.poly([(19, 18.5), (29, 18.5), (27, 24), (21, 24)], ROLE_ACCENT['Scout'])            # scarf
        paint.rect(20, 28, 8, 3.4, (34, 34, 36), radius=1)                                         # binoculars
    if zombie:
        for x, y, r in ((20, 30, 2.6), (28, 38, 2), (25, 24, 1.6)):
            paint.circle(x, y, r, (104, 30, 34))
        paint.poly([(15, 46), (18, 42), (21, 47), (25, 42), (29, 47), (33, 43), (33, 46)], (0, 0, 0, 0), shade=False)  # ragged hem

    # Arms; the zombie reaches forward with one.
    upper = [(10.5, 20), (15, 19.5), (14.5, 34), (10, 34)]
    fore = [(10, 33.5), (14.5, 33.5), (14, 46), (10.5, 46)]
    paint.ellipse(10, 18.6, 7, 6.5, top)
    paint.poly(upper, top)
    paint.poly(fore, top)
    paint.ellipse(10, 45, 4.6, 5, skin)
    if zombie:
        paint.poly([(33, 20), (37.5, 20), (45, 27), (42, 30)], top)
        paint.poly([(42, 28.5), (45.5, 26), (47.5, 30.5), (44, 32)], skin)
    else:
        paint.ellipse(31, 18.6, 7, 6.5, top)
        paint.poly(mirror(upper), top)
        paint.poly(mirror(fore), top)
        paint.ellipse(CANVAS_UNITS[0] - 14.6, 45, 4.6, 5, skin)

    # Role gear held or worn on the arms.
    if role == 'Leader':
        for x in (13, 31):
            paint.rect(x, 18.6, 4, 2, lighter(ROLE_ACCENT['Leader'], .1))                       # epaulettes
        paint.poly([(10.3, 25), (14.8, 25), (14.7, 28), (10.2, 28)], ROLE_ACCENT['Leader'], shade=False)  # armband
        paint.rect(33.5, 41, 4, 6, (30, 30, 34), radius=1)                                          # radio
    elif role == 'Defender':
        pad = [(10, 18.5), (16, 18.5), (15.5, 24), (10, 24)]
        paint.poly(pad, ROLE_ACCENT['Defender'])
        paint.poly(mirror(pad), ROLE_ACCENT['Defender'])
        paint.poly([(30, 46), (33.5, 43.5), (15, 25), (12.5, 27.5)], (34, 34, 38))                 # rifle
        paint.poly([(12, 26), (14, 24), (11.5, 21.5), (9.8, 23.5)], (54, 54, 60))
        for x in (16, 26):
            paint.poly([(x, 62), (x + 6, 62), (x + 6, 66), (x, 66)], (44, 46, 54), shade=False)   # knee pads
    elif role == 'Medic':
        paint.poly([(32, 44), (39, 44), (39, 51), (32, 51)], (236, 236, 232))                      # medical bag
        paint.cross(35.5, 47.5, 4, (220, 60, 60))

    # Neck and head.
    paint.poly([(21.8, 14), (26.2, 14), (26.6, 20), (21.4, 20)], darker(skin, .9))
    hx = 1.8 if zombie else 0                                                                      # zombie head lolls
    if role == 'Student':
        paint.ellipse(27.5, 5, 5, 9, hair)                                                         # ponytail
    paint.ellipse(17.6 + hx, 1.4, 12.8, 14.6, skin)
    paint.ellipse(17 + hx, 7, 2.2, 3.6, darker(skin, .92), shade=False)                            # ears
    paint.ellipse(28.8 + hx, 7, 2.2, 3.6, darker(skin, .8), shade=False)
    eye = (238, 210, 120) if zombie else (40, 32, 30)
    paint.ellipse(20.6 + hx, 8.4, 2.2, 1.3, eye, shade=False)
    paint.ellipse(25.4 + hx, 8.4, 2.2, 1.3, eye, shade=False)
    paint.line((20.4 + hx, 7.2), (22.8 + hx, 7.0), darker(skin, .62))                              # brows
    paint.line((25.2 + hx, 7.0), (27.6 + hx, 7.2), darker(skin, .62))
    paint.line((23.9 + hx, 9.6), (23.4 + hx, 11.4), darker(skin, .72))                             # nose
    paint.line((22.4 + hx, 12.9), (25.6 + hx, 12.9), darker(skin, .66))                            # mouth

    # Headwear and hair.
    if role == 'Leader':
        paint.ellipse(16.8, -0.6, 14.4, 7, (40, 54, 86))
        paint.rect(16.2, 4.8, 15.6, 2.2, (26, 34, 56), radius=1)
        paint.circle(24, 3, 1.1, (232, 196, 90))
    elif role == 'Rescuer':
        paint.ellipse(16.6, -0.8, 14.8, 9, ROLE_ACCENT['Rescuer'])
        paint.rect(23.3, -0.3, 1.4, 8, (240, 240, 232))
        paint.rect(16.5, 6, 15, 1.6, (200, 108, 36), radius=1)
    elif role == 'Defender':
        paint.ellipse(16.4, -1, 15.2, 10.6, (52, 54, 64))
        paint.rect(18.4, 6.6, 11.2, 3.6, (20, 22, 28), radius=1)                                   # visor
    elif role == 'Scout':
        paint.ellipse(17.4, -0.2, 13.2, 6.6, ROLE_ACCENT['Scout'])
        paint.rect(24, 4.6, 9, 1.8, (206, 178, 56), radius=1)
    elif zombie:
        paint.ellipse(19 + hx, 1.2, 6, 4, hair, shade=False)
        paint.ellipse(24.5 + hx, 1.8, 4.5, 3, hair, shade=False)
    else:
        paint.ellipse(17.4, 0.6, 13.2, 6.4, hair)
        paint.poly([(17.6, 4), (19.6, 4), (19, 10.5), (17.7, 10)], hair, shade=False)
        paint.poly([(28.4, 4), (30.4, 4), (30.3, 9.5), (29, 10)], hair, shade=False)

    # Soften the edges a touch, like a painted sprite.
    canvas = paint.surface
    half = pygame.transform.smoothscale(canvas, (canvas.get_width() // 2, canvas.get_height() // 2))
    frame = pygame.transform.smoothscale(half, canvas.get_size())
    return frame


def character_frames(role, height=None):
    """[standing, left step, right step] for a role, scaled to game height.

    All frames share one crop so the feet stay planted at the bottom edge.
    """
    height = height or GAME_HEIGHT.get(role, DEFAULT_HEIGHT)
    frames = [draw_figure(role, step) for step in (0, 1, -1)]
    bounds = frames[0].get_bounding_rect(min_alpha=24)
    for frame in frames[1:]:
        bounds.union_ip(frame.get_bounding_rect(min_alpha=24))
    width = max(1, round(bounds.width * height / bounds.height))
    return [pygame.transform.smoothscale(frame.subsurface(bounds), (width, height)) for frame in frames]


def build_character_sprites():
    """Every role's frames, facing right and mirrored to face left."""
    sprites = {}
    for role in ROLES:
        right = character_frames(role)
        sprites[role] = {'right': right, 'left': [pygame.transform.flip(frame, True, False) for frame in right]}
    return sprites
