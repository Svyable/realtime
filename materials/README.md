# Materials

Public-domain and CC0 beds, plus the scene kits an agent copies when it makes an hour.

`realtime materials` prints the index. The full map is [catalog.yaml](catalog.yaml). Recordist credits for the beds are in [sfx/nature/CREDITS.md](sfx/nature/CREDITS.md). Licenses were checked on 2026-10-07.

## Yule Love

A Christmas parlor, a hearth, snow at the window, and public-domain love songs and carols. Greensleeves is the same tune as What Child Is This. The Water Is Wide is the love song. Silent Night and Auld Lang Syne close the night. The piano is in the doorway, not shut behind it, and the room sits 11 LU under the piano.

```bash
realtime kit yule-love
# put a 16:9 keyframe.jpg in scenes/yule-love/ (see the prompt.md the kit writes)
realtime build scenes/yule-love/scene.yaml --root . --test
```

`--root` is this clone, because the scene points at `materials/sfx/nature/…`.

Train wheels and church bells are not in git. `realtime setup --sfx` downloads those four checked recordings into the cache. The parish-bells and night-train kits use them.
