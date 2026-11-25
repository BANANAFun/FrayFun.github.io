# Контрольные кадры EEVEE: python keys.py <PROJECT> <pct> f1 f2 ... → checks/keys_eevee.jpg
import bpy, sys, time, subprocess
from pathlib import Path
P = Path(sys.argv[1]); pct = int(sys.argv[2]); frames = [int(x) for x in sys.argv[3:]]
bpy.ops.wm.open_mainfile(filepath=str(P / "scene.blend"))
sc = bpy.context.scene
ENG = __import__("os").environ.get("ENG", "BLENDER_EEVEE"); sc.render.engine = ENG
if ENG == "CYCLES":
    sc.cycles.device = "CPU"; sc.cycles.samples = int(__import__("os").environ.get("SPP", "16")); sc.cycles.use_denoising = True; sc.cycles.denoiser = "OPENIMAGEDENOISE"; sc.cycles.max_bounces = 4; sc.cycles.use_adaptive_sampling = True; sc.render.use_persistent_data = True; sc.cycles.blur_glossy = 1.0; sc.cycles.caustics_reflective = False; sc.cycles.caustics_refractive = False
sc.render.resolution_percentage = pct
sc.render.image_settings.file_format = "JPEG"
out = P / "checks" / "k"; out.mkdir(parents=True, exist_ok=True)
paths = []
for f in frames:
    sc.frame_set(f); sc.render.filepath = str(out / f"k_{f:04d}.jpg")
    t = time.time(); bpy.ops.render.render(write_still=True); print("FRAME", f, round(time.time() - t, 1), flush=True)
    paths.append(sc.render.filepath)
args = ["ffmpeg", "-v", "error", "-y"]
for p in paths: args += ["-i", p]
n = len(paths); cols = min(n, 6); rows = (n + cols - 1) // cols
args += ["-filter_complex", "".join(f"[{i}]scale=270:480,drawtext=text='{frames[i]}':x=8:y=8:fontsize=22:fontcolor=yellow[v{i}];" for i in range(n))
         + "".join(f"[v{i}]" for i in range(n)) + f"xstack=inputs={n}:layout=" + "|".join(f"{(i%cols)*270}_{(i//cols)*480}" for i in range(n))
         + ("" if n > 1 else ""), str(P / "checks" / "keys_eevee.jpg")]
if n == 1: args = ["ffmpeg", "-v", "error", "-y", "-i", paths[0], "-vf", "scale=270:480", str(P / "checks" / "keys_eevee.jpg")]
subprocess.run(args)
