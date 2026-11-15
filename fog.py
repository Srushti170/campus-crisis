"""Animated, cloud-like fog of war for Campus Crisis.

The simulation (``world.py``) only tracks which grid cells the team has
revealed. This module turns that set into drifting volumetric fog:

* ``visual_clear_cells`` decides which cells should look clear, including
  building roofs and the fence line that the Scout never walks on.
* ``FogField`` eases every cell's fog density toward that target, so fog rolls
  back over about a second instead of popping off tile by tile.
* ``CloudFog`` renders the result: two layers of seamless fractal cloud noise
  drift past each other, and the fog's edge is built from soft, wobbling puffs
  so it billows like real cloud instead of following the grid.

Everything is built with pygame-ce alone (no numpy) and rendered at half
resolution, which is invisible for soft fog and keeps a frame cheap.
"""
import math
import random

import pygame

from world import BUILDINGS, COLS, ROWS, TILE, walkable

FOG_RES = 2                      # render scale divisor (2 = half resolution)
CELL = TILE // FOG_RES           # one grid cell in fog-canvas pixels
ALL_CELLS = tuple((x, y) for y in range(ROWS) for x in range(COLS))
# Once the team has seen this share of a building, its whole roof clears.
BUILDING_CLEAR_FRACTION = 0.55
# Fog dark/light tones: moonlit blue-grey that reads over the night campus.
FOG_SHADOW = (112, 122, 138)
FOG_LIGHT = (222, 229, 238)


def _smoothstep(edge0, edge1, value):
    if edge0 == edge1:
        return 0.0 if value < edge0 else 1.0
    t = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def _building_footprints():
    """Each building's cells and the walkable cells directly around it."""
    footprints = []
    for bx, by, width, height, _ in BUILDINGS:
        cells = {(x, y) for x in range(bx, bx + width) for y in range(by, by + height)}
        around = {(x + dx, y + dy) for x, y in cells for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))}
        footprints.append((cells, {c for c in around - cells if walkable(c)}))
    return footprints


BUILDING_FOOTPRINTS = _building_footprints()


def visual_clear_cells(revealed):
    """Return the cells that should be drawn without fog.

    Revealed cells are clear. A building has no walkable interior for the
    Scout to stand in, so its roof clears as a whole once most of it has been
    seen or the Scout has searched every route around it. Fence-line cells on
    the map edge follow the cell just inside them.
    """
    clear = set(revealed)
    for cells, around in BUILDING_FOOTPRINTS:
        seen = sum(c in revealed for c in cells)
        if seen >= len(cells) * BUILDING_CLEAR_FRACTION or around <= revealed:
            clear.update(cells)
    for x, y in ALL_CELLS:
        on_edge = x in (0, COLS - 1) or y in (0, ROWS - 1)
        if on_edge and not walkable((x, y)):
            inner = (min(max(x, 1), COLS - 2), min(max(y, 1), ROWS - 2))
            if inner in clear:
                clear.add((x, y))
    return clear


class FogField:
    """Per-cell fog density in [0, 1] that eases toward the revealed map."""

    CLEAR_RATE = 2.6      # exponential thinning per second
    CLEAR_FLOOR = 0.25    # plus a small linear term so fading always finishes

    def __init__(self):
        self.density = {cell: 1.0 for cell in ALL_CELLS}
        self._revealed_ref = None
        self._revealed_count = -1
        self._fading = set()

    def reset(self, revealed):
        """Snap to a new mission's revealed set without a fade."""
        clear = visual_clear_cells(revealed)
        self.density = {cell: 0.0 if cell in clear else 1.0 for cell in ALL_CELLS}
        self._revealed_ref, self._revealed_count = revealed, len(revealed)
        self._fading = set()

    def update(self, revealed, dt):
        if revealed is not self._revealed_ref:
            self.reset(revealed)
            return
        if len(revealed) != self._revealed_count:
            # The revealed set only ever grows, so new clear cells start fading.
            self._revealed_count = len(revealed)
            self._fading.update(c for c in visual_clear_cells(revealed) if self.density[c] > 0)
        if not self._fading or dt <= 0:
            return
        keep = 1 - math.exp(-self.CLEAR_RATE * dt)
        finished = []
        for cell in self._fading:
            value = self.density[cell]
            value -= value * keep + self.CLEAR_FLOOR * dt
            if value <= 0.0:
                value = 0.0
                finished.append(cell)
            self.density[cell] = value
        self._fading.difference_update(finished)


def _noise_octave(size, cells, rng):
    """One perfectly seamless octave of smooth value noise (greyscale surface).

    Random values are enlarged by an exact integer factor and then box-blurred
    twice. The blur runs on a copy padded with wrapped-around edges, so the
    texture tiles with no seam when it drifts across the screen.
    """
    width, height = size
    cols, rows = cells
    scale = width // cols
    if scale * cols != width or scale * rows != height:
        raise ValueError(f'{cells} cells must divide the {size} fog canvas exactly')
    values = bytes(v for _ in range(cols * rows) for v in (rng.randrange(256),) * 3)
    blocks = pygame.transform.scale(pygame.image.frombytes(values, (cols, rows), 'RGB'), size)
    radius = max(1, scale // 2)
    margin = radius * 2 + 2
    padded = pygame.Surface((width + margin * 2, height + margin * 2))
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            padded.blit(blocks, (margin + i * width, margin + j * height))
    smooth = pygame.transform.box_blur(pygame.transform.box_blur(padded, radius), radius)
    return smooth.subsurface((margin, margin, width, height)).copy()


def _fractal_noise(size, octaves, rng):
    """Blend several octaves (cells, weight) into one fractal greyscale surface."""
    combined, total = None, 0.0
    for cells, weight in octaves:
        layer = _noise_octave(size, cells, rng)
        total += weight
        if combined is None:
            combined = layer
        else:
            layer.set_alpha(round(255 * weight / total))
            combined.blit(layer, (0, 0))
    return combined


def _stretched(noise):
    """Return contrast-stretched greyscale bytes (3rd-97th percentile -> 0-255)."""
    grey = pygame.image.tobytes(noise, 'RGB')[0::3]
    ordered = sorted(grey)
    lo, hi = ordered[len(ordered) * 3 // 100], ordered[len(ordered) * 97 // 100]
    return grey.translate(bytes(round(255 * _smoothstep(lo, max(hi, lo + 1), v)) for v in range(256)))


def _embossed(noise, depth=3, gain=3):
    """Light the noise from the top-left so each billow gets a bright crown
    and a shaded underside, which is what makes flat noise read as cloud."""
    width, height = noise.get_size()
    wrapped = pygame.Surface((width * 2, height * 2))
    for i in range(2):
        for j in range(2):
            wrapped.blit(noise, (i * width, j * height))
    behind = (width - depth, height - depth, width, height)   # noise shifted down-right
    highlight, shadow = noise.copy(), wrapped.subsurface(behind).copy()
    highlight.blit(wrapped, (0, 0), behind, special_flags=pygame.BLEND_RGB_SUB)
    shadow.blit(noise, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
    lit = noise.copy()
    for _ in range(gain):
        lit.blit(highlight, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        lit.blit(shadow, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
    return lit


def _cloud_texture(size, colour_grey, alpha_grey, colour_fn, alpha_fn):
    """Map greyscale bytes through colour/alpha curves into a 2x2-tiled RGBA surface."""
    curve = [v / 255 for v in range(256)]
    channels = [bytes(max(0, min(255, round(colour_fn(t)[i]))) for t in curve) for i in range(3)]
    alpha = bytes(max(0, min(255, round(alpha_fn(t)))) for t in curve)
    rgba = bytearray(len(colour_grey) * 4)
    for index, table in enumerate(channels):
        rgba[index::4] = colour_grey.translate(table)
    rgba[3::4] = alpha_grey.translate(alpha)
    tile = pygame.image.frombytes(bytes(rgba), size, 'RGBA')
    width, height = size
    doubled = pygame.Surface((width * 2, height * 2), pygame.SRCALPHA)
    for i in range(2):
        for j in range(2):
            doubled.blit(tile, (i * width, j * height), special_flags=pygame.BLEND_RGBA_MAX)
    return doubled


def _lerp_colour(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


class CloudFog:
    """Renders the fog field as drifting, billowing cloud over the campus."""

    def __init__(self, seed=20231):
        rng = random.Random(seed)
        self.size = (COLS * CELL, ROWS * CELL)
        self.full_size = (COLS * TILE, ROWS * TILE)
        self.field = FogField()
        # Broad billows: the dense body of the fog, lit so each lump has volume.
        broad = _fractal_noise(self.size, (((7, 5), 1.0), ((14, 10), .5), ((28, 20), .22), ((56, 40), .07)), rng)
        thickness = _stretched(broad)
        self.body = _cloud_texture(
            self.size, _stretched(_embossed(broad, depth=4, gain=2)), thickness,
            lambda t: _lerp_colour(FOG_SHADOW, FOG_LIGHT, t),
            lambda t: 228 + 27 * t)
        # Finer, brighter vapour that drifts the other way for a churning look.
        fine = _stretched(_fractal_noise(self.size, (((14, 10), 1.0), ((28, 20), .5), ((56, 40), .2)), rng))
        self.wisps = _cloud_texture(
            self.size, fine, fine,
            lambda t: _lerp_colour((150, 162, 176), (236, 241, 246), t),
            lambda t: 175 * _smoothstep(.42, .9, t))
        # Drifting noise that eats into the fog's edge so it frays into wisps.
        ragged = _stretched(_fractal_noise(self.size, (((14, 10), 1.0), ((28, 20), .6), ((56, 40), .3)), rng))
        self.erosion = _cloud_texture(self.size, ragged, ragged, lambda t: (0, 0, 0), lambda t: 120 * t)
        self.canvas = pygame.Surface(self.size, pygame.SRCALPHA)
        self.mask = pygame.Surface(self.size, pygame.SRCALPHA)
        self._scratch = pygame.Surface(self.size, pygame.SRCALPHA)
        # Fixed per-cell jitter and wobble phase keep the edge organic, not gridded.
        self._jitter = {cell: (rng.uniform(-5, 5), rng.uniform(-5, 5),
                               rng.uniform(0, math.tau), rng.uniform(0, math.tau)) for cell in ALL_CELLS}
        self._blobs = {}
        # Pre-build every puff size/strength so the first fade never stutters.
        for radius in range(4, int(CELL * 1.45) + 4):
            for level in range(1, 17):
                self._blob(radius, level)
        self._last_time = None

    def _blob(self, radius, level):
        """Soft white puff: solid core, smooth falloff; cached by size and strength."""
        key = (radius, level)
        blob = self._blobs.get(key)
        if blob is None:
            peak = 255 * level / 16
            blob = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            middle = radius + 1
            for ring in range(radius, 0, -1):
                strength = _smoothstep(1.0, .28, ring / radius)
                pygame.draw.circle(blob, (255, 255, 255, round(peak * strength)), (middle, middle), ring)
            self._blobs[key] = blob
        return blob

    def _build_mask(self, now):
        mask = self.mask
        mask.fill((255, 255, 255, 0))
        blit = mask.blit
        add = pygame.BLEND_RGBA_ADD
        for (x, y), density in self.field.density.items():
            if density <= .015:
                continue
            jx, jy, phase_a, phase_b = self._jitter[(x, y)]
            # Thinning puffs also shrink, so cleared fog visibly rolls back.
            radius = int(CELL * (.7 + .75 * density) + 1.8 * math.sin(now * .85 + phase_a))
            radius = max(4, radius)
            blob = self._blob(radius, max(1, round(density * 16)))
            cx = (x + .5) * CELL + jx + 2.2 * math.sin(now * .55 + phase_b)
            cy = (y + .5) * CELL + jy + 1.8 * math.cos(now * .47 + phase_a)
            blit(blob, (round(cx) - radius - 1, round(cy) - radius - 1), special_flags=add)
        # Erode with drifting noise, then double the alpha: the solid interior
        # saturates back to full while the soft edge turns ragged and wispy.
        width, height = self.size
        ex, ey = self._drift_offset(now, (4.0, -3.0), 6, 4.2)
        mask.blit(self.erosion, (0, 0), (ex, ey, width, height), special_flags=pygame.BLEND_RGBA_SUB)
        scratch = self._scratch
        scratch.fill((0, 0, 0, 0))
        scratch.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
        mask.blit(scratch, (0, 0), special_flags=add)

    def _drift_offset(self, now, speed, sway, phase):
        width, height = self.size
        x = (now * speed[0] + sway * math.sin(now * .19 + phase)) % width
        y = (now * speed[1] + sway * .45 * math.cos(now * .13 + phase)) % height
        return int(x), int(y)

    def draw(self, surface, origin, revealed, now):
        """Advance the fade and draw the fog onto ``surface`` at ``origin``."""
        dt = 0.0 if self._last_time is None else max(0.0, min(.1, now - self._last_time))
        self._last_time = now
        self.field.update(revealed, dt)
        if not any(value > .015 for value in self.field.density.values()):
            return
        self._build_mask(now)
        canvas = self.canvas
        canvas.fill((0, 0, 0, 0))
        width, height = self.size
        bx, by = self._drift_offset(now, (7.0, 2.2), 9, 0.0)
        canvas.blit(self.body, (0, 0), (bx, by, width, height), special_flags=pygame.BLEND_RGBA_MAX)
        wx, wy = self._drift_offset(now, (-11.0, 3.4), 14, 2.1)
        canvas.blit(self.wisps, (0, 0), (wx, wy, width, height))
        canvas.blit(self.mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(pygame.transform.smoothscale(canvas, self.full_size), origin)
