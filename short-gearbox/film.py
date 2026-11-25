# Постановка «Виды коробок передач»: механизмы и машина из геометрии кодом (без людей и внешних ассетов).
#   python film.py <PROJECT>  (bpy как модуль)  или  blender -b --python film.py -- <PROJECT>
import bpy, bmesh, math, sys, json
from pathlib import Path
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
PROJECT = Path(argv[0] if argv else Path(__file__).parent).resolve()
sys.path.insert(0, str(PROJECT / "blender"))
from kit import core, cam
from kit.core import coll, keyset, fcurves

sc = core.reset(30)
SH, TOTAL, _ = core.shots_from_json(PROJECT)
sc.frame_start, sc.frame_end = 1, TOTAL
WORDS = json.loads((PROJECT / "audio" / "words.json").read_text(encoding="utf-8"))


def cue(word, after=0):
    """Кадр начала слова (первое вхождение после кадра after)."""
    for w in WORDS:
        f = round(w["s"] * 30) + 1
        if f >= after and w["t"].lower().startswith(word.lower()):
            return f
    raise KeyError(word)


CUES = []  # звуки для монтажа


def sfx(k, f, v=0.8):
    CUES.append({"k": k, "f": int(f), "v": v})


# ---------------------------------------------------------------- материалы
def mat(name, col=(0.5, 0.5, 0.5), metal=0.0, rough=0.5, emit=None, es=0.0, alpha=1.0, coat=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = coat
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = es
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    m.diffuse_color = (*col, 1) if not emit else (*emit, 1)
    m.metallic, m.roughness = metal, rough
    return m


def emis(name, col, s=5.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*col, 1)
    e.inputs[1].default_value = s
    nt.links.new(e.outputs[0], o.inputs[0])
    m.diffuse_color = (*col, 1)
    return m


def xray(name, col=(0.25, 0.65, 1.0), s=2.5, base=0.02):
    """Рентген-оболочка: светится по краям (френель), середина прозрачная."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs[0].default_value = 0.35
    pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 2.6
    ad = nt.nodes.new("ShaderNodeMath"); ad.operation = "ADD"; ad.inputs[1].default_value = base
    nt.links.new(lw.outputs["Facing"], pw.inputs[0]); nt.links.new(pw.outputs[0], ad.inputs[0])
    e = nt.nodes.new("ShaderNodeEmission"); e.inputs[0].default_value = (*col, 1); e.inputs[1].default_value = s
    t = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(ad.outputs[0], mx.inputs[0]); nt.links.new(t.outputs[0], mx.inputs[1]); nt.links.new(e.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], o.inputs[0])
    m.surface_render_method = "BLENDED"
    m.use_backface_culling = False
    m.diffuse_color = (*col, 0.25)
    return m


def key_emission(m, keys, socket="Emission Strength"):
    """Анимация силы свечения материала: keys = [(кадр, значение)]."""
    nt = m.node_tree
    node = nt.nodes.get("Principled BSDF") or next(n for n in nt.nodes if n.type == "EMISSION")
    inp = node.inputs[socket] if node.type == "BSDF_PRINCIPLED" else node.inputs[1]
    for f, v in keys:
        inp.default_value = v
        inp.keyframe_insert("default_value", frame=f)


def key_color(m, keys):
    nt = m.node_tree
    node = next(n for n in nt.nodes if n.type == "EMISSION")
    for f, c in keys:
        node.inputs[0].default_value = (*c, 1)
        node.inputs[0].keyframe_insert("default_value", frame=f)


def linear(ob):
    for fc in fcurves(ob):
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"


# ---------------------------------------------------------------- геометрия
def put(ob, c, m=None, loc=None, rot=None, parent=None):
    coll(c).objects.link(ob)
    if m:
        ob.data.materials.append(m)
    if loc is not None:
        ob.location = loc
    if rot is not None:
        ob.rotation_euler = rot
    if parent:
        ob.parent = parent
    return ob


def mesh_from(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return bpy.data.objects.new(name, me)


def box(name, size, loc, m, c, rot=(0, 0, 0), bevel=0.0, parent=None):
    sx, sy, sz = (s / 2 for s in size)
    v = [(x, y, z) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    ob = put(mesh_from(name, v, f), c, m, loc, rot, parent)
    if bevel:
        bv = ob.modifiers.new("Bevel", "BEVEL")
        bv.width, bv.segments = bevel, 3
        bv.limit_method = "ANGLE"
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def cyl(name, r, depth, loc, m, c, rot=(0, 0, 0), n=48, r2=None, bevel=0.0, parent=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=n, radius1=r, radius2=r if r2 is None else r2, depth=depth)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    ob = put(bpy.data.objects.new(name, me), c, m, loc, rot, parent)
    for p in me.polygons:
        p.use_smooth = len(p.vertices) == 4
    if bevel:
        bv = ob.modifiers.new("Bevel", "BEVEL")
        bv.width, bv.segments = bevel, 2
        bv.limit_method = "ANGLE"
    return ob


def sphere(name, r, loc, m, c, seg=24, parent=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return put(bpy.data.objects.new(name, me), c, m, loc, None, parent)


def torus(name, R, r, loc, m, c, rot=(0, 0, 0), parent=None, major=64, minor=16):
    v, f = [], []
    for i in range(major):
        a = 2 * math.pi * i / major
        for j in range(minor):
            b = 2 * math.pi * j / minor
            v.append(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b)))
    for i in range(major):
        for j in range(minor):
            a, b = i * minor + j, i * minor + (j + 1) % minor
            c2, d = ((i + 1) % major) * minor + (j + 1) % minor, ((i + 1) % major) * minor + j
            f.append((a, b, c2, d))
    ob = put(mesh_from(name, v, f), c, m, loc, rot, parent)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def gear(name, z, module, width, loc, m, c, rot=(0, 0, 0), hole=0.0, parent=None):
    """Прямозубая шестерня по оси Z (профиль трапецией, фаска модификатором)."""
    rp = module * z / 2
    ra, rf = rp + module, rp - 1.25 * module
    pts = []
    for i in range(z):
        a = 2 * math.pi * i / z
        p = 2 * math.pi / z
        for da, r in ((-0.5, rf), (-0.30, rf), (-0.16, ra), (0.16, ra), (0.30, rf)):
            pts.append((r, a + da * p))
    bm = bmesh.new()
    top = [bm.verts.new((r * math.cos(a), r * math.sin(a), width / 2)) for r, a in pts]
    bot = [bm.verts.new((r * math.cos(a), r * math.sin(a), -width / 2)) for r, a in pts]
    n = len(pts)
    bm.faces.new(top)
    bm.faces.new(list(reversed(bot)))
    for i in range(n):
        bm.faces.new((bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    ob = put(bpy.data.objects.new(name, me), c, m, loc, rot, parent)
    bv = ob.modifiers.new("Bevel", "BEVEL")
    bv.width, bv.segments, bv.limit_method = module * 0.12, 2, "ANGLE"
    ob.modifiers.new("WN", "WEIGHTED_NORMAL")
    return ob


def text(name, body, loc, size, m, c, rot=(math.pi / 2, 0, 0), extrude=0.02, align="CENTER", parent=None):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.bevel_depth = extrude * 0.3
    cu.align_x = align
    cu.align_y = "CENTER"
    return put(bpy.data.objects.new(name, cu), c, m, loc, rot, parent)


def light(name, kind, loc, energy, col=(1, 1, 1), size=1.0, rot=None, c="Lights", spot=None, target=None):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = col
    if kind == "AREA":
        ld.size = size
    elif kind in ("POINT", "SPOT"):
        ld.shadow_soft_size = size
    if spot:
        ld.spot_size = spot
        ld.spot_blend = 0.4
    ob = put(bpy.data.objects.new(name, ld), c, None, loc, rot)
    if target is not None:
        e = core.empty(name + ".T", target, 0.05)
        t = ob.constraints.new("TRACK_TO")
        t.target, t.track_axis, t.up_axis = e, "TRACK_NEGATIVE_Z", "UP_Y"
    return ob


def dome(name, center, top, bottom, r=45, strength=1.0):
    """Фон-сфера вокруг набора: вертикальный градиент, светится сама (у каждого «мира» свой фон)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs[1].default_value, mr.inputs[2].default_value = -0.2, 0.6
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*bottom, 1)
    ramp.color_ramp.elements[1].color = (*top, 1)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[1].default_value = strength
    nt.links.new(tc.outputs["Normal"], sep.inputs[0])
    nt.links.new(sep.outputs[2], mr.inputs[0])
    nt.links.new(mr.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], e.inputs[0])
    nt.links.new(e.outputs[0], o.inputs[0])
    m.use_backface_culling = False
    m.diffuse_color = (*bottom, 1)
    s = sphere(name, r, center, m, "Domes", seg=48)
    s.visible_shadow = False
    return s


def spin(ob, axis, f0, f1, turns, a0=0.0):
    """Равномерное вращение: turns оборотов между кадрами f0 и f1 (с экстраполяцией)."""
    ob.rotation_mode = "XYZ"
    i = "XYZ".index(axis)
    r = list(ob.rotation_euler)
    r[i] = a0
    ob.rotation_euler = r
    ob.keyframe_insert("rotation_euler", index=i, frame=f0)
    r[i] = a0 + 2 * math.pi * turns
    ob.rotation_euler = r
    ob.keyframe_insert("rotation_euler", index=i, frame=f1)
    for fc in fcurves(ob):
        if fc.data_path == "rotation_euler" and fc.array_index == i:
            for k in fc.keyframe_points:
                k.interpolation = "LINEAR"
            fc.extrapolation = "LINEAR"


def rot_keys(ob, axis, keys):
    """Вращение по ключам [(кадр, угол_рад)], сглаженное."""
    ob.rotation_mode = "XYZ"
    i = "XYZ".index(axis)
    for f, a in keys:
        r = list(ob.rotation_euler)
        r[i] = a
        ob.rotation_euler = r
        ob.keyframe_insert("rotation_euler", index=i, frame=f)


# ================================================================ МИР A: перекрёсток (шоты 1, 9)
A = Vector((0, 0, 0))
CA = "A_Street"
dome("Dome_A", A + Vector((0, 10, 0)), (0.006, 0.008, 0.03), (0.03, 0.02, 0.035), r=60)
asphalt = mat("Asphalt", (0.025, 0.026, 0.03), 0.0, 0.18, coat=0.6)
paint = mat("LinePaint", (0.75, 0.75, 0.72), 0.0, 0.4)
box("Road", (60, 60, 0.1), A + Vector((0, 8, -0.05)), asphalt, CA)
for i in range(7):  # пешеходный переход перед машиной
    box(f"Zebra{i}", (0.5, 3.0, 0.012), A + Vector((-3 + i * 1.0, 9.0, 0.006)), paint, CA)
for i in range(10):  # разметка
    box(f"Lane{i}", (0.14, 2.0, 0.01), A + Vector((1.8, -14 + i * 4.0, 0.005)), paint, CA)
    box(f"LaneB{i}", (0.14, 2.0, 0.01), A + Vector((1.8, 12 + i * 4.0, 0.005)), paint, CA)
box("StopLine", (3.6, 0.4, 0.012), A + Vector((0.9, 7.0, 0.006)), paint, CA)

# дома с окнами (кирпичная текстура = сетка окон)
def building(name, loc, size, hue):
    m = bpy.data.materials.new(name + "M")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*hue, 1)
    b.inputs["Roughness"].default_value = 0.8
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.35
    br.inputs["Color1"].default_value = (1.0, 0.62, 0.3, 1)
    br.inputs["Color2"].default_value = (0.0, 0.0, 0.0, 1)
    br.inputs["Mortar"].default_value = (0, 0, 0, 1)
    br.offset = 0.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.9, 0.9, 0.55)
    nt.links.new(tc.outputs["Object"], mp.inputs[0])
    nt.links.new(mp.outputs[0], br.inputs[0])
    noise = nt.nodes.new("ShaderNodeTexWhiteNoise")
    noise.noise_dimensions = "3D"
    nt.links.new(mp.outputs[0], noise.inputs[0])
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1
    nt.links.new(br.outputs["Color"], mul.inputs[1])
    nt.links.new(noise.outputs["Color"], mul.inputs[2])
    nt.links.new(mul.outputs[0], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 2.2
    m.diffuse_color = (*hue, 1)
    box(name, size, loc, m, CA)

blds = [((-9, 14, 7), (8, 8, 14)), ((-10, 2, 5), (6, 10, 10)), ((-9, -10, 9), (8, 9, 18)), ((10, 16, 8), (8, 8, 16)),
        ((10, 3, 6), (7, 9, 12)), ((11, -9, 10), (9, 9, 20)), ((-2, 28, 9), (12, 8, 18)), ((12, 28, 6), (8, 8, 12))]
for i, (l, s) in enumerate(blds):
    building(f"Bld{i}", A + Vector(l), s, (0.03 + 0.01 * (i % 3), 0.03, 0.04))

# светофор
pole_m = mat("PoleM", (0.05, 0.05, 0.055), 0.8, 0.35)
TL = A + Vector((3.9, 7.2, 0))
cyl("TLPole", 0.07, 4.2, TL + Vector((0, 0, 2.1)), pole_m, CA)
box("TLArm", (2.2, 0.1, 0.1), TL + Vector((-1.0, 0, 4.1)), pole_m, CA)
box("TLBox", (0.38, 0.32, 1.1), TL + Vector((-1.9, 0, 3.6)), mat("TLBoxM", (0.02, 0.02, 0.02), 0.2, 0.5), CA, bevel=0.03)
redM, ambM, grnM = emis("TLRed", (1.0, 0.04, 0.02), 0), emis("TLAmb", (1.0, 0.4, 0.0), 0), emis("TLGrn", (0.05, 1.0, 0.35), 0)
for k, (mm, dz) in enumerate(((redM, 0.33), (ambM, 0.0), (grnM, -0.33))):
    cyl(f"TLLamp{k}", 0.12, 0.04, TL + Vector((-1.9, -0.17, 3.6 + dz)), mm, CA, rot=(math.pi / 2, 0, 0))
key_emission(redM, [(1, 30), (SH[9][0] + 30, 30), (SH[9][0] + 36, 0)])
key_emission(grnM, [(1, 0), (SH[9][0] + 30, 0), (SH[9][0] + 36, 30)])
tl_red = light("TLRedGlow", "POINT", TL + Vector((-1.9, -0.6, 3.93)), 60, (1, 0.05, 0.02), 0.2)
tl_grn = light("TLGrnGlow", "POINT", TL + Vector((-1.9, -0.6, 3.27)), 0, (0.1, 1, 0.4), 0.2)
for ob, ks in ((tl_red, [(1, 60), (SH[9][0] + 30, 60), (SH[9][0] + 36, 0)]), (tl_grn, [(1, 0), (SH[9][0] + 30, 0), (SH[9][0] + 36, 60)])):
    for f, v in ks:
        ob.data.energy = v
        ob.data.keyframe_insert("energy", frame=f)

# фонари
for i, (x, y) in enumerate(((-3.2, -6), (-3.2, 10), (4.0, -14), (4.0, 18))):
    p = A + Vector((x, y, 0))
    cyl(f"Lamp{i}", 0.06, 5.5, p + Vector((0, 0, 2.75)), pole_m, CA)
    sphere(f"LampHead{i}", 0.22, p + Vector((0, 0, 5.5)), emis("LampGlow", (1.0, 0.7, 0.4), 18), CA)
    light(f"LampL{i}", "POINT", p + Vector((0, 0, 5.3)), 900, (1.0, 0.68, 0.38), 0.3)
light("MoonRim", "AREA", A + Vector((-6, 18, 9)), 1500, (0.45, 0.6, 1.0), 8, target=A + Vector((0, 0, 0.8)))
light("CityFill", "AREA", A + Vector((6, -10, 6)), 300, (0.6, 0.5, 0.9), 10, target=A + Vector((0, 0, 0.6)))

# машина (хэтчбек из примитивов)
def car(name, c, origin, body_m, glass_m, tire_m, rim_m, head_m=None, tail_m=None):
    root = core.empty(name + ".Root", origin, 0.3, c)
    bodyp = core.empty(name + ".Pitch", (0, 0, 0.0), 0.2, c)
    bodyp.parent = root
    L, W = 4.1, 1.78
    # нижний кузов
    b = box(name + ".Body", (W, L, 0.62), (0, 0, 0.66), body_m, c, bevel=0.12, parent=bodyp)
    sub = b.modifiers.new("Sub", "SUBSURF"); sub.levels = sub.render_levels = 1
    # кабина: трапеция
    v = [(-0.8, -1.25, 0.95), (0.8, -1.25, 0.95), (0.8, 1.05, 0.95), (-0.8, 1.05, 0.95),
         (-0.68, -0.85, 1.48), (0.68, -0.85, 1.48), (0.68, 0.55, 1.48), (-0.68, 0.55, 1.48)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    cab = put(mesh_from(name + ".Cabin", v, f), c, glass_m, None, None, bodyp)
    bv = cab.modifiers.new("Bevel", "BEVEL"); bv.width, bv.segments = 0.07, 3
    roof = box(name + ".Roof", (1.3, 1.36, 0.05), (0, -0.15, 1.5), body_m, c, bevel=0.02, parent=bodyp)
    for i, (x, y) in enumerate(((-0.82, 1.35), (0.82, 1.35), (-0.82, -1.3), (0.82, -1.3))):
        t = cyl(f"{name}.Tire{i}", 0.33, 0.24, (x, y, 0.33), tire_m, c, rot=(0, math.pi / 2, 0), bevel=0.05, parent=root)
        rr = cyl(f"{name}.Rim{i}", 0.2, 0.25, (0, 0, 0), rim_m, c, n=10, parent=t)
    if head_m:
        for s in (-1, 1):
            box(f"{name}.Head{s}", (0.42, 0.06, 0.13), (s * 0.6, 2.06, 0.78), head_m, c, bevel=0.02, parent=bodyp)
            box(f"{name}.Tail{s}", (0.36, 0.06, 0.12), (s * 0.63, -2.06, 0.8), tail_m, c, bevel=0.02, parent=bodyp)
    box(name + ".Grill", (0.7, 0.04, 0.16), (0, 2.06, 0.55), mat("GrillM", (0.01, 0.01, 0.01), 0.5, 0.4), c, parent=bodyp)
    return root, bodyp

body_red = mat("CarPaint", (0.55, 0.03, 0.02), 0.6, 0.22, coat=1.0)
glass = mat("CarGlass", (0.01, 0.012, 0.015), 0.0, 0.03, coat=1.0)
tire = mat("Tire", (0.015, 0.015, 0.015), 0.0, 0.7)
rim = mat("Rim", (0.7, 0.7, 0.72), 1.0, 0.25)
headM = mat("HeadM", (1, 1, 1), 0, 0.2, emit=(1.0, 0.92, 0.8), es=25)
tailM = mat("TailM", (0.6, 0.0, 0.0), 0, 0.3, emit=(1.0, 0.02, 0.01), es=6)
CAR, CARP = car("Car", CA, A + Vector((0.9, 1.2, 0)), body_red, glass, tire, rim, headM, tailM)
beams = []
for s in (-1, 1):
    bm_ = light(f"Beam{s}", "SPOT", (s * 0.6, 2.1, 0.78), 400, (1, 0.93, 0.82), 0.05, rot=(math.radians(-82), 0, 0), spot=math.radians(55))
    bm_.parent = CARP
    beams.append(bm_)

# Шот 1: рывок и «заглохла»
s1, e1 = SH[1]
JERK, STALL = cue("дёрнулась"), cue("заглохла")
keyset(CAR, "location", [(1, A + Vector((0.9, 1.2, 0))), (JERK - 4, A + Vector((0.9, 1.2, 0))), (JERK + 3, A + Vector((0.9, 1.75, 0))),
                         (JERK + 9, A + Vector((0.9, 1.62, 0))), (STALL, A + Vector((0.9, 1.66, 0)))])
rot_keys(CARP, "X", [(JERK - 4, 0.0), (JERK + 2, math.radians(-3.2)), (JERK + 7, math.radians(2.0)), (JERK + 12, math.radians(-1.2)),
                     (JERK + 17, math.radians(0.5)), (STALL + 2, 0.0), (STALL + 6, math.radians(-0.8)), (STALL + 12, 0.0)])
# мелкая вибрация работающего мотора до заглохания
CARP.location = (0, 0, 0)
CARP.keyframe_insert("location", index=2, frame=1)
for fc in fcurves(CARP):
    if fc.data_path == "location" and fc.array_index == 2:
        nz = fc.modifiers.new("NOISE"); nz.scale, nz.strength = 1.5, 0.012
        nz.use_restricted_range, nz.frame_start, nz.frame_end, nz.blend_out = True, 1, STALL + 4, 3
        nz2 = fc.modifiers.new("NOISE"); nz2.scale, nz2.strength = 1.5, 0.012
        nz2.use_restricted_range, nz2.frame_start, nz2.frame_end, nz2.blend_in = True, SH[9][0] + 20, TOTAL + 10, 3
# фары гаснут при заглохании, мигают при новом пуске в шоте 9
R9 = SH[9][0] + 18
key_emission(headM, [(1, 25), (STALL, 25), (STALL + 3, 3), (STALL + 5, 12), (STALL + 7, 1.5), (R9, 1.5), (R9 + 2, 25), (R9 + 4, 6), (R9 + 6, 25)])
for bm_ in beams:
    for f, v in ((1, 400), (STALL, 400), (STALL + 3, 40), (STALL + 5, 200), (STALL + 7, 20), (R9, 20), (R9 + 2, 400), (R9 + 4, 100), (R9 + 6, 400)):
        bm_.data.energy = v
        bm_.data.keyframe_insert("energy", frame=f)
sfx("sfx_jerk", JERK, 0.9)
sfx("sfx_hit", STALL, 0.8)
sfx("sfx_horn", STALL + 22, 0.45)

# дождь: облако штрихов, циклично падает
def rain(name, center, size, n=1800, H=10.0):
    import random
    random.seed(4)
    v, f = [], []
    for k in range(n):
        x = center[0] + (random.random() - 0.5) * size[0]
        y = center[1] + (random.random() - 0.5) * size[1]
        z = random.random() * 2 * H
        l = 0.25 + random.random() * 0.2
        i = len(v)
        v += [(x - 0.004, y, z), (x + 0.004, y, z), (x + 0.004, y, z + l), (x - 0.004, y, z + l)]
        f.append((i, i + 1, i + 2, i + 3))
    ob = put(mesh_from(name, v, f), CA, emis("RainM", (0.6, 0.7, 0.9), 0.9))
    ob.visible_shadow = False
    keyset(ob, "location", [(1, (0, 0, 0)), (16, (0, 0, -H))], "LINEAR")
    for fc in fcurves(ob):
        fc.modifiers.new("CYCLES")
    return ob

rain("Rain", (0.5, 3.0), (12, 16), n=2400, H=8.0)

# камера шота 1: низко у переднего колеса → резкий наезд на фару при «заглохла»
HEAD_W = A + Vector((0.9 + 0.6, 1.66 + 2.06, 0.78))
cam1 = cam.shot_camera("Cam1", [
    (s1, A + Vector((2.9, 6.4, 0.3)), A + Vector((1.0, 2.4, 0.6)), 24),
    (JERK, A + Vector((2.7, 6.0, 0.36)), A + Vector((1.0, 2.7, 0.62)), 24),
    (STALL - 2, A + Vector((2.6, 5.8, 0.4)), A + Vector((1.05, 2.9, 0.66)), 26),
    (STALL + 6, A + Vector((2.0, 4.7, 0.72)), HEAD_W, 42),
    (e1 + 1, A + Vector((1.95, 4.6, 0.74)), HEAD_W, 46)], focus=[(s1, A + Vector((1.3, 3.4, 0.6))), (STALL + 6, HEAD_W)], fstop=2.0, handheld=0.6)

# камера шота 9: кран вверх над перекрёстком, машина трогается на зелёный
s9, e9 = SH[9]
GO = R9 + 16
keyset(CAR, "location", [(s9, A + Vector((0.9, 1.66, 0))), (GO, A + Vector((0.9, 1.66, 0))), (e9 + 1, A + Vector((0.9, 7.5, 0)))])
cam9 = cam.shot_camera("Cam9", [
    (s9, A + Vector((-2.4, -2.6, 1.0)), A + Vector((0.9, 2.0, 0.8)), 30),
    (s9 + 40, A + Vector((-3.4, -4.0, 3.2)), A + Vector((0.9, 3.0, 0.7)), 28),
    (e9 + 1, A + Vector((-4.5, -6.5, 8.5)), A + Vector((0.9, 5.5, 0.3)), 26)], focus="Car.Root", fstop=4.0, handheld=0.3)
sfx("sfx_click", R9, 0.6)
sfx("sfx_engine", R9 + 2, 0.6)

# ================================================================ МИР B: рентген машины (шот 2)
B = Vector((120, 0, 0))
CB = "B_Xray"
dome("Dome_B", B, (0.01, 0.03, 0.09), (0.0, 0.004, 0.015), r=40)
xs = xray("XrayShell", (0.25, 0.6, 1.0), 0.45, 0.0)
xr, xp = car("XCar", CB, B, xs, xs, xs, xray("XrayRim", (0.3, 0.7, 1.0), 1.2, 0.0))
eng_m = mat("Engine", (0.25, 0.3, 0.35), 0.9, 0.3, emit=(1.0, 0.35, 0.08), es=0.0)
hot = emis("HotOrange", (1.0, 0.35, 0.05), 6)
cold_m = emis("ColdBlue", (0.2, 0.55, 1.0), 4)
eng = box("XEngine", (0.75, 0.55, 0.5), B + Vector((0, 1.35, 0.72)), eng_m, CB, bevel=0.04)
pistons = []
for i in range(4):
    p = cyl(f"XPiston{i}", 0.07, 0.12, B + Vector((-0.27 + i * 0.18, 1.35, 1.02)), hot, CB)
    pistons.append(p)
crank = cyl("XCrankPulley", 0.16, 0.06, B + Vector((0.42, 1.35, 0.6)), mat("Pulley", (0.6, 0.6, 0.6), 1, 0.3), CB, rot=(0, math.pi / 2, 0), n=8)
shaft = cyl("XShaft", 0.035, 2.4, B + Vector((0, 0.05, 0.38)), cold_m, CB, rot=(math.pi / 2, 0, 0))
gb = box("XGearboxGap", (0.36, 0.42, 0.34), B + Vector((0, 0.85, 0.55)), xray("XrayGap", (1.0, 0.25, 0.15), 4.0, 0.08), CB, bevel=0.04)
qm = text("XQuestion", "?", B + Vector((0, 0.85, 1.05)), 0.45, emis("QM", (1.0, 0.3, 0.15), 8), CB, rot=(math.pi / 2, 0, math.pi / 2 + 0.4))
s2, e2 = SH[2]
# поршни дёргаются, шкив вертится, колёса стоят
for i, p in enumerate(pistons):
    z0 = p.location.z
    for f in range(s2 - 5, e2 + 6, 3):
        p.location.z = z0 + 0.05 * math.sin(f * 1.4 + i * math.pi / 2)
        p.keyframe_insert("location", index=2, frame=f)
spin(crank, "X", s2, e2, 6)
key_emission(eng_m, [(s2, 0.0), (cue("мотор") , 4.0), (cue("малых"), 1.0), (cue("оборотах"), 4.0), (cue("коробки"), 0.8)])
# стрелка тахометра у нуля дрожит
gauge = torus("XGauge", 0.32, 0.012, B + Vector((-0.9, 0.2, 1.75)), cold_m, CB, rot=(math.pi / 2, 0, 0))
needle = box("XNeedle", (0.02, 0.01, 0.28), (0, 0, 0.12), hot, CB)
npiv = core.empty("XNeedlePivot", B + Vector((-0.9, 0.18, 1.75)), 0.05, CB)
needle.parent = npiv
for k, f in enumerate(range(s2, e2 + 4, 4)):
    npiv.rotation_euler = (0, math.radians(70 + (6 if k % 2 else -4) + (k % 3) * 2), 0)
    npiv.keyframe_insert("rotation_euler", index=1, frame=f)
for i in range(1, 9):
    a = math.radians(70 - i * 17.5)
    box(f"XTick{i}", (0.012, 0.01, 0.05), B + Vector((-0.9 + 0.27 * math.sin(a), 0.2, 1.75 + 0.27 * math.cos(a))), cold_m, CB, rot=(0, a, 0))
key_emission(bpy.data.materials["QM"], [(s2, 0), (cue("коробки") - 2, 0), (cue("коробки") + 4, 12)])
light("XKey", "AREA", B + Vector((-3, -2, 4)), 200, (0.4, 0.6, 1.0), 4, target=B + Vector((0, 0.5, 0.6)))
cam2 = cam.shot_camera("Cam2", [
    (s2, B + Vector((2.6, 3.6, 1.6)), B + Vector((0, 1.4, 0.75)), 32),
    ((s2 + e2) // 2, B + Vector((3.0, 0.6, 1.2)), B + Vector((0, 0.7, 0.6)), 30),
    (e2 + 1, B + Vector((2.4, -2.2, 0.9)), B + Vector((0, -0.6, 0.45)), 32)], focus=None, handheld=0.35)
sfx("sfx_whoosh", s2 - 4, 0.6)
sfx("sfx_hum", s2, 0.5)

# ================================================================ МИР C: механика, пара шестерён (шот 3)
C = Vector((240, 0, 0))
CC = "C_Manual"
dome("Dome_C", C, (0.05, 0.035, 0.02), (0.005, 0.004, 0.004), r=30)
steel = mat("Steel", (0.42, 0.43, 0.46), 1.0, 0.3)
brass = mat("Brass", (0.85, 0.55, 0.22), 1.0, 0.25)
s3, e3 = SH[3]
MOD = 0.06
z1, z2 = 11, 33
small = gear("GearSmall", z1, MOD, 0.22, C + Vector((0, 0, 1.0)), brass, CC, rot=(math.pi / 2, 0, 0))
big_x = MOD * (z1 + z2) / 2
big = gear("GearBig", z2, MOD, 0.22, C + Vector((big_x, 0, 1.0)), steel, CC, rot=(math.pi / 2, 0, 0))
cyl("ShaftSmall", 0.06, 1.2, C + Vector((0, 0.2, 1.0)), steel, CC, rot=(math.pi / 2, 0, 0))
cyl("ShaftBig", 0.09, 1.2, C + Vector((big_x, 0.2, 1.0)), steel, CC, rot=(math.pi / 2, 0, 0))
# вращение: маленькая быстро, большая в 3 раза медленнее, в обратную сторону
small.rotation_mode = big.rotation_mode = "XYZ"
for ob, turns, a0 in ((small, 3.0, 0.0), (big, -1.0, math.pi / z2)):
    ob.rotation_euler = (math.pi / 2, 0, 0)
    spin(ob, "Y", s3 - 10, e3 + 10, turns, a0)
# стрелка «сила растёт»: дуга вокруг большой шестерни
GROW = cue("сила")
arc_m = emis("TorqueArc", (1.0, 0.45, 0.08), 0)
arc = torus("TorqueArc", 1.32, 0.03, C + Vector((big_x, -0.16, 1.0)), arc_m, CC, rot=(math.pi / 2, 0, 0))
key_emission(arc_m, [(s3, 0), (GROW - 2, 0), (GROW + 4, 8), (e3, 4)])
head = cyl("TorqueHead", 0.12, 0.25, C + Vector((big_x - 1.32, -0.16, 1.0)), arc_m, CC, n=24, r2=0.0)
keyset(arc, "scale", [(GROW - 2, (0.9, 0.9, 0.9)), (GROW + 6, (1.04, 1.04, 1.04)), (e3, (1.0, 1.0, 1.0))])
light("CKey", "AREA", C + Vector((-2.5, -3, 3.5)), 500, (1.0, 0.82, 0.62), 3, target=C + Vector((0.6, 0, 1.0)))
light("CRim", "AREA", C + Vector((3, 3, 2.5)), 700, (0.4, 0.6, 1.0), 3, target=C + Vector((0.6, 0, 1.0)))
light("CFill", "AREA", C + Vector((1, -4, 0.2)), 80, (1, 1, 1), 4, target=C + Vector((0.6, 0, 1.0)))
mid = C + Vector((big_x * 0.35, 0, 1.0))
cam3 = cam.shot_camera("Cam3", cam.move("orbit", s3, e3 + 1, mid, dist=4.2, height=0.5, lens=42, extra={"from": -55, "to": 15}),
                       focus=[(s3, C + Vector((0, 0, 1.0))), (GROW, C + Vector((big_x * 0.6, -0.1, 1.0)))], fstop=2.8, handheld=0.3)
sfx("sfx_gears", s3, 0.55)
sfx("sfx_shift", s3 + 6, 0.8)
sfx("sfx_hit", GROW, 0.6)

# ================================================================ МИР D: гидротрансформатор (шот 4a) + вентиляторы (4b)
D = Vector((360, 0, 0))
CD = "D_Converter"
dome("Dome_D", D, (0.0, 0.03, 0.05), (0.0, 0.005, 0.01), r=30)
s4, e4 = SH[4]
FANS = cue("как", s4) - 3
housing_m = mat("Housing", (0.22, 0.23, 0.25), 1.0, 0.35)
# корпус-«бублик» в разрезе: половина тора
def half_torus(name, R, r, loc, m, c, rot):
    ob = torus(name, R, r, loc, m, c, rot)
    bis = ob.modifiers.new("Cut", "BOOLEAN")
    cutter = box(name + ".Cutter", (5, 5, 5), loc + Vector((0, -2.5, 0)), None, c)
    cutter.hide_render = True
    cutter.hide_viewport = True
    bis.object = cutter
    bis.operation = "DIFFERENCE"
    sol = ob.modifiers.new("Solid", "SOLIDIFY"); sol.thickness = 0.02
    return ob

half_torus("ConvHousing", 0.75, 0.38, D + Vector((0, 0, 1.2)), housing_m, CD, rot=(0, math.pi / 2, 0))
pump = core.empty("Pump", D + Vector((-0.2, 0, 1.2)), 0.2, CD)
turb = core.empty("Turbine", D + Vector((0.2, 0, 1.2)), 0.2, CD)
blade_a = mat("BladeA", (0.9, 0.5, 0.15), 1.0, 0.3)
blade_b = mat("BladeB", (0.3, 0.6, 0.9), 1.0, 0.3)
for wheel, m_, sgn in ((pump, blade_a, -1), (turb, blade_b, 1)):
    cyl(wheel.name + ".Disc", 0.32, 0.05, (sgn * 0.12, 0, 0), m_, CD, rot=(0, math.pi / 2, 0), parent=wheel)
    for k in range(16):
        a = 2 * math.pi * k / 16
        bl = box(f"{wheel.name}.Blade{k}", (0.18, 0.02, 0.5), (0, 0.72 * math.cos(a), 0.72 * math.sin(a)), m_, CD,
                 rot=(a, math.radians(25 * sgn), 0), parent=wheel)
spin(pump, "X", s4 - 10, e4, 7)
rot_keys(turb, "X", [(s4 - 10, 0), (s4 + 20, 0.3), (s4 + 60, 3.5), (FANS, 14), (e4, 26)])
# поток масла: светящиеся капли по тору
oil_m = emis("Oil", (0.15, 0.7, 1.0), 10)
oil = core.empty("OilFlow", D + Vector((0, 0, 1.2)), 0.2, CD)
import random
random.seed(7)
for k in range(140):
    a = random.random() * 2 * math.pi
    b = random.random() * 2 * math.pi
    R, r = 0.75, 0.25 * random.random() + 0.05
    p = Vector(((r * math.sin(b)), (R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a)))
    sphere(f"OilDrop{k}", 0.025, p, oil_m, CD, seg=8, parent=oil)
spin(oil, "X", s4 - 10, e4, 4)
light("DKey", "AREA", D + Vector((-2, -3, 3)), 400, (1, 0.85, 0.7), 3, target=D + Vector((0, 0, 1.2)))
light("DRim", "AREA", D + Vector((2, 3, 2)), 500, (0.3, 0.7, 1.0), 3, target=D + Vector((0, 0, 1.2)))
cam4 = cam.shot_camera("Cam4", [
    (s4, D + Vector((1.4, -3.4, 1.9)), D + Vector((0, 0, 1.2)), 35),
    (FANS - 7, D + Vector((0.7, -2.1, 1.45)), D + Vector((0, 0, 1.2)), 42),
    (FANS, D + Vector((0.7, -2.0, 1.45)), D + Vector((1.8, 0, 1.3)), 42)], focus=[(s4, D + Vector((0, -0.6, 1.2)))], fstop=2.8, handheld=0.4)
sfx("sfx_fluid", s4, 0.45)
sfx("sfx_whoosh", FANS - 4, 0.7)

# вентиляторы
F = Vector((360, 60, 0))
CF = "D_Fans"
dome("Dome_F", F, (0.08, 0.07, 0.06), (0.02, 0.018, 0.016), r=20)
fan_body = mat("FanBody", (0.85, 0.85, 0.82), 0.0, 0.4)
fan_bl = mat("FanBlade", (0.2, 0.55, 0.95), 0.0, 0.35)
box("Table", (4.0, 1.6, 0.06), F + Vector((0, 0, 0.75)), mat("Wood", (0.25, 0.13, 0.06), 0, 0.5), CF)
fans = []
for s in (-1, 1):
    base = F + Vector((s * 0.5, 0, 0.78))
    cyl(f"FanBase{s}", 0.18, 0.05, base + Vector((0, 0, 0.025)), fan_body, CF)
    cyl(f"FanStem{s}", 0.025, 0.4, base + Vector((0, 0, 0.22)), fan_body, CF)
    hub = core.empty(f"FanHub{s}", base + Vector((0, 0, 0.5)), 0.1, CF)
    hub.rotation_euler = (0, 0, 0)
    torus(f"FanGuard{s}", 0.27, 0.008, base + Vector((0, 0, 0.5)), fan_body, CF, rot=(0, math.pi / 2, 0))
    cyl(f"FanMotor{s}", 0.08, 0.14, base + Vector((-s * 0.09, 0, 0.5)), fan_body, CF, rot=(0, math.pi / 2, 0))
    rotor = core.empty(f"FanRotor{s}", base + Vector((0, 0, 0.5)), 0.1, CF)
    for k in range(3):
        a = 2 * math.pi * k / 3
        box(f"FanBlade{s}.{k}", (0.012, 0.09, 0.23), (0, 0.13 * math.cos(a + math.pi / 2) * 0, 0), fan_bl, CF, parent=rotor)
        bl = bpy.data.objects[f"FanBlade{s}.{k}"]
        bl.location = (0, -0.13 * math.sin(a), 0.13 * math.cos(a))
        bl.rotation_euler = (a, math.radians(25), 0)
    cyl(f"FanCap{s}", 0.045, 0.05, (0, 0, 0), fan_body, CF, rot=(0, math.pi / 2, 0), parent=rotor)
    fans.append(rotor)
spin(fans[0], "X", FANS - 20, e4 + 10, 9)
rot_keys(fans[1], "X", [(FANS, 0), (FANS + 6, 0.1), (FANS + 20, 1.6), (e4 + 10, 12)])
# воздушные струи между вентиляторами
air_m = emis("Air", (0.75, 0.85, 1.0), 1.2)
for k in range(10):
    z = F.z + 1.28 + (k % 5 - 2) * 0.08
    y = F.y + (k // 5 - 0.5) * 0.18
    st = box(f"Air{k}", (0.22, 0.006, 0.006), (F.x - 0.55, y, z), air_m, CF)
    st.visible_shadow = False
    keyset(st, "location", [(FANS + 2 * k, Vector((F.x - 0.4, y, z))), (FANS + 2 * k + 12, Vector((F.x + 0.4, y, z)))], "LINEAR")
    for fc in fcurves(st):
        fc.modifiers.new("CYCLES")
light("FKey", "AREA", F + Vector((-1.5, -2.5, 2.5)), 250, (1, 0.9, 0.8), 2.5, target=F + Vector((0, 0, 1.2)))
light("FRim", "AREA", F + Vector((1.5, 2.5, 2.0)), 200, (0.6, 0.75, 1.0), 2.5, target=F + Vector((0, 0, 1.2)))
cam4b = cam.shot_camera("Cam4b", [
    (FANS, F + Vector((-1.25, -0.95, 1.5)), F + Vector((-0.15, 0, 1.2)), 30),
    (e4 + 1, F + Vector((-0.6, -1.25, 1.45)), F + Vector((0.2, 0, 1.2)), 32)], focus=[(FANS, F + Vector((-0.5, 0, 1.28))), (FANS + 30, F + Vector((0.5, 0, 1.28)))], fstop=2.2, handheld=0.45)

# ================================================================ МИР E: вариатор (шот 5)
E = Vector((480, 0, 0))
CE = "E_CVT"
dome("Dome_E", E, (0.02, 0.04, 0.06), (0.003, 0.004, 0.006), r=30)
s5, e5 = SH[5]
DIST = 1.6
P1, P2 = E + Vector((0, 0, 1.2)), E + Vector((DIST, 0, 1.2))
cone_m = mat("ConeSteel", (0.6, 0.61, 0.64), 1.0, 0.32)
cones = {}
for nm, P in (("Drive", P1), ("Driven", P2)):
    for s in (-1, 1):
        cn = cyl(f"{nm}Cone{s}", 0.6, 0.22, P + Vector((0, s * 0.13, 0)), cone_m, CE, rot=(math.radians(-90 * s), 0, 0), n=64, r2=0.12)
        cones[(nm, s)] = cn
    cyl(f"{nm}Shaft", 0.06, 1.4, P, cone_m, CE, rot=(math.pi / 2, 0, 0))

def belt_pts(r1, r2, n=160):
    """Точки ремня вокруг двух окружностей (центры 0 и DIST по X), по длине равномерно."""
    d = DIST
    beta = math.asin((r1 - r2) / d)
    segs = []
    a0, a1 = math.pi / 2 + beta, 3 * math.pi / 2 - beta
    segs.append(("arc", (0, 0), r1, a0, a1))
    p_a = (r1 * math.cos(a1), r1 * math.sin(a1))
    b0 = -math.pi / 2 - beta
    p_b = (d + r2 * math.cos(b0), r2 * math.sin(b0))
    segs.append(("line", p_a, p_b))
    b1 = math.pi / 2 + beta
    segs.append(("arc", (d, 0), r2, b0, b1))
    segs.append(("line", (d + r2 * math.cos(b1), r2 * math.sin(b1)), (r1 * math.cos(a0), r1 * math.sin(a0))))
    lens = []
    for s in segs:
        lens.append(abs(s[4] - s[3]) * s[2] if s[0] == "arc" else math.dist(s[1], s[2]))
    Lt = sum(lens)
    pts = []
    for i in range(n):
        t = Lt * i / n
        for s, l in zip(segs, lens):
            if t <= l:
                if s[0] == "arc":
                    a = s[3] + (s[4] - s[3]) * t / l
                    pts.append((s[1][0] + s[2] * math.cos(a), s[1][1] + s[2] * math.sin(a)))
                else:
                    u = t / l
                    pts.append((s[1][0] + (s[2][0] - s[1][0]) * u, s[1][1] + (s[2][1] - s[1][1]) * u))
                break
            t -= l
    return pts

N = 160
pa, pb = belt_pts(0.22, 0.5, N), belt_pts(0.5, 0.22, N)
HW = 0.05
def ring_verts(pts):
    v = []
    for x, z in pts:
        v += [(x, -HW, z), (x, HW, z)]
    return v
faces = [(2 * i, 2 * ((i + 1) % N), 2 * ((i + 1) % N) + 1, 2 * i + 1) for i in range(N)]
belt = put(mesh_from("Belt", ring_verts(pa), faces), CE, None, P1)
uv = belt.data.uv_layers.new()
for poly in belt.data.polygons:
    for li in poly.loop_indices:
        vi = belt.data.loops[li].vertex_index
        i = vi // 2
        uv.data[li].uv = ((i if not (poly.index == N - 1 and i == 0) else N) / N, vi % 2)
belt.shape_key_add(name="Basis")
kb = belt.shape_key_add(name="Shift")
for i, co in enumerate(ring_verts(pb)):
    kb.data[i].co = co
sol = belt.modifiers.new("Solid", "SOLIDIFY"); sol.thickness = 0.03; sol.offset = 1
# сегменты толкающего ремня — полосатая текстура, бегущая по длине
bm_mat = bpy.data.materials.new("BeltM"); bm_mat.use_nodes = True
nt = bm_mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Metallic"].default_value = 1.0; bsdf.inputs["Roughness"].default_value = 0.25
tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
wave = nt.nodes.new("ShaderNodeTexWave"); wave.wave_profile = "SAW"
wave.inputs["Scale"].default_value = 60; wave.inputs["Distortion"].default_value = 0
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].position = 0.7; ramp.color_ramp.elements[0].color = (0.75, 0.76, 0.8, 1)
ramp.color_ramp.elements[1].position = 0.75; ramp.color_ramp.elements[1].color = (0.12, 0.12, 0.13, 1)
nt.links.new(tc.outputs["UV"], mp.inputs[0]); nt.links.new(mp.outputs[0], wave.inputs[0])
nt.links.new(wave.outputs["Fac"], ramp.inputs[0]); nt.links.new(ramp.outputs[0], bsdf.inputs["Base Color"])
wave.bands_direction = "X"
loc_in = mp.inputs["Location"]
for f, x in ((s5 - 10, 0.0), (e5 + 10, -1.2)):
    loc_in.default_value = (x, 0, 0)
    loc_in.keyframe_insert("default_value", frame=f)
for fc in fcurves(bm_mat.node_tree):
    for k in fc.keyframe_points:
        k.interpolation = "LINEAR"
belt.data.materials.append(bm_mat)
SHIFT0, SHIFT1 = cue("ремень"), cue("плавно") + 10
kb.value = 0
kb.keyframe_insert("value", frame=SHIFT0)
kb.value = 1
kb.keyframe_insert("value", frame=SHIFT1)
# конусы: на ведущем сходятся (ремень выше), на ведомом расходятся
for (nm, s), cn in cones.items():
    y0 = 0.13 if nm == "Drive" else 0.06
    y1 = 0.06 if nm == "Drive" else 0.13
    P = P1 if nm == "Drive" else P2
    keyset(cn, "location", [(SHIFT0, P + Vector((0, s * y0, 0))), (SHIFT1, P + Vector((0, s * y1, 0)))])
    cn.rotation_mode = "XYZ"
for (nm, s), cn in cones.items():
    spin(cn, "Y", s5 - 10, e5 + 10, (5 if nm == "Drive" else 2.2) * s, 0)
    cn.rotation_euler[0] = math.radians(-90 * s)
    cn.keyframe_insert("rotation_euler", index=0, frame=1)
light("EKey", "AREA", E + Vector((-2, -3, 3.5)), 300, (1, 0.9, 0.8), 3, target=P1.lerp(P2, 0.5))
light("ERim", "AREA", E + Vector((3, 3, 2.5)), 300, (0.3, 0.6, 1.0), 3, target=P1.lerp(P2, 0.5))
light("EUnder", "AREA", E + Vector((0.8, -2, 0.0)), 60, (1, 1, 1), 3, target=P1.lerp(P2, 0.5))
cam5 = cam.shot_camera("Cam5", [
    (s5, E + Vector((-0.7, -2.0, 1.55)), P1 + Vector((0, 0, 0.1)), 50),
    (SHIFT0, E + Vector((-0.2, -2.3, 1.7)), P1.lerp(P2, 0.35), 45),
    (e5 + 1, E + Vector((2.6, -2.2, 1.85)), P2 + Vector((-0.2, 0, 0)), 40)],
    focus=[(s5, P1 + Vector((0, -0.2, 0))), (SHIFT0 + 20, P2 + Vector((0, -0.2, 0)))], fstop=2.4, handheld=0.3)
sfx("sfx_whir", s5, 0.5)

# ================================================================ МИР F: робот — педаль сама уходит вниз (шот 6)
G = Vector((600, 0, 0))
CG = "F_Robot"
dome("Dome_G", G, (0.015, 0.02, 0.03), (0.002, 0.002, 0.004), r=25)
s6, e6 = SH[6]
PRESS = cue("выжимает")
floor_m = mat("CarFloor", (0.03, 0.03, 0.03), 0.0, 0.9)
box("Floor", (3, 3, 0.05), G + Vector((0, 0, 0)), floor_m, CG)
box("Firewall", (3, 0.05, 1.6), G + Vector((0, 0.9, 0.8)), floor_m, CG)
pedal_piv = core.empty("PedalPivot", G + Vector((-0.25, 0.8, 1.0)), 0.05, CG)
arm_m = mat("PedalArm", (0.1, 0.1, 0.1), 0.8, 0.4)
box("PedalArm", (0.04, 0.04, 0.6), (0, -0.08, -0.3), arm_m, CG, rot=(math.radians(-15), 0, 0), parent=pedal_piv)
box("PedalPad", (0.26, 0.05, 0.2), (0, -0.16, -0.6), mat("PadRubber", (0.15, 0.15, 0.15), 0.0, 0.6, emit=(1.0, 0.4, 0.1), es=0.6), CG, bevel=0.01, parent=pedal_piv)
box("GasPedal", (0.1, 0.03, 0.2), G + Vector((0.25, 0.65, 0.4)), arm_m, CG, rot=(math.radians(20), 0, 0))
box("BrakePedal", (0.16, 0.03, 0.12), G + Vector((0.02, 0.64, 0.42)), arm_m, CG, bevel=0.01)
# актуатор: блок с чипом и штоком
act = box("Actuator", (0.3, 0.2, 0.18), G + Vector((-0.25, 0.75, 1.35)), mat("ActBody", (0.15, 0.17, 0.2), 0.7, 0.35), CG, bevel=0.02)
chip_m = emis("ChipGlow", (0.1, 1.0, 0.5), 0)
box("Chip", (0.12, 0.01, 0.08), G + Vector((-0.25, 0.645, 1.36)), chip_m, CG)
for k in range(4):
    box(f"Trace{k}", (0.004, 0.012, 0.06), G + Vector((-0.32 + k * 0.045, 0.645, 1.42)), chip_m, CG)
rod = cyl("ActRod", 0.012, 0.3, G + Vector((-0.25, 0.73, 1.15)), rim, CG)
rot_keys(pedal_piv, "X", [(s6, 0), (PRESS - 4, 0), (PRESS + 6, math.radians(17)), (e6, math.radians(18))])
keyset(rod, "location", [(PRESS - 4, G + Vector((-0.25, 0.73, 1.15))), (PRESS + 6, G + Vector((-0.25, 0.68, 1.05)))])
key_emission(chip_m, [(s6, 0), (cue("компьютер") - 6, 0), (cue("компьютер") - 3, 15), (cue("компьютер"), 2), (cue("компьютер") + 3, 15), (PRESS - 6, 0), (PRESS - 3, 15)])
light("GKey", "SPOT", G + Vector((-1.2, -1.2, 2.0)), 300, (1, 0.9, 0.8), 0.1, spot=math.radians(40), target=G + Vector((-0.2, 0.7, 0.7)))
light("GPad", "SPOT", G + Vector((0.4, -0.6, 0.9)), 120, (1, 0.8, 0.6), 0.05, spot=math.radians(35), target=G + Vector((-0.25, 0.6, 0.5)))
light("GRim", "AREA", G + Vector((1.0, 0.2, 1.8)), 80, (0.3, 0.6, 1.0), 1.5, target=G + Vector((-0.2, 0.7, 0.8)))
light("GChip", "POINT", G + Vector((-0.25, 0.55, 1.36)), 0, (0.1, 1, 0.5), 0.05)
PAD = G + Vector((-0.25, 0.62, 0.45))
LOOK6 = G + Vector((-0.22, 0.62, 0.78))
cam6 = cam.shot_camera("Cam6", [(s6, G + Vector((0.55, -1.0, 0.6)), LOOK6, 50), (e6 + 1, G + Vector((0.3, -0.45, 0.62)), LOOK6, 26)],
                       focus="PedalPad", fstop=2.0, handheld=0.5)
sfx("sfx_beep", cue("компьютер") - 3, 0.5)
sfx("sfx_click", PRESS + 5, 0.8)

# ================================================================ МИР H: две муфты (шот 7)
H = Vector((720, 0, 0))
CH = "G_DSG"
dome("Dome_H", H, (0.04, 0.02, 0.06), (0.004, 0.002, 0.008), r=30)
s7, e7 = SH[7]
CLICK = cue("щелчок")
shaft_out = cyl("OuterShaft", 0.09, 2.6, H + Vector((0, 0, 1.4)), steel, CH, rot=(0, math.pi / 2, 0))
shaft_in = cyl("InnerShaft", 0.05, 3.6, H + Vector((0.3, 0, 1.4)), brass, CH, rot=(0, math.pi / 2, 0))
cl3_m = emis("Clutch3", (1.0, 0.45, 0.08), 12)
cl4_m = emis("Clutch4", (0.2, 0.7, 1.0), 2)
c3 = torus("ClutchOdd", 0.55, 0.05, H + Vector((-1.5, 0, 1.4)), cl3_m, CH, rot=(0, math.pi / 2, 0))
c4 = torus("ClutchEven", 0.4, 0.05, H + Vector((-1.38, 0, 1.4)), cl4_m, CH, rot=(0, math.pi / 2, 0))
cyl("ClutchDiscOdd", 0.52, 0.03, H + Vector((-1.5, 0, 1.4)), steel, CH, rot=(0, math.pi / 2, 0))
cyl("ClutchDiscEven", 0.37, 0.03, H + Vector((-1.38, 0, 1.4)), brass, CH, rot=(0, math.pi / 2, 0))
g3 = gear("Gear3", 22, 0.04, 0.16, H + Vector((-0.3, 0, 1.4)), steel, CH, rot=(0, math.pi / 2, 0))
g4 = gear("Gear4", 26, 0.04, 0.16, H + Vector((0.6, 0, 1.4)), brass, CH, rot=(0, math.pi / 2, 0))
n3m, n4m = emis("Num3", (1.0, 0.45, 0.08), 14), emis("Num4", (0.2, 0.7, 1.0), 3)
t3 = text("Txt3", "3", H + Vector((-0.3, -0.05, 2.25)), 0.5, n3m, CH)
t4 = text("Txt4", "4", H + Vector((0.6, -0.05, 2.25)), 0.5, n4m, CH)
for ob in (g3, shaft_out):
    ob.rotation_mode = "XYZ"
spin(g3, "X", s7 - 10, CLICK, 3.0)
rot_keys(g4, "X", [(s7 - 10, 0), (CLICK, 0.5), (CLICK + 8, 4), (e7, 20)])
key_color(cl3_m, [(CLICK - 1, (1.0, 0.45, 0.08)), (CLICK + 2, (0.2, 0.7, 1.0))])
key_emission(cl3_m, [(CLICK - 1, 12), (CLICK + 2, 1.5)])
key_emission(cl4_m, [(cue("четвёртая") - 3, 2), (cue("четвёртая") + 4, 6), (CLICK - 1, 6), (CLICK + 2, 30), (CLICK + 12, 14)])
key_color(cl4_m, [(CLICK - 1, (0.2, 0.7, 1.0)), (CLICK + 2, (1.0, 0.45, 0.08))])
key_emission(n3m, [(s7, 14), (CLICK - 1, 14), (CLICK + 2, 1.0)])
key_emission(n4m, [(s7, 0.6), (cue("четвёртая") - 3, 0.6), (cue("четвёртая") + 4, 6), (CLICK - 1, 6), (CLICK + 2, 40), (CLICK + 10, 16)])
key_color(n4m, [(CLICK - 1, (0.2, 0.7, 1.0)), (CLICK + 2, (1.0, 0.45, 0.08))])
keyset(c3, "location", [(CLICK - 1, H + Vector((-1.5, 0, 1.4))), (CLICK + 2, H + Vector((-1.6, 0, 1.4)))])
keyset(c4, "location", [(CLICK - 1, H + Vector((-1.38, 0, 1.4))), (CLICK + 2, H + Vector((-1.46, 0, 1.4)))])
light("HKey", "AREA", H + Vector((-2, -3, 3.5)), 500, (1, 0.9, 0.85), 3, target=H + Vector((0, 0, 1.4)))
light("HRim", "AREA", H + Vector((2, 3, 3)), 600, (0.6, 0.4, 1.0), 3, target=H + Vector((0, 0, 1.4)))
NUMS = H + Vector((0.15, 0, 1.9))
cam7 = cam.shot_camera("Cam7", [
    (s7, H + Vector((-1.6, -3.4, 2.2)), H + Vector((-0.6, 0, 1.5)), 32),
    (CLICK - 3, H + Vector((-0.2, -3.0, 2.0)), NUMS, 36),
    (CLICK + 4, H + Vector((0.3, -1.7, 2.0)), H + Vector((0.6, 0, 2.0)), 46),
    (e7 - 6, H + Vector((0.35, -1.6, 2.0)), H + Vector((0.6, 0, 2.0)), 48),
    (e7 + 1, H + Vector((0.4, -1.6, 2.0)), H + Vector((3.2, 0, 2.0)), 48)],
    focus=[(s7, H + Vector((-0.6, 0, 1.5))), (CLICK - 3, NUMS)], fstop=2.8, handheld=0.6)
sfx("sfx_click", CLICK, 0.9)
sfx("sfx_hit", CLICK + 1, 0.7)
sfx("sfx_rev", CLICK + 2, 0.6)
sfx("sfx_whoosh", e7 - 7, 0.7)

# ================================================================ МИР I: студия, четыре коробки (шот 8)
I = Vector((840, 0, 0))
CI = "H_Studio"
dome("Dome_I", I, (0.03, 0.03, 0.035), (0.004, 0.004, 0.005), r=30)
s8, e8 = SH[8]
box("StudioFloor", (14, 8, 0.05), I + Vector((1.8, 1, -0.025)), mat("StudioFloorM", (0.02, 0.02, 0.022), 0.0, 0.25, coat=0.5), CI)
names = [("МЕХАНИКА", "контроля"), ("АВТОМАТ", "комфорта"), ("ВАРИАТОР", "плавности"), ("РОБОТ", "скорости")]
cols = [(1.0, 0.45, 0.08), (0.2, 0.7, 1.0), (0.3, 1.0, 0.5), (0.9, 0.25, 1.0)]
ped_m = mat("Pedestal", (0.05, 0.05, 0.055), 0.3, 0.4)
dark = mat("DarkMetal", (0.08, 0.08, 0.09), 0.9, 0.3)
for k, ((nm, w), col) in enumerate(zip(names, cols)):
    X = I + Vector((k * 1.2, 0, 0))
    hit = cue(w, s8)
    box(f"Ped{k}", (0.8, 0.8, 0.9), X + Vector((0, 0, 0.45)), ped_m, CI, bevel=0.02)
    ring_m = emis(f"PedRing{k}", col, 0)
    box(f"PedStrip{k}", (0.82, 0.82, 0.03), X + Vector((0, 0, 0.88)), ring_m, CI)
    lab_m = emis(f"Label{k}", col, 0.6)
    text(f"Label{k}", nm, X + Vector((0, -0.41, 0.6)), 0.13, lab_m, CI, extrude=0.005)
    key_emission(ring_m, [(s8, 0), (hit - 3, 0), (hit + 3, 20), (hit + 30, 6), (e8, 6)])
    key_emission(lab_m, [(s8, 0.6), (hit - 3, 0.6), (hit + 3, 10), (hit + 30, 4)])
    top = X + Vector((0, 0, 0.9))
    root = core.empty(f"Icon{k}", top + Vector((0, 0, 0.35)), 0.1, CI)
    if k == 0:  # рычаг с H-схемой
        box("Gate", (0.4, 0.3, 0.03), (0, 0, -0.3), dark, CI, parent=root)
        cyl("Lever", 0.02, 0.45, (0, 0, -0.08), rim, CI, parent=root)
        sphere("Knob", 0.07, (0, 0, 0.16), mat("KnobM", (0.02, 0.02, 0.02), 0, 0.4), CI, parent=root)
    elif k == 1:  # селектор P R N D
        box("SelBase", (0.3, 0.45, 0.06), (0, 0, -0.3), dark, CI, parent=root)
        for j, ch in enumerate("PRND"):
            text(f"Sel{ch}", ch, (0.1, 0.15 - j * 0.1, -0.265), 0.07, lab_m, CI, rot=(0, 0, 0), parent=root)
        cyl("SelStick", 0.025, 0.3, (-0.05, -0.15, -0.12), rim, CI, parent=root)
        box("SelHead", (0.08, 0.14, 0.1), (-0.05, -0.15, 0.06), mat("SelHeadM", (0.02, 0.02, 0.02), 0.2, 0.4), CI, bevel=0.02, parent=root)
    elif k == 2:  # мини-вариатор
        for s in (-1, 1):
            cyl(f"MiniCone{s}", 0.17, 0.08, (-0.12, s * 0.05, -0.05), cone_m, CI, rot=(math.radians(-90 * s), 0, 0), r2=0.04, parent=root)
            cyl(f"MiniConeB{s}", 0.17, 0.08, (0.14, s * 0.05, -0.05), cone_m, CI, rot=(math.radians(-90 * s), 0, 0), r2=0.04, parent=root)
        torus("MiniBelt", 0.16, 0.012, (0.01, 0, -0.05), rim, CI, rot=(math.pi / 2, 0, 0), parent=root)
        bpy.data.objects["MiniBelt"].scale = (1.6, 1.0, 0.75)
    else:  # чип
        box("BigChip", (0.34, 0.34, 0.05), (0, 0, -0.2), dark, CI, bevel=0.01, parent=root)
        box("BigChipCore", (0.2, 0.2, 0.02), (0, 0, -0.17), ring_m, CI, parent=root)
        for j in range(6):
            for s in (-1, 1):
                box(f"Pin{j}{s}", (0.02, 0.06, 0.01), (-0.125 + j * 0.05, s * 0.2, -0.22), rim, CI, parent=root)
    spin(root, "Z", s8 - 10, e8 + 10, 0.25 if k % 2 else -0.25)
    keyset(root, "location", [(hit - 4, top + Vector((0, 0, 0.3))), (hit + 4, top + Vector((0, 0, 0.42))), (hit + 16, top + Vector((0, 0, 0.36)))])
    light(f"IconSpot{k}", "SPOT", X + Vector((0, -0.6, 3.0)), 0, col, 0.1, spot=math.radians(28), target=top)
    sl = bpy.data.objects[f"IconSpot{k}"]
    for f, v in ((s8, 40), (hit - 3, 40), (hit + 3, 600), (hit + 30, 250)):
        sl.data.energy = v
        sl.data.keyframe_insert("energy", frame=f)
    sfx("sfx_hit", hit, 0.5)
light("IKey", "AREA", I + Vector((1.8, -4, 4)), 300, (1, 0.95, 0.9), 6, target=I + Vector((1.8, 0, 1.0)))
light("IRim", "AREA", I + Vector((1.8, 3, 3)), 400, (0.5, 0.6, 1.0), 6, target=I + Vector((1.8, 0, 1.0)))
cam8 = cam.shot_camera("Cam8", [
    (s8, I + Vector((-0.6, -2.4, 1.55)), I + Vector((0.0, 0, 1.1)), 35),
    (e8 + 1, I + Vector((4.2, -2.4, 1.6)), I + Vector((3.6, 0, 1.1)), 35)], focus=None, handheld=0.3)

# ---------------------------------------------------------------- склейки, рендер-настройки, звуки
cams = {1: cam1, 2: cam2, 3: cam3, 4: cam4, 5: cam5, 6: cam6, 7: cam7, 8: cam8, 9: cam9}
shots = dict(SH)
cam.bind_markers(shots, cams)
m = sc.timeline_markers.new("S4b", frame=FANS)
m.camera = cam4b
for c in cams.values():
    c.data.clip_start = 0.05
    c.data.clip_end = 200
cam4b.data.clip_start = 0.05

world = bpy.data.worlds.new("World")
sc.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.002, 0.002, 0.004, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

ee = sc.eevee
ee.taa_render_samples = 16
try:
    ee.use_shadows = True
    ee.shadow_ray_count = 1
    ee.shadow_step_count = 4
except Exception:
    pass
sc.render.use_motion_blur = True
sc.render.motion_blur_shutter = 0.5

# свечение (bloom) через композитор
try:
    ng = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
    sc.compositing_node_group = ng
    rl = ng.nodes.new("CompositorNodeRLayers")
    gl = ng.nodes.new("CompositorNodeGlare")
    out = ng.nodes.new("NodeGroupOutput")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    try:
        gl.inputs["Type"].default_value = "Bloom"
        gl.inputs["Threshold"].default_value = 1.0
        gl.inputs["Strength"].default_value = 0.6
        gl.inputs["Size"].default_value = 0.5
    except Exception:
        gl.glare_type = "BLOOM"
    ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
    ng.links.new(gl.outputs["Image"], out.inputs[0])
    sc.render.use_compositing = True
    print("BLOOM ok")
except Exception as ex:
    print("BLOOM skipped", ex)

(PROJECT / "audio" / "cues.json").write_text(json.dumps(sorted(CUES, key=lambda c: c["f"]), ensure_ascii=False, indent=1), encoding="utf-8")
core.save(PROJECT)
print("SAVED", PROJECT / "scene.blend", "frames", TOTAL)
