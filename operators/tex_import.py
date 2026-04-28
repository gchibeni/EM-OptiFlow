"""
Background texture processing + Blender material application for OptiFlow.

Flow:
  1. schedule_tex_import()  called from items.py after the item is created
  2. _process_job()         daemon thread: PIL-processes each texture one by one,
                            appending a _BpyTask to _bpy_queue and incrementing
                            _pil_done for each texture (gives 0-50% progress)
  3. _apply_pending()       bpy.app.timer: pops one _BpyTask per call, loads it
                            into Blender, builds the material when the job is
                            complete (gives 50-100% progress)
"""

import bpy
import os
import threading
import tempfile

from ..core import helpers

# ── Module-level state ───────────────────────────────────────────────────────

_lock             = threading.Lock()
_pil_done         = 0     # individual textures PIL-processed so far
_pil_total        = 0     # total individual textures to process (all jobs)
_active_threads   = 0     # PIL threads still running
_bpy_queue        = []    # list[_BpyTask] ready to load into Blender
_bpy_done         = 0     # individual textures loaded into Blender so far
_timer_registered = False
_cleanup_pending  = False

# ── Constants ────────────────────────────────────────────────────────────────

_COMPRESSION_LABELS = {
    'AUTO':     'Auto',
    'SMALLEST': 'Smallest Size',
    'BALANCED': 'Balanced',
    'HIGHER':   'Higher Quality',
}

_FORMAT_MAP = {
    'JPG':  ('JPEG', 'jpg'),
    'PNG':  ('PNG',  'png'),
    'WEBP': ('WEBP', 'webp'),
}

_SKIP_PREFIXES = frozenset({'COL', 'PLACER', 'SNAP', 'GUIDE'})

_NON_COLOR_TYPES = frozenset({
    'ORM', 'Roughness', 'Reflection', 'Metallic',
    'Normal', 'Opacity', 'Occlusion',
})

_ORM_COMPONENT_TYPES = frozenset({'Roughness', 'Metallic', 'Occlusion'})

# ── Data classes ──────────────────────────────────────────────────────────────

class _TexJob:
    """Represents one item's full texture import task."""
    __slots__ = (
        'gi', 'ii', 'mesh_obj_names', 'overrides', 'temp_dir',
        'tex_by_type',    # dict[str, list[str]]  tex_type → [src_path, ...]
        'bpy_remaining',  # int — Blender tasks left before material can be built
        'bpy_images',     # dict[str, list[bpy.types.Image]]
        'first_error',    # str | None
    )

    def __init__(self, gi, ii, mesh_obj_names, overrides, temp_dir, tex_by_type):
        self.gi             = gi
        self.ii             = ii
        self.mesh_obj_names = mesh_obj_names
        self.overrides      = overrides
        self.temp_dir       = temp_dir
        self.tex_by_type    = tex_by_type
        self.bpy_remaining  = sum(len(v) for v in tex_by_type.values())
        self.bpy_images     = {}
        self.first_error    = None


class _BpyTask:
    """One texture file that needs to be loaded into Blender on the main thread."""
    __slots__ = ('job', 'tex_type', 'temp_path', 'failed')

    def __init__(self, job, tex_type, temp_path, failed=False):
        self.job       = job
        self.tex_type  = tex_type
        self.temp_path = temp_path
        self.failed    = failed

# ── Public API ────────────────────────────────────────────────────────────────

def schedule_tex_import(gi, ii, mesh_obj_names, src_paths, overrides, scene):
    """
    Kick off async PIL processing + Blender material application for one item.

    gi / ii           — group / item indices in scene.optiflow_groups
    mesh_obj_names    — names of MESH objects belonging to this item
    src_paths         — flat list of texture file paths
    overrides         — dict with roughness/metallic/size/compression/format flags+values
    scene             — current bpy.types.Scene (for progress tracking)
    """
    global _pil_total, _active_threads, _timer_registered

    from ..operators.items import _classify_tex

    # Classify and filter
    tex_by_type = {}
    for path in src_paths:
        t = _classify_tex(os.path.basename(path))
        if t is not None:
            tex_by_type.setdefault(t, []).append(path)

    tex_by_type.pop('Height', None)
    tex_by_type.pop('Mask', None)

    if 'ORM' in tex_by_type:
        tex_by_type.pop('Occlusion', None)
        tex_by_type.pop('Roughness', None)
        tex_by_type.pop('Metallic',  None)

    if 'Roughness' in tex_by_type and 'Reflection' in tex_by_type:
        tex_by_type.pop('Reflection')

    if not tex_by_type:
        return

    has_orm_components = any(t in tex_by_type for t in _ORM_COMPONENT_TYPES)
    has_opacity_merge  = 'Color' in tex_by_type and 'Opacity' in tex_by_type
    tex_count = sum(len(v) for v in tex_by_type.values())
    if has_orm_components:
        component_count  = sum(len(tex_by_type.get(t, [])) for t in _ORM_COMPONENT_TYPES)
        tex_count       -= component_count - 1
    if has_opacity_merge:
        tex_count -= len(tex_by_type['Opacity'])
    temp_dir  = tempfile.mkdtemp(prefix='optiflow_tex_')
    job       = _TexJob(gi, ii, mesh_obj_names, overrides, temp_dir, tex_by_type)
    if has_orm_components or has_opacity_merge:
        job.bpy_remaining = tex_count

    with _lock:
        _pil_total      += tex_count
        _active_threads += 1

    scene.optiflow_is_importing = True

    t = threading.Thread(target=_process_job, args=(job,), daemon=True)
    t.start()

    if not _timer_registered:
        _timer_registered = True
        bpy.app.timers.register(_apply_pending, first_interval=0.2)


def cancel_all():
    """Called on addon unregister — clears all pending state."""
    global _pil_done, _pil_total, _active_threads, _bpy_queue, _bpy_done
    global _timer_registered, _cleanup_pending
    with _lock:
        _bpy_queue.clear()
        _pil_done         = 0
        _pil_total        = 0
        _active_threads   = 0
        _bpy_done         = 0
        _timer_registered = False
        _cleanup_pending  = False

# ── Phase 1: Background PIL thread ────────────────────────────────────────────

def _select_format(ov, src_ext, tex_type=None):
    if ov.get('format_enabled'):
        fmt = ov['format']
        if fmt == 'AUTO':
            return ('PNG', 'png') if tex_type in ('Normal', 'ORM') else ('JPEG', 'jpg')
        return _FORMAT_MAP.get(fmt, ('JPEG', 'jpg'))
    if src_ext in ('.jpg', '.jpeg'):
        return 'JPEG', 'jpg'
    if src_ext == '.webp':
        return 'WEBP', 'webp'
    return 'PNG', 'png'


def _select_alpha_format(ov, src_ext, tex_type=None):
    pil_format, ext = _select_format(ov, src_ext, tex_type)
    if pil_format == 'JPEG':
        return 'PNG', 'png'
    return pil_format, ext


def _derive_orm_stem(src_path):
    """Strip the recognized type suffix from a source filename to produce an ORM base name."""
    from ..operators.items import _TEX_ALIASES
    stem  = os.path.splitext(os.path.basename(src_path))[0]
    lower = stem.lower()
    for _, aliases in _TEX_ALIASES:
        for alias in aliases:
            idx = lower.rfind(alias)
            if idx != -1:
                return stem[:idx]
    return stem


def _process_job(job):
    """PIL-only: process each texture, saving to temp dir, queuing one _BpyTask per file."""
    global _pil_done, _active_threads

    ov = job.overrides

    orm_sources = {t: job.tex_by_type[t][0]
                   for t in _ORM_COMPONENT_TYPES if t in job.tex_by_type}
    color_paths = job.tex_by_type.get('Color', [])
    opacity_src = (job.tex_by_type['Opacity'][0]
                   if 'Opacity' in job.tex_by_type and color_paths else None)
    other_tasks = [(t, p)
                   for t, paths in job.tex_by_type.items()
                   if t not in _ORM_COMPONENT_TYPES and t != 'Color'
                   and not (t == 'Opacity' and color_paths)
                   for p in paths]

    try:
        from ..core.tex_utils import (
            get_image, resize_image, invert_image, save_image, adjust_reflectivity,
        )
        tex_utils_ok = True
    except Exception as e:
        tex_utils_ok = False
        job.first_error = str(e)

    try:
        # ORM combination: Roughness→G, Metallic→B, Occlusion→R
        if orm_sources:
            out_path = None
            failed   = not tex_utils_ok
            if not failed:
                try:
                    from PIL import Image as PILImage

                    def _prep_channel(tex_type, src_path):
                        img = get_image(src_path)
                        if tex_type in ('Roughness',) and ov.get('roughness_enabled'):
                            img = adjust_reflectivity(img, ov['roughness'] / 100.0)
                        elif tex_type == 'Metallic' and ov.get('metallic_enabled'):
                            img = adjust_reflectivity(img, ov['metallic'] / 100.0)
                        img = img.convert('L')
                        if ov.get('size_enabled'):
                            img = resize_image(img, (int(ov['size']), int(ov['size'])))
                        return img

                    rough_img = _prep_channel('Roughness', orm_sources['Roughness']) if 'Roughness' in orm_sources else None
                    metal_img = _prep_channel('Metallic',  orm_sources['Metallic'])  if 'Metallic'  in orm_sources else None
                    occl_img  = _prep_channel('Occlusion', orm_sources['Occlusion']) if 'Occlusion' in orm_sources else None

                    ref   = rough_img or metal_img or occl_img
                    w, h  = ref.size
                    white = PILImage.new('L', (w, h), 255)
                    black = PILImage.new('L', (w, h), 0)

                    def _fit(img, fallback):
                        if img is None:
                            return fallback
                        return img if img.size == (w, h) else img.resize((w, h), PILImage.LANCZOS)

                    # For missing channels, bake the override value in as a solid fill
                    # rather than a hardcoded default — the ORM node bypasses shader values.
                    rough_fallback = (PILImage.new('L', (w, h), int(ov['roughness'] / 100.0 * 255))
                                      if rough_img is None and ov.get('roughness_enabled') else white)
                    metal_fallback = (PILImage.new('L', (w, h), int(ov['metallic'] / 100.0 * 255))
                                      if metal_img is None and ov.get('metallic_enabled') else black)

                    orm_img = PILImage.merge('RGB', (
                        _fit(occl_img,  white),
                        _fit(rough_img, rough_fallback),
                        _fit(metal_img, metal_fallback),
                    ))

                    ref_src = (orm_sources.get('Roughness')
                               or orm_sources.get('Metallic')
                               or orm_sources.get('Occlusion'))
                    stem = _derive_orm_stem(ref_src) + '_ORM'

                    orig_ext = os.path.splitext(ref_src)[1].lower()
                    pil_format, ext = _select_format(ov, orig_ext, 'ORM')

                    compression = 'Uncompressed'
                    if ov.get('compression_enabled'):
                        compression = _COMPRESSION_LABELS.get(ov['compression'], 'Uncompressed')

                    out_path = os.path.join(job.temp_dir, f"{stem}.{ext}")
                    n = 0
                    while os.path.exists(out_path):
                        n += 1
                        out_path = os.path.join(job.temp_dir, f"{stem}_{n}.{ext}")

                    save_image(orm_img, out_path, format=pil_format, compression=compression)

                except Exception as e:
                    failed = True
                    if job.first_error is None:
                        job.first_error = str(e)

            with _lock:
                _bpy_queue.append(_BpyTask(job, 'ORM', out_path, failed))
                _pil_done += 1

        # Color + optional opacity merge
        for color_src in color_paths:
            out_path = None
            failed   = not tex_utils_ok
            if not failed:
                try:
                    from PIL import Image as PILImage

                    img = get_image(color_src)
                    source_info = dict(img.info)
                    if hasattr(img, 'quantization'):
                        source_info['quantization'] = img.quantization
                    try:
                        from PIL.JpegImagePlugin import get_sampling
                        source_info['subsampling'] = get_sampling(img)
                    except Exception:
                        pass

                    orig_ext = os.path.splitext(color_src)[1].lower()
                    if ov.get('size_enabled'):
                        img = resize_image(img, (int(ov['size']), int(ov['size'])))

                    if opacity_src:
                        opc = get_image(opacity_src).convert('L')
                        if ov.get('size_enabled'):
                            opc = resize_image(opc, (int(ov['size']), int(ov['size'])))
                        if img.size != opc.size:
                            opc = opc.resize(img.size, PILImage.LANCZOS)
                        img = img.convert('RGBA')
                        img.putalpha(opc)
                        pil_format, ext = _select_alpha_format(ov, orig_ext)
                    elif img.mode in ('RGBA', 'LA'):
                        alpha = img.split()[-1]
                        if alpha.getextrema()[0] < 255:
                            img = img.convert('RGBA')
                            pil_format, ext = _select_alpha_format(ov, orig_ext)
                        else:
                            img = img.convert('RGB')
                            pil_format, ext = _select_format(ov, orig_ext)
                    else:
                        img = img.convert('RGB')
                        pil_format, ext = _select_format(ov, orig_ext)

                    compression = 'Uncompressed'
                    if ov.get('compression_enabled'):
                        compression = _COMPRESSION_LABELS.get(ov['compression'], 'Uncompressed')

                    stem = os.path.splitext(os.path.basename(color_src))[0]
                    out_path = os.path.join(job.temp_dir, f"{stem}.{ext}")
                    n = 0
                    while os.path.exists(out_path):
                        n += 1
                        out_path = os.path.join(job.temp_dir, f"{stem}_{n}.{ext}")

                    save_image(img, out_path, format=pil_format,
                               compression=compression, source_info=source_info)

                except Exception as e:
                    failed = True
                    if job.first_error is None:
                        job.first_error = str(e)

            with _lock:
                _bpy_queue.append(_BpyTask(job, 'Color', out_path, failed))
                _pil_done += 1

        # All other texture types processed individually
        for tex_type, src_path in other_tasks:
            out_path = None
            failed   = not tex_utils_ok

            if not failed:
                try:
                    img = get_image(src_path)

                    source_info = dict(img.info)
                    if hasattr(img, 'quantization'):
                        source_info['quantization'] = img.quantization
                    try:
                        from PIL.JpegImagePlugin import get_sampling
                        source_info['subsampling'] = get_sampling(img)
                    except Exception:
                        pass

                    if tex_type == 'Reflection':
                        img = invert_image(img)

                    if tex_type in ('Roughness', 'Reflection') and ov.get('roughness_enabled'):
                        img = adjust_reflectivity(img, ov['roughness'] / 100.0)
                    elif tex_type == 'Metallic' and ov.get('metallic_enabled'):
                        img = adjust_reflectivity(img, ov['metallic'] / 100.0)

                    if ov.get('size_enabled'):
                        size = int(ov['size'])
                        img  = resize_image(img, (size, size), keep_aspect=True)

                    orig_ext = os.path.splitext(src_path)[1].lower()
                    pil_format, ext = _select_format(ov, orig_ext, tex_type)

                    compression = 'Uncompressed'
                    if ov.get('compression_enabled'):
                        compression = _COMPRESSION_LABELS.get(ov['compression'], 'Uncompressed')

                    stem     = os.path.splitext(os.path.basename(src_path))[0]
                    out_path = os.path.join(job.temp_dir, f"{stem}.{ext}")
                    n = 0
                    while os.path.exists(out_path):
                        n += 1
                        out_path = os.path.join(job.temp_dir, f"{stem}_{n}.{ext}")

                    save_image(img, out_path, format=pil_format,
                               compression=compression, source_info=source_info)

                except Exception as e:
                    failed = True
                    if job.first_error is None:
                        job.first_error = str(e)

            with _lock:
                _bpy_queue.append(_BpyTask(job, tex_type, out_path, failed))
                _pil_done += 1

    finally:
        with _lock:
            _active_threads -= 1

# ── Phase 2: Main-thread timer ────────────────────────────────────────────────

def _apply_pending():
    """Load one processed texture into Blender per call; build material when job is done."""
    global _timer_registered, _cleanup_pending, _bpy_done

    if _cleanup_pending:
        _reset_state()
        return None

    with _lock:
        task         = _bpy_queue.pop(0) if _bpy_queue else None
        pil_done     = _pil_done
        pil_total    = _pil_total
        queue_left   = len(_bpy_queue)
        threads_left = _active_threads

    if task is not None:
        _load_bpy_task(task)
        with _lock:
            _bpy_done += 1
            bpy_done = _bpy_done

        if task.job.bpy_remaining == 0:
            try:
                _build_material_for_job(task.job)
            except Exception as e:
                print(f"[OptiFlow] Material build error for [{task.job.gi}][{task.job.ii}]: {e}")
    else:
        with _lock:
            bpy_done = _bpy_done

    # Update progress bar: PIL counts as first 50%, Blender loading as second 50%
    progress = min(1.0, (pil_done + bpy_done) / (pil_total * 2)) if pil_total > 0 else 0.0
    for scene in bpy.data.scenes:
        if scene.optiflow_is_importing:
            scene.optiflow_tex_progress = progress
            break

    _tag_redraw_all()

    if task is not None or threads_left > 0 or queue_left > 0:
        return 0.1

    _cleanup_pending = True
    return 0.5


def _load_bpy_task(task):
    """Load one temp file into Blender. Always decrements job.bpy_remaining."""
    job = task.job
    try:
        if not task.failed and task.temp_path and os.path.exists(task.temp_path):
            colorspace = 'Non-Color' if task.tex_type in _NON_COLOR_TYPES else 'sRGB'
            bpy_img = bpy.data.images.load(task.temp_path)
            try:
                bpy_img.colorspace_settings.name = colorspace
            except Exception:
                pass
            job.bpy_images.setdefault(task.tex_type, []).append(bpy_img)
    except Exception as e:
        if job.first_error is None:
            job.first_error = str(e)
    finally:
        job.bpy_remaining -= 1


def _reset_state():
    """Reset all module counters and hide the progress bar."""
    global _pil_done, _pil_total, _bpy_done, _timer_registered, _cleanup_pending
    _cleanup_pending  = False
    _timer_registered = False
    _pil_done  = 0
    _pil_total = 0
    _bpy_done  = 0
    for scene in bpy.data.scenes:
        scene.optiflow_is_importing = False
        scene.optiflow_tex_progress = 0.0
    _tag_redraw_all()


def _tag_redraw_all():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()

# ── Material construction ─────────────────────────────────────────────────────

def _build_material_for_job(job):
    """Build and assign Principled BSDF material once all images for a job are loaded."""
    if not job.bpy_images:
        if job.first_error:
            print(f"[OptiFlow] All textures failed for [{job.gi}][{job.ii}]: {job.first_error}")
        return

    # gi < 0 is a sentinel used by change_textures — no item guard needed
    if job.gi >= 0:
        item = None
        for sc in bpy.data.scenes:
            try:
                g = sc.optiflow_groups[job.gi]
                i = g.items[job.ii]
                item = i
                break
            except (IndexError, AttributeError, KeyError):
                continue
        if item is None:
            return

    # Collect valid mesh objects
    mesh_objs = []
    for name in job.mesh_obj_names:
        obj = bpy.data.objects.get(name)
        if obj and obj.type == 'MESH' and helpers.get_prefix(obj) not in _SKIP_PREFIXES:
            mesh_objs.append(obj)
    if not mesh_objs:
        return

    colors         = job.bpy_images.get('Color', [])
    is_multi_color = (
        (job.overrides.get('item_mode') == 'OBJECT' and len(mesh_objs) > 2 and len(colors) > 1)
        or (job.overrides.get('change_tex') and len(mesh_objs) > 1 and len(colors) > 1)
    )

    if is_multi_color:
        for idx, obj in enumerate(mesh_objs):
            color_img = colors[idx] if idx < len(colors) else colors[-1]
            mat = _build_material(job.bpy_images, color_img, job.overrides)
            _assign_material(obj, mat)
    else:
        color_img = colors[0] if colors else None
        mat = _build_material(job.bpy_images, color_img, job.overrides)
        for obj in mesh_objs:
            _assign_material(obj, mat)

    # Purge old materials and images that are no longer referenced anywhere.
    # Materials must be removed first so their node trees release image users.
    for mat_name in job.overrides.get('old_mat_names', []):
        old_mat = bpy.data.materials.get(mat_name)
        if old_mat and old_mat.users == 0:
            bpy.data.materials.remove(old_mat)

    for img_name in job.overrides.get('old_image_names', []):
        old_img = bpy.data.images.get(img_name)
        if old_img and old_img.users == 0:
            bpy.data.images.remove(old_img)


def _unique_mat_name(base='Mat'):
    if base not in bpy.data.materials:
        return base
    n = 1
    while f"{base}_{n}" in bpy.data.materials:
        n += 1
    return f"{base}_{n}"


def _assign_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def _build_material(bpy_images, color_img, overrides):
    """Create a Principled BSDF material from pre-loaded bpy.types.Image objects."""
    mat = bpy.data.materials.new(name=_unique_mat_name('Mat'))
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    out  = nodes.new('ShaderNodeOutputMaterial')
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

    # Base Color — alpha connected only when the image is genuinely RGBA (depth=32)
    if color_img is not None:
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = color_img
        links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        if color_img.depth == 32:
            gt = nodes.new('ShaderNodeMath')
            gt.operation = 'GREATER_THAN'
            gt.inputs[1].default_value = 0.5
            links.new(tex.outputs['Alpha'], gt.inputs[0])
            links.new(gt.outputs['Value'], bsdf.inputs['Alpha'])
            mat.blend_method = 'CLIP'

    # Standalone opacity (only when no Color map was present — opacity was not merged)
    if color_img is None and bpy_images.get('Opacity'):
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = bpy_images['Opacity'][0]
        gt  = nodes.new('ShaderNodeMath')
        gt.operation = 'GREATER_THAN'
        gt.inputs[1].default_value = 0.5
        links.new(tex.outputs['Color'], gt.inputs[0])
        links.new(gt.outputs['Value'], bsdf.inputs['Alpha'])
        mat.blend_method = 'CLIP'

    # ORM: separate R/G/B — G→Roughness, B→Metallic
    if bpy_images.get('ORM'):
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = bpy_images['ORM'][0]
        sep = nodes.new('ShaderNodeSeparateColor')
        links.new(tex.outputs['Color'], sep.inputs['Color'])
        links.new(sep.outputs['Green'], bsdf.inputs['Roughness'])
        links.new(sep.outputs['Blue'],  bsdf.inputs['Metallic'])
    else:
        # Roughness / Reflection (already inverted in PIL step)
        rough_imgs = bpy_images.get('Roughness') or bpy_images.get('Reflection')
        if rough_imgs:
            tex = nodes.new('ShaderNodeTexImage')
            tex.image = rough_imgs[0]
            links.new(tex.outputs['Color'], bsdf.inputs['Roughness'])
        elif overrides.get('roughness_enabled'):
            bsdf.inputs['Roughness'].default_value = overrides['roughness'] / 100.0

        metal_imgs = bpy_images.get('Metallic')
        if metal_imgs:
            tex = nodes.new('ShaderNodeTexImage')
            tex.image = metal_imgs[0]
            links.new(tex.outputs['Color'], bsdf.inputs['Metallic'])
        elif overrides.get('metallic_enabled'):
            bsdf.inputs['Metallic'].default_value = overrides['metallic'] / 100.0

    # Normal map
    if bpy_images.get('Normal'):
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = bpy_images['Normal'][0]
        nm  = nodes.new('ShaderNodeNormalMap')
        links.new(tex.outputs['Color'], nm.inputs['Color'])
        links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])

    # Emission
    if bpy_images.get('Emission'):
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = bpy_images['Emission'][0]
        links.new(tex.outputs['Color'], bsdf.inputs['Emission Color'])
        bsdf.inputs['Emission Strength'].default_value = 1.0

    _arrange_mat_nodes(mat.node_tree)
    return mat


def _arrange_mat_nodes(node_tree):
    """Simple columnar layout: textures → utilities → BSDF → output."""
    y_gap = 300
    cols  = {
        'TEX_IMAGE':       -800,
        'SEPARATE_COLOR':  -400,
        'NORMAL_MAP':      -400,
        'MATH':            -400,
        'BSDF_PRINCIPLED':    0,
        'OUTPUT_MATERIAL':  380,
    }
    col_rows = {}
    for node in node_tree.nodes:
        t = node.type
        if t not in cols:
            continue
        x             = cols[t]
        row           = col_rows.get(x, 0)
        node.location = (x, -row * y_gap)
        col_rows[x]   = row + 1
