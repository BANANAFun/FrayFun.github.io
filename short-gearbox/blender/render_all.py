# Финальный рендер Cycles CPU: python render_all.py <PROJECT> [pct] [spp] — дорендеривает недостающие кадры.
import bpy, sys, time
from pathlib import Path
P = Path(sys.argv[1]); pct = int(sys.argv[2]) if len(sys.argv) > 2 else 50; spp = int(sys.argv[3]) if len(sys.argv) > 3 else 8
bpy.ops.wm.open_mainfile(filepath=str(P / "scene.blend"))
sc = bpy.context.scene
sc.render.engine = "CYCLES"
c = sc.cycles
c.device = "CPU"; c.samples = spp; c.use_adaptive_sampling = True
c.use_denoising = True; c.denoiser = "OPENIMAGEDENOISE"
c.max_bounces = 4; c.glossy_bounces = 2; c.transparent_max_bounces = 16
c.caustics_reflective = c.caustics_refractive = False; c.blur_glossy = 1.0
sc.render.use_persistent_data = True
sc.render.resolution_percentage = pct
sc.render.image_settings.file_format = "JPEG"; sc.render.image_settings.quality = 95
out = P / "renders" / "final"; out.mkdir(parents=True, exist_ok=True)
for f in range(sc.frame_start, sc.frame_end + 1):
    fp = out / f"f_{f:04d}.jpg"
    if fp.exists() and fp.stat().st_size > 0:
        continue
    sc.frame_set(f); sc.render.filepath = str(out / f"tmp_{f:04d}.jpg")
    t = time.time(); bpy.ops.render.render(write_still=True)
    Path(sc.render.filepath).rename(fp)
    print("FRAME", f, round(time.time() - t, 1), flush=True)
print("ALLDONE")
