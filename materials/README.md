# Materials

Public-domain and CC0 beds, plus the scene kits an agent copies when it makes an hour.

`realtime materials` prints the index. The full map is [catalog.yaml](catalog.yaml). Recordist credits for the curated beds are in [sfx/nature/CREDITS.md](sfx/nature/CREDITS.md) (checked 2026-10-07). The larger draw-pile is [sfx/pdsounds/](sfx/pdsounds/CREDITS.md): public-domain environmental recordings from PDSounds.org, checked on Commons on 2026-10-11.

## Yule Love

A Christmas parlor, a hearth, snow at the window, and public-domain love songs and carols. Greensleeves is the same tune as What Child Is This. The Water Is Wide is the love song. Silent Night and Auld Lang Syne close the night. The piano is in the doorway, not shut behind it, and the room sits 11 LU under the piano.

```bash
realtime kit yule-love
# put a 16:9 keyframe.jpg in scenes/yule-love/ (see the prompt.md the kit writes)
realtime build scenes/yule-love/scene.yaml --root . --test
```

`--root` is this clone, because the scene points at `materials/sfx/nature/…`.

Parish bells are in `sfx/pdsounds/interior/`. Carriage wheels for the night-train kit are still fetched with `realtime setup --sfx`. The same command also fetches a steam whistle. The train-ride recording is already in `sfx/pdsounds/transit/`.
