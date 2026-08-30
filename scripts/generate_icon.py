"""Generate RetroDisc's original caricature application icon locally."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)
S = 1024
im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)

# Soft shadow behind the circular disc.
shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
sd = ImageDraw.Draw(shadow)
sd.ellipse((71, 71, 953, 953), fill=(0, 0, 0, 150))
shadow = shadow.filter(ImageFilter.GaussianBlur(28))
im.alpha_composite(shadow)
d = ImageDraw.Draw(im)

# Optical disc with blue enamel rim and iridescent sectors.
d.ellipse((55, 45, 969, 959), fill=(20, 35, 65, 255), outline=(8, 14, 28, 255), width=28)
d.ellipse((88, 78, 936, 926), fill=(83, 129, 180, 255), outline=(203, 228, 246, 255), width=17)
for box, start, end, color in [
    ((111, 101, 913, 903), 205, 282, (53, 218, 233, 190)),
    ((124, 114, 900, 890), 285, 352, (236, 78, 148, 175)),
    ((142, 132, 882, 872), 354, 45, (251, 201, 57, 185)),
    ((160, 150, 864, 854), 48, 112, (103, 230, 132, 175)),
]:
    d.pieslice(box, start=start, end=end, fill=color)
d.ellipse((184, 174, 840, 830), fill=(26, 68, 123, 255), outline=(8, 23, 50, 255), width=18)
d.arc((103, 93, 921, 911), 190, 325, fill=(246, 253, 255, 235), width=20)
d.arc((121, 111, 903, 893), 12, 118, fill=(186, 229, 255, 160), width=13)

# Suit shoulders and torso.
d.ellipse((180, 650, 844, 1110), fill=(8, 21, 46, 255), outline=(4, 9, 22, 255), width=25)
d.polygon([(337, 680), (512, 995), (687, 680), (620, 615), (404, 615)], fill=(241, 245, 247, 255))
d.polygon([(182, 708), (357, 642), (484, 989), (292, 872)], fill=(14, 37, 75, 255), outline=(4, 11, 27, 255))
d.polygon([(842, 708), (667, 642), (540, 989), (732, 872)], fill=(14, 37, 75, 255), outline=(4, 11, 27, 255))
d.polygon([(477, 713), (547, 713), (578, 902), (512, 993), (446, 902)], fill=(190, 20, 35, 255), outline=(91, 7, 15, 255))
d.polygon([(477, 713), (512, 754), (547, 713), (528, 673), (496, 673)], fill=(222, 36, 49, 255))

# Ears behind the face.
d.ellipse((213, 356, 355, 598), fill=(221, 126, 63, 255), outline=(83, 38, 18, 255), width=18)
d.ellipse((669, 356, 811, 598), fill=(221, 126, 63, 255), outline=(83, 38, 18, 255), width=18)
d.arc((246, 397, 330, 554), 80, 275, fill=(151, 70, 34, 255), width=15)
d.arc((694, 397, 778, 554), 265, 100, fill=(151, 70, 34, 255), width=15)

# Caricatured orange-tan head: broad top, narrower chin.
d.polygon([(310, 268), (385, 203), (539, 177), (678, 224), (726, 341),
           (713, 520), (657, 658), (562, 716), (466, 704), (374, 647),
           (315, 525), (286, 374)], fill=(231, 142, 71, 255), outline=(73, 31, 13, 255))
d.ellipse((329, 260, 695, 669), fill=(232, 143, 73, 255))
# Face highlights and characteristic cheek shading.
d.ellipse((357, 306, 672, 570), fill=(244, 161, 84, 205))
d.ellipse((311, 437, 454, 611), fill=(213, 112, 57, 150))
d.ellipse((571, 437, 714, 611), fill=(213, 112, 57, 150))
d.arc((310, 270, 704, 692), 95, 265, fill=(78, 33, 15, 255), width=16)

# Exaggerated golden comb-over.
hair_dark = (142, 91, 22, 255)
hair = (246, 193, 63, 255)
hair_hi = (255, 225, 109, 255)
d.polygon([(287, 363), (302, 259), (363, 174), (471, 122), (623, 133),
           (714, 205), (744, 286), (673, 250), (591, 238), (506, 252),
           (421, 236), (349, 296)], fill=hair_dark, outline=(77, 43, 10, 255))
d.polygon([(306, 326), (327, 239), (409, 168), (522, 135), (636, 163),
           (707, 227), (655, 219), (579, 214), (507, 239), (426, 216),
           (357, 273)], fill=hair)
for pts in [
    [(340, 262), (425, 184), (538, 158)],
    [(385, 264), (481, 185), (608, 181)],
    [(443, 250), (534, 190), (667, 222)],
    [(495, 239), (584, 202), (700, 254)],
]:
    d.line(pts, fill=hair_hi, width=22, joint="curve")
# Swept hair tip.
d.polygon([(294, 323), (318, 247), (365, 214), (348, 337), (308, 383)], fill=hair, outline=hair_dark)

# Brows, narrowed smiling eyes.
d.line([(355, 365), (408, 340), (466, 352)], fill=(93, 52, 21, 255), width=25)
d.line([(558, 352), (616, 340), (669, 365)], fill=(93, 52, 21, 255), width=25)
d.ellipse((368, 365, 463, 420), fill=(246, 243, 224, 255), outline=(78, 35, 17, 255), width=12)
d.ellipse((561, 365, 656, 420), fill=(246, 243, 224, 255), outline=(78, 35, 17, 255), width=12)
d.ellipse((414, 377, 444, 412), fill=(40, 103, 139, 255))
d.ellipse((580, 377, 610, 412), fill=(40, 103, 139, 255))
d.ellipse((424, 385, 437, 399), fill=(9, 13, 18, 255))
d.ellipse((587, 385, 600, 399), fill=(9, 13, 18, 255))
# Smiling lower eyelids.
d.arc((362, 379, 467, 436), 8, 172, fill=(125, 57, 29, 255), width=12)
d.arc((557, 379, 662, 436), 8, 172, fill=(125, 57, 29, 255), width=12)

# Nose and laugh lines.
d.line([(513, 399), (487, 505), (521, 531), (559, 511)], fill=(157, 73, 37, 255), width=15, joint="curve")
d.line([(469, 523), (502, 540), (551, 530)], fill=(247, 179, 107, 255), width=10)
d.arc((326, 405, 458, 601), 300, 80, fill=(145, 62, 31, 255), width=13)
d.arc((568, 405, 700, 601), 100, 240, fill=(145, 62, 31, 255), width=13)

# Big unmistakable grin with teeth.
d.rounded_rectangle((367, 548, 657, 650), radius=47, fill=(80, 27, 15, 255), outline=(91, 35, 18, 255), width=12)
d.rounded_rectangle((386, 557, 638, 611), radius=22, fill=(255, 252, 231, 255))
for x in (432, 478, 524, 570):
    d.line((x, 560, x - 2, 608), fill=(193, 183, 158, 255), width=5)
d.arc((391, 594, 633, 642), 5, 175, fill=(198, 66, 54, 255), width=20)
d.arc((370, 530, 654, 667), 198, 342, fill=(119, 48, 25, 255), width=13)

# Small disc hub reflection peeking through as visual cue.
d.ellipse((760, 735, 914, 889), fill=(164, 218, 239, 245), outline=(247, 252, 255, 255), width=13)
d.ellipse((804, 779, 870, 845), fill=(24, 58, 105, 255), outline=(6, 19, 42, 255), width=10)
d.arc((775, 750, 900, 875), 195, 310, fill=(255, 255, 255, 230), width=13)

# Final crisp outer rim.
d.ellipse((55, 45, 969, 959), outline=(4, 8, 19, 255), width=24)

# Save master and icon sizes.
png = ASSETS / "retrodisc_1024.png"
ico = ASSETS / "retrodisc.ico"
im.save(png, optimize=True)
im.save(ico, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
# Separate previews are handy when visually checking small-icon readability.
for size in (16, 32, 48, 256):
    im.resize((size, size), Image.Resampling.LANCZOS).save(ASSETS / f"retrodisc_{size}.png")
print(png)
print(ico)
