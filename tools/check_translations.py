"""Checks that every translation key used in the code exists in lang/en.json and in all other languages,
and that {placeholders} match. Run: python tools/check_translations.py"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PREFIX = r"(?:act|tab|group|side|theme|field|repeat|col|panel|aspect|sort|sc|about|lyr|msg|btn|tag|info|set|splash|st|osd|sub|menu|pl|lib|browse|batch|ren|cover|mb|dlg|np|search)"
src = "".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(ROOT, "*.py")))
used = set(re.findall(r"""["'](%s\.[a-z_0-9]+)["']""" % PREFIX, src)) | {"yes", "no"}
used |= {"act." + a for a in re.findall(r'mk\("([a-z_0-9]+)"', src)}
used |= {"act.browse_" + m for m in ("artists", "albums", "genres", "tracks")} | {"act.pause"}
from cm_main import RIBBONS, TABS  # noqa: E402
import cm_tags  # noqa: E402
used |= {"tab." + t for t in TABS} | {"group." + g for r in RIBBONS.values() for g, _ in r}
used |= {"field." + f for f in cm_tags.FIELDS} | {"repeat." + r for r in ("off", "all", "one")}
used |= {"theme." + t + s for t in ("system", "light", "dark") for s in ("", "_desc")}
used |= {"side." + v for v in ("music", "videos", "favourites", "recent", "most", "nocover", "nolyrics", "library", "smart", "playlists")}
used -= {"cover.jpg", "splash.png"}
langs = {os.path.basename(p)[:-5]: json.load(open(p, encoding="utf-8")) for p in glob.glob(os.path.join(ROOT, "lang", "*.json"))}
en = langs["en"]
bad = 0
for k in sorted(used - set(en)):
    print("missing in en:", k)
    bad += 1
for code, d in sorted(langs.items()):
    if code == "en":
        continue
    for k in sorted(set(en) - set(d)):
        if not k.startswith("_"):
            print(f"missing in {code}: {k}")
            bad += 1
    for k, v in d.items():
        if k in en and set(re.findall(r"\{(\w+)", v)) != set(re.findall(r"\{(\w+)", en[k])):
            print(f"placeholders differ in {code}: {k}")
            bad += 1
print("unused in en:", sorted(k for k in set(en) - used if not k.startswith("_")))
print("OK" if not bad else f"{bad} problem(s)")
sys.exit(1 if bad else 0)
