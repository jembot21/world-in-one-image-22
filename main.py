#!/usr/bin/env python3
"""Render a deterministic, illustrated front page from the adjacent stories.json.

Only Pillow is needed beyond the standard library. If Pillow is not installed,
the matching bundled wheel supplies it; native extensions are unpacked into a
fresh system temporary directory, leaving the output directory image-only.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
SIZE = 1024
SCALE = 3
PAPER = "#f7f3ea"
INK = "#14202e"
NAVY = "#0d2137"
GOLD = "#c9a227"
RED = "#b3392e"
MUTED = "#657785"
RULE = "#c9cbc4"
PALE = "#edece4"


def pillow():
    """Try the installed package, then the ABI-matched vendor wheel."""
    try:
        import PIL
    except ImportError:
        # CPython's cache tag is 'cpython-313', while wheels use 'cp313'.
        tag = sys.implementation.cache_tag.replace("cpython-", "cp")
        wheels = sorted((ROOT / "vendor").glob(f"*-{tag}-{tag}-*.whl"))
        if not wheels:
            raise RuntimeError(f"No bundled Pillow wheel for {tag}") from None
        wheel = wheels[0]
        sys.path.insert(0, str(wheel))
        import PIL

        # zipimport handles Python modules, but cannot load a wheel's .so files.
        unpacked = Path(tempfile.mkdtemp(prefix=f"news22-pillow-{tag}-"))
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(unpacked)
        for name in sorted(sys.modules):
            if name == "PIL" or name.startswith("PIL."):
                del sys.modules[name]
        sys.path.remove(str(wheel))
        sys.path.insert(0, str(unpacked))
        import PIL
    from PIL import Image, ImageDraw, ImageFont
    return Image, ImageDraw, ImageFont


class Page:
    """All coordinates and text boxes use final-output pixels."""

    def __init__(self, Image, ImageDraw, ImageFont):
        self.Image = Image
        self.ImageFont = ImageFont
        self.image = Image.new("RGB", (SIZE * SCALE, SIZE * SCALE), PAPER)
        self.draw = ImageDraw.Draw(self.image)
        self.fonts = {}

    def font(self, face, size):
        key = (face, round(size * SCALE))
        if key not in self.fonts:
            self.fonts[key] = self.ImageFont.truetype(
                str(ROOT / "assets" / "fonts" / f"{face}.ttf"), key[1],
                layout_engine=self.ImageFont.Layout.BASIC,
            )
        return self.fonts[key]

    def rect(self, box, fill, outline=None, width=1):
        self.draw.rectangle(tuple(round(v * SCALE) for v in box),
                            fill=fill, outline=outline, width=round(width * SCALE))

    def ellipse(self, box, fill=None, outline=None, width=1):
        self.draw.ellipse(tuple(round(v * SCALE) for v in box),
                          fill=fill, outline=outline, width=round(width * SCALE))

    def line(self, points, fill, width=1):
        self.draw.line([(round(x * SCALE), round(y * SCALE)) for x, y in points],
                       fill=fill, width=max(1, round(width * SCALE)), joint="curve")

    def polygon(self, points, fill):
        self.draw.polygon([(round(x * SCALE), round(y * SCALE)) for x, y in points],
                          fill=fill)

    def arc(self, box, start, end, fill, width=1):
        self.draw.arc(tuple(round(v * SCALE) for v in box), start, end,
                      fill=fill, width=round(width * SCALE))

    def width(self, text, font):
        bounds = self.draw.textbbox((0, 0), text, font=font)
        return max(self.draw.textlength(text, font=font), bounds[2]-bounds[0]) / SCALE

    def text(self, text, x, y, font, fill=INK):
        # Align the visible ink to the specified top edge, not the font baseline.
        bounds = self.draw.textbbox((0, 0), text, font=font)
        self.draw.text((round(x * SCALE) - bounds[0], round(y * SCALE) - bounds[1]),
                       text, font=font, fill=fill)

    def wrap(self, text, font, width):
        lines = []
        for paragraph in text.split("\n"):
            current = ""
            for word in paragraph.split():
                candidate = f"{current} {word}" if current else word
                if self.width(candidate, font) <= width:
                    current = candidate
                    continue
                if current:
                    lines.append(current)
                    current = ""
                # Long tokens also wrap, rather than escaping the text box.
                while self.width(word, font) > width:
                    end = 1
                    while end < len(word) and self.width(word[:end + 1], font) <= width:
                        end += 1
                    lines.append(word[:end])
                    word = word[end:]
                current = word
            if current:
                lines.append(current)
        return lines

    def fit(self, text, face, box, size, max_lines=1, min_size=5, align="left", fill=INK,
            line_spacing=1.18):
        x, y, width, height = box
        chosen = None
        # Third-pixel increments keep fitting precise without font raster scaling.
        for units in range(round(size * SCALE), round(min_size * SCALE) - 1, -1):
            font = self.font(face, units / SCALE)
            lines = self.wrap(text, font, width)
            bounds = [self.draw.textbbox((0, 0), line, font=font) for line in lines]
            ink_height = max((b[3] - b[1] for b in bounds), default=0) / SCALE
            advance = max(ink_height + 2, units / SCALE * line_spacing)
            total = ink_height + advance * max(0, len(lines) - 1)
            if len(lines) <= max_lines and total <= height:
                chosen = (font, lines, advance)
                break
        if chosen is None:
            raise ValueError(f"Text does not fit its box: {text!r}")
        font, lines, advance = chosen
        for i, line in enumerate(lines):
            offset = (width - self.width(line, font)) / 2 if align == "center" else 0
            self.text(line, x + offset, y + i * advance, font, fill)
        return font

    def badge(self, number, x, y, radius=8):
        self.ellipse((x-radius, y-radius, x+radius, y+radius), GOLD)
        font = self.font("bodybold", 9 if number < 10 else 8)
        bounds = self.draw.textbbox((0, 0), str(number), font=font)
        h = (bounds[3] - bounds[1]) / SCALE
        self.text(str(number), x-self.width(str(number), font)/2, y-h/2, font, NAVY)

    def scene(self, key, x, y, w, h):
        """A shared 220 x 66 drawing space keeps twelve icons visually coherent."""
        sx, sy = w / 220, h / 66

        def pt(a, b):
            return x + a*sx, y + b*sy

        def rect(box, color, outline=None, width=1):
            self.rect((*pt(box[0], box[1]), *pt(box[2], box[3])), color, outline, width)

        def ellipse(box, color=None, outline=None, width=1):
            self.ellipse((*pt(box[0], box[1]), *pt(box[2], box[3])), color, outline, width)

        def line(points, color=NAVY, width=1.5):
            self.line([pt(a, b) for a, b in points], color, width)

        def poly(points, color=NAVY):
            self.polygon([pt(a, b) for a, b in points], color)

        def arc(box, start, end, color=NAVY, width=1.5):
            self.arc((*pt(box[0], box[1]), *pt(box[2], box[3])), start, end, color, width)

        def flame(a, b, scale=1):
            poly([(a-10*scale,b), (a-13*scale,b-12*scale), (a-4*scale,b-20*scale),
                  (a-3*scale,b-32*scale), (a+6*scale,b-23*scale),
                  (a+5*scale,b-13*scale), (a+12*scale,b-19*scale),
                  (a+12*scale,b-7*scale), (a+7*scale,b)], RED)
            poly([(a-4*scale,b), (a-5*scale,b-9*scale), (a+1*scale,b-18*scale),
                  (a+6*scale,b-6*scale), (a+4*scale,b)], GOLD)

        def shield(a, b, scale=1):
            poly([(a-15*scale,b-20*scale), (a,b-25*scale), (a+15*scale,b-20*scale),
                  (a+13*scale,b), (a,b+10*scale), (a-13*scale,b)], GOLD)
            line([(a-7*scale,b-7*scale), (a-1*scale,b-1*scale),
                  (a+8*scale,b-12*scale)], NAVY, 2)

        rect((0, 0, 220, 66), PALE)
        if key in ("tanker", "shipfire"):
            for row in (53, 60):
                line([(i, row + (2 if (i//8) % 2 else 0)) for i in range(8, 213, 8)], MUTED, 1)
            poly([(34,39),(182,39),(166,51),(47,51)])
            rect((44,26,71,39), NAVY)
            rect((50,21,62,26), NAVY)
            rect((48,29,54,32), PALE)
            rect((58,29,65,32), PALE)
            if key == "tanker":
                for a in (81, 111, 141):
                    rect((a,30,a+24,39), MUTED)
                line([(61,20),(61,12)], NAVY)
                flame(159,39,.8)
            else:
                for a in (79, 101, 123):
                    rect((a,29,a+19,38), GOLD)
                    line([(a+4,30),(a+4,37)], NAVY, .6)
                ellipse((153,2,169,15), MUTED)
                ellipse((164,0,185,12), MUTED)
                flame(155,38,.85)
        elif key in ("missiles", "strike"):
            for a, height in ((28,18),(49,28),(72,22),(96,35),(120,20),(143,26)):
                rect((a,57-height,a+18,57), NAVY)
                for b in range(59-height, 53, 7):
                    rect((a+4,b,a+6,b+2), PALE)
            line([(23,57),(170,57)], NAVY)
            if key == "missiles":
                arc((21,3,172,85), 191, 318, RED, 1.8)
                arc((44,12,192,96), 197, 302, RED, 1)
                poly([(125,9),(137,11),(130,19)], RED)
                poly([(143,23),(154,26),(147,32)], RED)
            else:
                burst = []
                for i in range(20):
                    angle = -math.pi/2 + i*math.pi/10
                    r = 20 if i % 2 == 0 else 9
                    burst.append((102+math.cos(angle)*r,25+math.sin(angle)*r))
                poly(burst, RED)
            shield(185,41,.8)
        elif key == "summit":
            ellipse((70,7,121,58), None, NAVY, 2)
            ellipse((84,7,107,58), None, NAVY, 1)
            line([(71,32),(120,32)], NAVY, 1)
            arc((70,17,121,44), 0, 360, NAVY, 1)
            rect((140,10,149,46), PAPER, RED, 2)
            ellipse((134,40,155,60), RED)
            rect((143,24,146,48), RED)
            for b in (15,24,33):
                line([(151,b),(158,b)], RED, 1)
            line([(53,59),(169,59)], GOLD, 2)
        elif key == "quake":
            poly([(17,49),(61,10),(92,44),(124,4),(171,48),(199,27),(215,58),(17,58)])
            poly([(50,20),(61,10),(74,24),(63,21)], PAPER)
            poly([(111,17),(124,4),(139,21),(123,16)], PAPER)
            line([(112,26),(101,37),(112,44),(103,52),(117,61)], GOLD, 2.5)
            line([(10,54),(38,54),(44,48),(50,60),(58,35),(66,62),(73,50),
                  (81,54),(91,54)], RED, 1.7)
        elif key == "bottle":
            poly([(79,10),(99,10),(99,24),(107,30),(107,59),(71,59),(71,30),(79,24)])
            rect((79,5,99,11), GOLD)
            rect((76,31,102,54), PAPER)
            ellipse((82,34,97,45), NAVY)
            rect((86,43,93,48), NAVY)
            ellipse((85,38,88,41), PAPER)
            ellipse((91,38,94,41), PAPER)
            line([(82,49),(97,54)], NAVY, 1)
            line([(97,49),(82,54)], NAVY, 1)
            poly([(140,12),(166,55),(115,55)], RED)
            rect((138,28,142,40), PAPER)
            ellipse((138,44,142,48), PAPER)
        elif key == "factory":
            poly([(30,56),(30,33),(61,21),(61,33),(90,21),(90,33),(121,21),
                  (121,34),(171,34),(171,56)])
            rect((146,11,161,37), NAVY)
            for a in range(40, 141, 23):
                rect((a,41,a+12,49), PAPER)
            flame(184,55,1.2)
            line([(21,58),(205,58)], NAVY, 1)
        elif key == "march":
            for i, a in enumerate((37,66,95,124,153,182)):
                b = 35 + (i%2)*3
                ellipse((a-5,b-10,a+5,b), NAVY)
                poly([(a-6,b+2),(a+6,b+2),(a+9,54),(a-9,54)])
                line([(a-4,53),(a-5,63)], NAVY, 3)
                line([(a+4,53),(a+5,63)], NAVY, 3)
            rect((64,4,157,19), RED)
            line([(66,19),(66,46)], NAVY, 1.5)
            line([(155,19),(155,46)], NAVY, 1.5)
            line([(78,11),(142,11)], PAPER, 2)
            line([(91,15),(131,15)], PAPER, 1)
        elif key == "capture":
            points = []
            for i in range(12):
                angle = -math.pi/2 + i*math.pi/6
                r = 28 if i%2 == 0 else 14
                points.append((88+math.cos(angle)*r,33+math.sin(angle)*r))
            poly(points, GOLD)
            ellipse((76,21,100,45), None, NAVY, 1.5)
            ellipse((83,28,93,38), NAVY)
            ellipse((139,32,163,57), None, NAVY, 3)
            ellipse((166,17,190,42), None, NAVY, 3)
            line([(161,39),(172,34)], NAVY, 3)
            rect((159,34,165,43), NAVY)
            rect((167,30,173,37), NAVY)
        elif key == "mercury":
            # Mercury sits at a focus, away from the ellipse's centre. The
            # spacecraft follows the orbit rather than a ring across the globe.
            orbit_cx, orbit_cy, orbit_rx, orbit_ry = 121, 34, 76, 29
            ellipse((orbit_cx-orbit_rx, orbit_cy-orbit_ry,
                     orbit_cx+orbit_rx, orbit_cy+orbit_ry), None, MUTED, 1.1)
            ellipse((73,11,120,58), GOLD)
            ellipse((86,19,96,29), None, NAVY, .8)
            ellipse((103,34,113,44), None, NAVY, .8)
            ellipse((84,44,90,50), NAVY)
            angle = -math.pi/4
            craft_x = orbit_cx + orbit_rx*math.cos(angle)
            craft_y = orbit_cy + orbit_ry*math.sin(angle)
            rect((craft_x-4,craft_y-4,craft_x+4,craft_y+4), NAVY)
            rect((craft_x-17,craft_y-4,craft_x-7,craft_y+4), MUTED)
            rect((craft_x+7,craft_y-4,craft_x+17,craft_y+4), MUTED)
            line([(craft_x-7,craft_y),(craft_x+7,craft_y)], NAVY, 1)
            line([(craft_x,craft_y-4),(craft_x+4,craft_y-9)], NAVY, 1)
            for a,b in ((30,13),(207,44),(164,58)):
                line([(a-2,b),(a+2,b)], NAVY, .7)
                line([(a,b-2),(a,b+2)], NAVY, .7)
        elif key == "cricket":
            for a in (137,148,159):
                rect((a,20,a+3,59), NAVY)
            line([(137,19),(148,19)], GOLD, 2)
            line([(149,19),(162,19)], GOLD, 2)
            poly([(67,17),(77,12),(102,48),(88,59),(64,25)], GOLD)
            line([(64,18),(56,7)], NAVY, 5)
            ellipse((109,46,124,61), RED)
            arc((110,46,121,61), 270, 90, PAPER, 1)
            line([(46,61),(177,61)], MUTED, 1)
        else:
            raise ValueError(f"Unknown scene key: {key}")


def masthead(page, data):
    page.rect((0,0,1024,92), NAVY)
    page.fit("THE WORLD IN ONE IMAGE", "masthead", (24,11,976,50), 48,
             align="center", fill=PAPER)
    page.line([(28,65),(996,65)], GOLD, 1)
    subline = data["masthead"]["date"] + "    /    " + data["masthead"]["story_count"]
    page.fit(subline, "headline", (30,73,964,15), 12.5, align="center", fill=PAPER)


# Small, hand-drawn continental outlines are geometry, independent of news text.
LAND = (
    ((-168,70),(-135,71),(-121,59),(-105,56),(-84,50),(-61,53),(-52,46),
     (-68,43),(-80,27),(-97,26),(-97,22),(-87,21),(-89,17),(-94,16),
     (-105,20),(-110,27),(-117,33),(-126,43),(-146,58)),
    ((-98,21),(-84,22),(-76,9),(-82,7),(-93,16)),
    ((-81,12),(-62,10),(-35,-6),(-42,-22),(-54,-34),(-68,-55),(-72,-34),
     (-71,-18),(-77,-9),(-81,-4),(-80,2)),
    ((-53,82),(-22,76),(-42,59),(-58,62)),
    ((-11,36),(-10,59),(7,71),(32,70),(40,59),(40,48),(41,42),
     (36,36),(26,36),(23,40),(13,36)),
    ((-18,34),(10,37),(33,30),(43,11),(35,-5),(31,-28),(18,-35),(9,-15),(-9,5)),
    ((29,70),(65,77),(112,73),(179,66),(161,52),(143,45),(126,28),(107,6),
     (93,20),(79,7),(66,26),(43,12),(32,31),(45,48)),
    ((97,8),(119,5),(133,-4),(151,-6),(153,-11),(125,-10),(102,-5)),
    ((112,-11),(137,-12),(154,-28),(144,-39),(116,-32)),
    ((165,-35),(179,-39),(173,-48),(167,-46)),
    ((130,33),(141,45),(146,43),(137,32)),
    ((45,-13),(50,-17),(49,-25),(44,-25)),
    ((-10,51),(-7,59),(0,58),(2,51)),
)

# Use the scene key to anchor pins, preserving the leads' order from the JSON.
LOCATIONS = {
    "tanker": (56.3,26.6), "missiles": (46.7,24.7), "summit": (30.7,36.9),
    "shipfire": (27,60), "strike": (33.4,47.9), "quake": (-75.2,-11.5),
    "bottle": (93.9,24.8), "factory": (114,-3), "march": (7.8,48.6),
    "capture": (-107.4,24.8), "cricket": (174.8,-41.3),
}
# Anchors are lon/lat: Strasbourg, Junin, Sinaloa and Wellington, for example.
# European and Gulf badges stay close to their anchors, with short leader lines.
PIN_OFFSETS = {
    "tanker": (3,3), "missiles": (-1,5), "summit": (17,4),
    "shipfire": (10,-4), "strike": (27,-2), "march": (0,0),
    "quake": (3,0), "capture": (4,-1),
}


def inside(px, py, polygon):
    contained = False
    previous = polygon[-1]
    for current in polygon:
        ax, ay = previous
        bx, by = current
        if (ay > py) != (by > py) and px < (bx-ax)*(py-ay)/(by-ay)+ax:
            contained = not contained
        previous = current
    return contained


def map_strip(page, data):
    page.rect((0,92,1024,180), PAPER)
    page.fit("WHERE IT\nHAPPENED", "headline", (24,114,115,35), 16, max_lines=2)
    page.fit("12 LEADS / 12 LOCATIONS", "bodybold", (24,158,124,13), 7.5, fill=MUTED)
    left, top, width, height = 170, 100, 717, 79

    def project(lon, lat):
        return left+(lon+180)/360*width, top+(83-lat)/143*height

    for lon in range(-180,181,30):
        x,_ = project(lon,0)
        page.line([(x,top),(x,top+height)], "#e3e4dc", .45)
    for lat in range(-60,84,30):
        _,y = project(0,lat)
        page.line([(left,y),(left+width,y)], "#e3e4dc", .45)
    for polygon in LAND:
        page.polygon([project(lon,lat) for lon,lat in polygon], "#e0e4df")
    for lat in range(-54,82,6):
        for lon in range(-174,180,2):
            if any(inside(lon,lat,polygon) for polygon in LAND):
                x,y = project(lon,lat)
                page.ellipse((x-1.05,y-1.05,x+1.05,y+1.05), "#95a5ac")
    page.rect((917,108,998,179), PALE, RULE, .7)
    page.fit("SPACE", "headline", (924,115,67,10), 9.5, align="center", fill=MUTED)
    page.ellipse((934,136,971,167), None, MUTED, .8)
    page.ellipse((944,137,963,157), MUTED)
    for lead in data["leads"]:
        key = lead["scene_key"]
        if key == "mercury":
            page.badge(lead["number"],975,152,8)
            continue
        x,y = project(*LOCATIONS[key])
        dx,dy = PIN_OFFSETS.get(key,(0,0))
        if dx or dy:
            page.line([(x,y),(x+dx,y+dy)], NAVY, .8)
            page.ellipse((x-1.4,y-1.4,x+1.4,y+1.4), NAVY)
        page.badge(lead["number"],x+dx,y+dy,7.5)


def numbers_strip(page, data):
    page.rect((0,180,1024,218), NAVY)
    page.fit("THE DAY\nIN NUMBERS", "headline", (24,187,104,26), 11,
             max_lines=2, fill=PAPER)
    x = 141
    # Description widths differ; all five numerical highlights stay prominent.
    widths = (143,174,157,138,247)
    for item,w in zip(data["numbers"],widths,strict=True):
        page.line([(x-9,188),(x-9,210)], "#425264", .6)
        number, description = item.split(" — ",1)
        page.fit(number, "headline", (x,185,w-10,19), 17, fill=GOLD)
        page.fit(description, "body", (x,205,w-10,10), 8, fill=PAPER)
        x += w


def lead_grid(page, data):
    left, top, width, row_height = 24, 229, 976, 166
    column_width = width / 4
    for col in range(1,4):
        x = left+col*column_width
        page.line([(x,top),(x,top+3*row_height-6)], RULE, .7)
    for row in range(1,3):
        y = top+row*row_height-1
        page.line([(left,y),(1000,y)], RULE, .8)
    for index,lead in enumerate(data["leads"]):
        col,row = index%4,index//4
        x = left+col*column_width+8
        y = top+row*row_height
        w = column_width-16
        page.badge(lead["number"],x+8,y+8,8)
        page.fit(lead["region"], "headline", (x+24,y+2,w-24,14), 10.5,
                 fill=MUTED)
        page.scene(lead["scene_key"],x,y+19,w,60)
        headline_font = page.fit(lead["headline"], "headline", (x,y+82,w,37), 17,
                                 max_lines=2, min_size=12.5)
        headline_lines = page.wrap(lead["headline"],headline_font,w)
        ink_height = max(page.draw.textbbox((0,0),line,font=headline_font)[3] -
                         page.draw.textbbox((0,0),line,font=headline_font)[1]
                         for line in headline_lines) / SCALE
        headline_advance = max(ink_height+2,headline_font.size/SCALE*1.18)
        dek_top = y+82+ink_height+headline_advance*(len(headline_lines)-1)+4
        page.fit(lead["dek"], "body", (x,dek_top,w,y+row_height-4-dek_top), 11.5,
                 max_lines=4, min_size=8.5, line_spacing=1.28)


def brief_layout(page, items, width, height):
    """Fit a whole column as a unit; keep every brief and use a shared size."""
    gap = 3
    for units in range(round(11.5*SCALE), round(8*SCALE)-1,-1):
        font = page.font("body",units/SCALE)
        advance = units/SCALE*1.28
        wrapped = [page.wrap(item,font,width-10) for item in items]
        last_ink = (page.draw.textbbox((0,0),wrapped[-1][-1],font=font)[3] -
                    page.draw.textbbox((0,0),wrapped[-1][-1],font=font)[1]) / SCALE
        total = (sum(map(len,wrapped))-1)*advance + last_ink + (len(items)-1)*gap
        if total <= height:
            # Share spare height between stories so every column reaches the
            # same baseline above the footer, without stretching the type.
            if len(items) > 1:
                gap += (height-total)/(len(items)-1)
            return font,advance,wrapped,gap
    raise ValueError("The briefs column is too tall")


def briefs(page, data):
    page.line([(24,735),(1000,735)], NAVY, 2)
    page.fit("AROUND THE WORLD IN BRIEF", "headline", (24,745,780,21), 18)
    count = sum(len(items) for _, items in sorted(data["briefs"].items()))
    page.fit(f"{count} MORE STORIES", "bodybold", (840,752,160,12), 9,
             align="center", fill=MUTED)
    page.line([(24,769),(1000,769)], RULE, .7)
    names = ("AMERICAS", "EUROPE", "MIDDLE EAST & AFRICA", "ASIA-PACIFIC · SCIENCE · SPORT")
    for index,name in enumerate(names):
        x = 34+index*244
        if index:
            page.line([(x-10,777),(x-10,992)], RULE, .7)
        page.fit(name, "headline", (x,776,230,17), 12.5, min_size=9)
        page.line([(x,793),(x+23,793)], GOLD, 2)
        font,advance,wrapped,gap = brief_layout(page,data["briefs"][name],230,191)
        y = 800
        for lines in wrapped:
            page.ellipse((x,y+3,x+2.5,y+5.5), GOLD)
            for line in lines:
                page.text(line,x+10,y,font)
                y += advance
            y += gap


def footer(page, data):
    page.line([(24,999),(1000,999)], NAVY, .8)
    # A restrained shear gives the bundled regular serif an italic character.
    font = page.font("serif",10)
    text = data["footer"]
    while page.width(text,font) > 955:
        font = page.font("serif",font.size/SCALE-1/3)
    bounds = page.draw.textbbox((0,0),text,font=font)
    layer = page.Image.new("RGBA",(bounds[2]-bounds[0]+24*SCALE,14*SCALE),(0,0,0,0))
    from PIL import ImageDraw
    ImageDraw.Draw(layer).text((12*SCALE-bounds[0],-bounds[1]),text,font=font,fill=MUTED)
    layer = layer.transform(layer.size,page.Image.Transform.AFFINE,
                            (1,.15,-1.5*SCALE,0,1,0),page.Image.Resampling.BICUBIC)
    page.image.paste(layer,((SIZE*SCALE-layer.width)//2,1007*SCALE),layer)


def main():
    output = Path(os.environ.get("MAKEFUN_OUTPUT_DIR","/output"))
    output.mkdir(parents=True,exist_ok=True)
    Image,ImageDraw,ImageFont = pillow()
    with (ROOT / "stories.json").open(encoding="utf-8") as source:
        data = json.load(source)
    if len(data["leads"]) != 12 or len(data["numbers"]) != 5:
        raise ValueError("Expected twelve leads and five numerical highlights")
    page = Page(Image,ImageDraw,ImageFont)
    masthead(page,data)
    map_strip(page,data)
    numbers_strip(page,data)
    lead_grid(page,data)
    briefs(page,data)
    footer(page,data)
    image = page.image.resize((SIZE,SIZE),Image.Resampling.LANCZOS)
    destination = output / "entry.png"
    image.save(destination,format="PNG",optimize=False,compress_level=9)
    if destination.stat().st_size >= 1024*1024:
        raise RuntimeError("PNG exceeds the 1 MiB size limit")
    print(f"{destination}: {image.width}x{image.height}, {destination.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
