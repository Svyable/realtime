"""Run a scene. Stages whose inputs, code, and upstream keys are unchanged are skipped.

Audio (compose through master) and picture (plate, loop, thumbnail) share nothing until
the final mux, so those two chains run at the same time.
"""
import hashlib, json, math, os, shutil, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from realtime.graph import AUDIO, NEEDS, VISUAL, expand_needs, stage_key
from realtime.runtime import Workspace, activate, asset_dirs, current, default_media
from realtime.scene import keyframe_path, load
from realtime.version import __version__


def sh(*a):
    subprocess.run([str(x) for x in a], check=True)


def probe_dur(p):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def _sha256_file(path):
    if not os.path.exists(path):
        return 'missing'
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


class Build:
    def __init__(self, scene, test=False, force=(), only=None, procs=6, out=None, root=None):
        ov = {'duration_min': 3, 'visual': {'loop_s': 12}} if test else {}
        self.cfg = load(scene, ov)
        self.test = test
        self.dur = self.cfg['duration_min'] * 60
        root = root or os.getcwd()
        media = default_media()
        slug_out = out or os.path.join(media, self.cfg['slug'], 'test' if test else '')
        self.ws = activate(Workspace(self.cfg['_file'], root, slug_out, asset_dirs()))
        self.out = str(self.ws.out)
        self.work = os.path.join(self.out, 'work')
        os.makedirs(self.work, exist_ok=True)
        self.force = set(force)
        self.user_force = set(force)
        self.only = expand_needs(only) if only else None
        self.procs = procs
        self._lock = threading.RLock()
        self.manifest_path = os.path.join(self.out, '.realtime-manifest.json')
        self.manifest = {}
        if os.path.exists(self.manifest_path):
            self.manifest = json.load(open(self.manifest_path))
        self.logf = open(os.path.join(self.out, 'build.log'), 'a')

    def log(self, *m):
        s = ' '.join(str(x) for x in m)
        with self._lock:
            print(s, flush=True)
            self.logf.write(s + '\n')
            self.logf.flush()

    def p(self, *n):
        return os.path.join(self.out, *n)

    def key(self, stage):
        extra = {}
        if stage == 'plate':
            extra['keyframe'] = _sha256_file(keyframe_path(self.cfg))
        with self._lock:
            up = {dep: self.manifest.get('stages', {}).get(dep, {}).get('key') for dep in NEEDS[stage]}
        return stage_key(stage, self.cfg, up, self.test, __version__, extra)

    def commit(self, stage):
        with self._lock:
            self.manifest.setdefault('stages', {})[stage] = {'key': self.key(stage)}
            self.manifest['version'] = __version__
            tmp = self.manifest_path + '.part'
            json.dump(self.manifest, open(tmp, 'w'), indent=1)
            os.replace(tmp, self.manifest_path)

    def fresh(self, stage, *outs):
        """True when this stage should run."""
        if self.only and stage not in self.only:
            return False
        if 'all' in self.force or stage in self.force:
            return True
        if not all(os.path.exists(o) for o in outs):
            return True
        stored = self.manifest.get('stages', {}).get(stage, {}).get('key')
        return stored != self.key(stage)

    def wants(self, stages):
        return self.only is None or bool(self.only & set(stages))

    def compose(self):
        from realtime.music import setlist as SL
        from realtime.music.compose import compose_setlist
        sl = self.p('setlist.json')
        if self.fresh('compose', sl):
            if self.cfg['music'].get('setlist'):
                src = self.cfg['music']['setlist']
                if not os.path.isabs(src):
                    beside = os.path.join(self.cfg['_dir'], src)
                    src = beside if os.path.exists(beside) else current().resolve(src)
                data = json.load(open(src))
                if self.test:
                    data['pieces'] = [dict(data['pieces'][0], form=SL.TEST_FORM)]
            else:
                mx = self.cfg['mix']
                music_min = (self.dur - mx['first_piece_at'] - mx['end_padding']) / 60 * 0.9
                data = SL.generate(self.cfg, music_min, self.test)
            json.dump(data, open(sl, 'w'), indent=1)
            shutil.rmtree(self.p('midi'), ignore_errors=True)
            for f in os.listdir(self.work):
                if f.startswith('dry_'):
                    os.remove(os.path.join(self.work, f))
            self.log(f'[compose] {len(data["pieces"])} pieces ({data.get("mood", "hand-written")})')
            compose_setlist(data, self.p('midi'), self.log)
            self.commit('compose')
        return json.load(open(sl))

    def audio(self):
        import realtime.audio.mix as A
        data = self.compose()
        tl = self.p('timeline.json')
        mids = sorted(f for f in os.listdir(self.p('midi')) if f.endswith('.mid'))
        midis = [(self.p('midi', f), s) for f, s in zip(mids, data['pieces'])]
        if self.fresh('piano', tl, f'{self.work}/piano.npy'):
            self.log(f'[piano] distance={self.cfg["piano"]["distance"]} -> {A.preset(self.cfg)}')
            timeline = {'pieces': A.build_piano_bus(self.cfg, self.work, midis, self.dur, self.log)}
            json.dump(timeline, open(tl, 'w'), indent=1)
            self.commit('piano')
        timeline = json.load(open(tl))
        if self.fresh('ambience', f'{self.work}/bed.npy'):
            self.log(f'[ambience] bed {self.cfg["mix"]["bed_lu_below_piano"]} LU under the piano')
            timeline['accents'] = A.build_ambience(self.cfg, self.work, self.dur, self.log)
            json.dump(timeline, open(tl, 'w'), indent=1)
            self.commit('ambience')
        if self.fresh('mix', f'{self.work}/mix.npy'):
            A.mixdown(self.cfg, self.work, self.dur)
            self.commit('mix')
            self.log('[mix] done')
        if self.fresh('master', self.p('audio_master.wav')):
            m = A.master(self.cfg, self.work, self.p('audio_master.wav'))
            self.log(f'[master] {m}')
            json.dump(m, open(self.p('work', 'master.json'), 'w'))
            self.commit('master')
        return timeline

    def visuals(self):
        import cv2
        import realtime.visual.engine as V
        v = self.cfg['visual']
        plate = self.p('plate.png')
        if self.fresh('plate', plate):
            cv2.imwrite(plate, V.load_plate(self.cfg, v['width'], v['height'], self.log))
            self.commit('plate')
            self.log('[plate] ok')
        pl = cv2.imread(plate)
        V.regions_preview(self.cfg, pl, self.p('regions-preview.jpg'))
        loop = self.p('loop.mp4')
        if self.fresh('loop', loop):
            V.prepare(self.cfg, pl, self.test)
            self.log(f'[loop] {v["loop_s"]}s x {v["fps"]} fps')
            t0 = time.time()
            V.render_loop(loop, self.procs, log=self.log)
            self.log(f'[loop] {time.time() - t0:.0f}s')
            self.commit('loop')
        if self.fresh('thumbnail', self.p('thumbnail.jpg')):
            self.thumbnail(pl)
            self.commit('thumbnail')
        return pl

    def assemble(self):
        full = self.p(f'{self.cfg["slug"]}{"-test" if self.test else ""}.mp4')
        if not self.fresh('video', full):
            return full
        L = self.cfg['visual']['loop_s']
        n = math.ceil(self.dur / L)
        loop = self.p('loop.mp4')
        f, l = f'{self.work}/seg_first.mp4', f'{self.work}/seg_last.mp4'
        enc = ['-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-tune', 'film', '-pix_fmt', 'yuv420p',
               '-g', str(self.cfg['visual']['fps'] * 4)]
        sh('ffmpeg', '-v', 'error', '-y', '-i', loop, '-vf', 'fade=in:st=0:d=3', *enc, f)
        tail = self.dur - (n - 1) * L
        sh('ffmpeg', '-v', 'error', '-y', '-i', loop, '-vf', f'trim=0:{tail},fade=out:st={max(0, tail - 4)}:d=4', *enc, l)
        with open(f'{self.work}/concat.txt', 'w') as c:
            c.write(f"file '{f}'\n" + f"file '{loop}'\n" * max(0, n - 2) + (f"file '{l}'\n" if n > 1 else ''))
        sh('ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', f'{self.work}/concat.txt',
           '-i', self.p('audio_master.wav'), '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac',
           '-b:a', '320k', '-t', str(self.dur), '-movflags', '+faststart', full)
        self.commit('video')
        self.log(f'[video] {full}')
        return full

    def preview(self, full, timeline):
        out = self.p('preview-60s.mp4')
        if not self.fresh('preview', out):
            return
        st = self.cfg['preview']['start_s']
        if st == 'auto':
            ps = timeline['pieces']
            d = [p for p in ps if 'door_open' in p]
            st = d[0]['door_open'] - 15 if d else (ps[min(1, len(ps) - 1)]['start'] + 20 if ps else 30)
        st = max(0, min(st, self.dur - 60))
        sh('ffmpeg', '-v', 'error', '-y', '-ss', str(st), '-i', full, '-t', '60', '-c:v', 'libx264', '-crf', '20',
           '-preset', 'medium', '-af', 'afade=in:d=2,afade=out:st=57:d=3', '-vf', 'fade=in:d=1,fade=out:st=58.5:d=1.5',
           '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', out)
        self.commit('preview')
        self.log(f'[preview] from {st:.0f}s')

    def thumbnail(self, plate):
        import cv2
        import realtime.visual.engine as V
        T = self.cfg['thumbnail']
        V.prepare(self.cfg, plate, True)
        img = cv2.cvtColor(V.frame(0, grain=False), cv2.COLOR_BGR2RGB)
        im = Image.fromarray(img).resize((1280, 720), Image.LANCZOS)
        im = Image.eval(im, lambda v: min(255, int(v * (1 + T.get('lift', 0.08)))))
        im.save(self.p('thumbnail-notext.jpg'), quality=92)
        if T.get('text'):
            fp = current().find('fonts', T['font']) or ''
            font = ImageFont.truetype(fp, T['size']) if fp and os.path.exists(fp) else ImageFont.load_default()
            d0 = ImageDraw.Draw(im)
            bb = d0.multiline_textbbox((0, 0), T['text'], font=font, align='center')
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            if isinstance(T['position'], str):
                pos = {'top-right': (1280 - tw - 60, 50), 'top-left': (60, 50),
                       'bottom-left': (60, 720 - th - 70), 'bottom-right': (1280 - tw - 60, 720 - th - 70),
                       'top-center': ((1280 - tw) // 2, 50)}[T['position']]
            else:
                pos = (int(T['position'][0] * 1280), int(T['position'][1] * 720))
            glow = Image.new('RGBA', im.size, (0, 0, 0, 0))
            ImageDraw.Draw(glow).multiline_text(pos, T['text'], font=font, fill=T['glow'], align='center')
            glow = glow.filter(ImageFilter.GaussianBlur(14))
            im = Image.alpha_composite(im.convert('RGBA'), glow)
            ImageDraw.Draw(im).multiline_text(pos, T['text'], font=font, fill=T['color'], align='center')
            im = im.convert('RGB')
        im.save(self.p('thumbnail.jpg'), quality=92)
        self.log('[thumbnail] ok')

    def qc(self, full, timeline):
        import cv2
        import realtime.audio.mix as A
        if not self.fresh('qc', self.p('qc', 'qc.json')):
            return json.load(open(self.p('qc', 'qc.json')))
        q = self.p('qc')
        os.makedirs(q, exist_ok=True)
        loop = self.p('loop.mp4')
        sh('ffmpeg', '-v', 'error', '-y', '-sseof', '-2', '-i', loop, '-i', loop, '-filter_complex',
           '[1:v]trim=0:2,setpts=PTS-STARTPTS[b];[0:v][b]concat=n=2:v=1[v]', '-map', '[v]',
           '-c:v', 'libx264', '-crf', '20', self.p('loop-check-4s.mp4'))
        cap = cv2.VideoCapture(loop)
        fr = []
        while True:
            ok, x = cap.read()
            if not ok:
                break
            fr.append(cv2.resize(x, (480, 270)).astype(np.float32))
        seam = float(np.abs(fr[-1] - fr[0]).mean())
        step = float(np.median([np.abs(fr[i + 1] - fr[i]).mean() for i in range(0, len(fr) - 1, max(1, len(fr) // 40))]))
        for t in [2, self.dur * 0.21, self.dur * 0.58, self.dur - 3]:
            sh('ffmpeg', '-v', 'error', '-y', '-ss', str(round(t, 2)), '-i', full, '-frames:v', '1',
               os.path.join(q, f'frame_{int(t):05d}.png'))
        dec = subprocess.run(['ffmpeg', '-v', 'error', '-i', full, '-f', 'null', '-'], capture_output=True, text=True).stderr.strip()
        r = {'duration_video': probe_dur(full), 'target_s': self.dur, 'loudness': A.ebur128(self.p('audio_master.wav')),
             'targets': self.cfg['master'], 'piano_minus_bed_LU_median_min_max': A.bed_vs_piano(self.work, timeline['pieces']),
             'bed_target_LU': self.cfg['mix']['bed_lu_below_piano'], 'loop_seam_diff': round(seam, 3),
             'loop_frame_step': round(step, 3), 'decode_errors': dec[:2000] or None,
             'pieces': len(timeline['pieces']), 'accents': timeline.get('accents', [])}
        r['pass'] = bool(abs(r['duration_video'] - self.dur) < 0.5
                         and r['loudness']['true_peak'] <= self.cfg['master']['true_peak'] + 0.05
                         and abs(r['loudness']['lufs'] - self.cfg['master']['lufs']) < 1.0
                         and not r['decode_errors'] and seam < step * 2.5)
        json.dump(r, open(os.path.join(q, 'qc.json'), 'w'), indent=1)
        self.commit('qc')
        self.log('[qc]', json.dumps(r))
        return r

    def release(self, full):
        out = self.p(f'release-{self.cfg["slug"]}.mp4')
        if not (self.cfg['release_encode'] or 'release' in self.user_force) or not self.fresh('release', out):
            return
        kbps = int((1.9 * 2 ** 30 * 8 / self.dur - 330_000) / 1000)
        kbps = min(kbps, 6000)
        X = ['-c:v', 'libx264', '-preset', 'medium', '-b:v', f'{kbps}k', '-maxrate', f'{int(kbps * 1.6)}k',
             '-bufsize', f'{kbps * 3}k', '-pix_fmt', 'yuv420p', '-x264-params', 'aq-mode=3', '-profile:v', 'high',
             '-passlogfile', f'{self.work}/p2']
        sh('ffmpeg', '-y', '-v', 'error', '-i', full, *X, '-pass', '1', '-an', '-f', 'null', os.devnull)
        sh('ffmpeg', '-y', '-v', 'error', '-i', full, *X, '-pass', '2', '-c:a', 'copy', '-movflags', '+faststart', out)
        self.commit('release')
        self.log(f'[release] {out} {os.path.getsize(out) / 2 ** 30:.2f} GiB')

    def run(self):
        t0 = time.time()
        self.log(f'=== {self.cfg["slug"]} {"TEST " if self.test else ""}{self.dur / 60:.0f} min -> {self.out}')
        do_audio = self.wants(AUDIO) or self.wants(('video', 'preview', 'qc', 'release'))
        do_visual = self.wants(VISUAL) or self.wants(('video', 'preview', 'qc', 'release'))
        tl = pl = None
        if do_audio and do_visual:
            with ThreadPoolExecutor(max_workers=2) as pool:
                fa = pool.submit(self.audio)
                fv = pool.submit(self.visuals)
                tl = fa.result()
                pl = fv.result()
        elif do_audio:
            tl = self.audio()
        elif do_visual:
            pl = self.visuals()
        if not self.wants(('video', 'preview', 'qc', 'release')):
            self.log(f'=== done in {(time.time() - t0) / 60:.1f} min')
            return None
        full = self.assemble()
        self.preview(full, tl)
        if pl is not None and self.fresh('thumbnail', self.p('thumbnail.jpg')):
            self.thumbnail(pl)
            self.commit('thumbnail')
        report = self.qc(full, tl)
        self.release(full)
        self.log(f'=== done in {(time.time() - t0) / 60:.1f} min')
        return report
