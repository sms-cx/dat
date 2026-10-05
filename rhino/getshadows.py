#! python 3
"""
I didn't create the original script, this is the update to work in python 3 and remove some quirks of the original.
I do not know who created the initial version.

copyright 2026 Simon Trapp
"""

# Version 1.3

import System
import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
from System.Collections.Generic import List

RG = Rhino.Geometry
VECTOR_LAYER = "shadows_vector"
HATCH_LAYER = "shadow_hatch"


# helpers
def _to_brep(geo):
    if isinstance(geo, (RG.Extrusion, RG.Surface)):
        return geo.ToBrep()
    return geo


def _unit(v):
    length = v.Length
    if length < 1e-12:
        return None
    return RG.Vector3d(v.X / length, v.Y / length, v.Z / length)


def _dot(a, b):
    return a.X * b.X + a.Y * b.Y + a.Z * b.Z


def _ensure_layer(name, color):
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = name
        layer.Color = color
        idx = sc.doc.Layers.Add(layer)
    return idx


def _solid_hatch_index():
    hp = sc.doc.HatchPatterns.FindName("Solid")
    if hp is not None and not hp.IsDeleted:
        return hp.Index
    return sc.doc.HatchPatterns.Add(Rhino.DocObjects.HatchPattern.Defaults.Solid)


def _first_hit(origin, direction, breps, meshes):
    # first surface distance along ray
    best = None
    if breps.Count:
        ray = RG.Ray3d(origin, direction)
        try:
            events = RG.Intersect.Intersection.RayShoot(breps, ray, 1)
            if events:
                best = origin.DistanceTo(events[0].Point)
        except Exception:
            pts = RG.Intersect.Intersection.RayShoot(ray, breps, 1)
            if pts:
                best = origin.DistanceTo(pts[0])
    for m in meshes:
        t = RG.Intersect.Intersection.MeshRay(m, RG.Ray3d(origin, direction))
        if t >= 0 and (best is None or t < best):
            best = t
    return best


def _plane_hit(origin, direction, plane):
    line = RG.Line(origin, origin + direction)
    ok, t = RG.Intersect.Intersection.LinePlane(line, plane)
    if ok and t > 0:
        return t
    return None


def _split_geoms(geoms):
    breps = List[RG.GeometryBase]()
    meshes = []
    for g in geoms:
        if isinstance(g, RG.Mesh):
            meshes.append(g)
        else:
            breps.Add(g)
    return breps, meshes


# main
def ShadowCurves():
    tol = sc.doc.ModelAbsoluteTolerance
    aTol = sc.doc.ModelAngleToleranceRadians
    cPlane = rs.ViewCPlane()
    targIds = None

    ids = rs.GetObjects("Select objects to cast shadows", filter=8 + 16 + 32, preselect=True)
    if not ids:
        return
    casters = [(id, _to_brep(sc.doc.Objects.FindId(id).Geometry)) for id in ids]

    # --- target selection ---------------------------------------------------
    blnC = sc.sticky.get('INCLUDE_CPLANE', True)
    while True:
        go = Rhino.Input.Custom.GetObject()
        go.GeometryFilter = Rhino.DocObjects.ObjectType.Brep
        go.SetCommandPrompt("Select target objects. Press Enter to use the current CPlane only.")
        opCPlane = Rhino.Input.Custom.OptionToggle(blnC, "No", "Yes")
        go.AddOptionToggle("IncludeCPlane", opCPlane)
        rc = go.GetMultiple(1, 0)

        if rc == Rhino.Input.GetResult.Option:
            blnC = opCPlane.CurrentValue
            sc.sticky['INCLUDE_CPLANE'] = blnC
            continue
        if go.CommandResult() != Rhino.Commands.Result.Success:
            if not blnC:
                return
            break
        if rc == Rhino.Input.GetResult.Object:
            targIds = [go.Object(i).ObjectId for i in range(go.ObjectCount)]
            break

    targets = []
    if targIds:
        targets = [(id, _to_brep(sc.doc.Objects.FindId(id).Geometry)) for id in targIds]
    else:
        blnC = True

    # light direction
    vecDir = None

    def lights_with_dir(rhino_object, geometry, component_index):
        return not (geometry.IsLinearLight or geometry.IsPointLight)

    while True:
        go = Rhino.Input.Custom.GetObject()
        idxDir = go.AddOption("Direction")
        idxSun = go.AddOption("Sun")
        go.SetCommandPrompt("Select a light.")
        go.GeometryFilter = Rhino.DocObjects.ObjectType.Light
        go.SetCustomGeometryFilter(lights_with_dir)
        rc = go.Get()

        if go.CommandResult() != Rhino.Commands.Result.Success:
            return go.CommandResult()
        if rc == Rhino.Input.GetResult.Object:
            light = go.Object(0).Light()
            if light.IsPointLight or light.IsLinearLight:
                print("Cannot get shadow curves from a linear or point light.")
                continue
            vecDir = light.Direction
            break
        elif rc == Rhino.Input.GetResult.Option:
            idx = go.OptionIndex()
            if idx == idxDir:
                lineRC, line = Rhino.Input.RhinoGet.GetLine()
                if lineRC != Rhino.Commands.Result.Success:
                    return
                vecDir = line.To - line.From
            elif idx == idxSun:
                vecDir = sc.doc.Lights.Sun.Vector
            break

    u = _unit(vecDir) if vecDir is not None else None
    if u is None:
        print("No valid shadow direction.")
        return
    negU = RG.Vector3d(-u.X, -u.Y, -u.Z)

    # scene setup
    occluders = {}
    for gid, g in casters + targets:
        occluders[gid] = g
    occBreps, occMeshes = _split_geoms(occluders.values())

    bb = RG.BoundingBox.Empty
    for g in occluders.values():
        bb.Union(g.GetBoundingBox(True))
    diag = max(bb.Diagonal.Length, 1.0)

    # project plane P as master, normal to light
    P = RG.Plane(bb.Center - u * (diag + 1.0), u)
    eps = max(tol * 10.0, diag * 2e-5)      # cleanup for selfshadows
    depthTol = max(tol * 50.0, eps * 20.0)  # depth match tolerance
    spacing = diag / 300.0

    # per-caster shadow regions in P
    # loops: (curve, isOuter); outer loops CCW, holes CW, so (tangent x u) always points out of the shadow.
    def silhouette_loops(geo):
        sils = RG.Silhouette.Compute(geo, RG.SilhouetteType.Boundary, u, tol, aTol)
        if not sils:
            return []
        proj = [RG.Curve.ProjectToPlane(s.Curve, P) for s in sils if s.Curve is not None]
        proj = [c for c in proj if c is not None]
        if not proj:
            return []
        joined = RG.Curve.JoinCurves(List[RG.Curve](proj), tol * 2.0, False)
        closed = [c for c in joined if c.IsClosed]
        if not closed:
            return []
        regions = RG.Brep.CreatePlanarBreps(List[RG.Curve](closed), tol)
        loops = []
        for b in regions or []:
            for face in b.Faces:
                for lp in face.Loops:
                    crv = lp.To3dCurve()
                    outer = lp.LoopType == RG.BrepLoopType.Outer
                    want = (RG.CurveOrientation.CounterClockwise if outer
                            else RG.CurveOrientation.Clockwise)
                    if crv.ClosedCurveOrientation(P) != want:
                        crv.Reverse()
                    loops.append((crv, outer))
        return loops

    casterData = []
    for cid, geo in casters:
        loops = silhouette_loops(geo)
        if loops:
            casterData.append((cid, loops))

    if not casterData:
        print("No closed silhouettes could be computed.")
        return

    # visibility test
    def first_hit_from_P(origin):
        best = _first_hit(origin, u, occBreps, occMeshes)
        if blnC:
            d = _plane_hit(origin, u, cPlane)
            if d is not None and (best is None or d < best):
                best = d
        return best

    def visible(q, loop):
        # q is visible shadow edge for vertical shadows
        p = P.ClosestPoint(q)
        depth = _dot(q - P.Origin, u)
        ok, t = loop.ClosestPoint(p)
        if not ok:
            return False
        n = _unit(RG.Vector3d.CrossProduct(loop.TangentAt(t), u))
        if n is None:
            return False
        hit = first_hit_from_P(p + n * eps)
        if hit is None or abs(hit - depth) >= depthTol:
            return False
        inner = first_hit_from_P(p - n * eps)
        return inner is not None and inner < depth - depthTol

    def visible_parts(crv, loop):
        length = crv.GetLength()
        if length < tol:
            return []
        dom = crv.Domain
        n = int(min(max(length / spacing, 24), 400))
        ts = [dom.ParameterAt(i / float(n)) for i in range(n + 1)]
        flags = [visible(crv.PointAt(t), loop) for t in ts]
        if not any(flags):
            return []
        if all(flags):
            return [crv]

        def refine(a, b, fa):
            for _ in range(12):
                m = 0.5 * (a + b)
                if visible(crv.PointAt(m), loop) == fa:
                    a = m
                else:
                    b = m
            return 0.5 * (a + b)

        intervals = []
        start = dom.Min if flags[0] else None
        for i in range(n):
            if flags[i] != flags[i + 1]:
                x = refine(ts[i], ts[i + 1], flags[i])
                if flags[i]:
                    intervals.append((start, x))
                    start = None
                else:
                    start = x
        if start is not None:
            intervals.append((start, dom.Max))

        # merge curves to closed
        if crv.IsClosed and flags[0] and flags[-1] and len(intervals) > 1:
            first = intervals.pop(0)
            last = intervals.pop()
            intervals.append((last[0], first[1]))

        parts = []
        for a, b in intervals:
            piece = crv.Trim(a, b)
            if piece is not None and piece.GetLength() > tol:
                parts.append(piece)
        return parts

    # shadow edges
    rs.EnableRedraw(False)
    try:
        kept = []
        cplaneXf = RG.Transform.ProjectAlong(cPlane, u)
        for cid, loops in casterData:
            for loop, _ in loops:
                projs = []
                for _, tb in targets:
                    if isinstance(tb, RG.Brep):
                        r = RG.Curve.ProjectToBrep(loop, tb, u, tol)
                        if r:
                            projs.extend(r)
                if blnC:
                    d = loop.DuplicateCurve()
                    if d.Transform(cplaneXf):
                        projs.append(d)
                for c in projs:
                    kept.extend(visible_parts(c, loop))

        outlines = []
        if kept:
            outlines = list(RG.Curve.JoinCurves(List[RG.Curve](kept), eps * 3.0, False))

        # hatches
        hatchIdx = _solid_hatch_index()

        def upstream_part(geo, plane, nLight):
            cut = RG.Plane(plane.Origin + nLight * eps, nLight)
            gbb = geo.GetBoundingBox(True)
            dists = [cut.DistanceTo(c) for c in gbb.GetCorners()]
            if min(dists) >= 0:
                return [geo]                      # completely on the light side
            if max(dists) <= 0:
                return []                         # completely behind the plane
            if isinstance(geo, RG.Mesh):
                parts = geo.Split(cut) or []
                return [m for m in parts
                        if cut.DistanceTo(m.GetBoundingBox(True).Center) > 0]
            # Brep.Trim keeps the side opposite the cutter normal
            flipped = RG.Plane(cut.Origin, RG.Vector3d(-nLight.X, -nLight.Y, -nLight.Z))
            out = []
            for piece in geo.Trim(flipped, tol) or []:
                capped = piece.CapPlanarHoles(tol)
                out.append(capped if capped is not None else piece)
            return out

        def shadow_region_on_plane(plane, nLight):
            # union of all caster shadow on 'plane', cast only by geometry to light
            xf = RG.Transform.ProjectAlong(plane, u)
            pieces = []
            for _, geo in casters:
                for part in upstream_part(geo, plane, nLight):
                    crvs = List[RG.Curve]()
                    for loop, _ in silhouette_loops(part):
                        d = loop.DuplicateCurve()
                        if d.Transform(xf):
                            crvs.Add(d)
                    if crvs.Count:
                        b = RG.Brep.CreatePlanarBreps(crvs, tol)
                        if b:
                            pieces.extend(b)
            if len(pieces) > 1:
                merged = RG.Brep.CreatePlanarUnion(List[RG.Brep](pieces), plane, tol)
                if merged:
                    pieces = list(merged)
            return pieces

        def buried_regions(plane, skipId=None):
            # removed hidden regions
            secs = []
            for gid, g in occluders.items():
                if gid == skipId or not isinstance(g, RG.Brep) or not g.IsSolid:
                    continue
                ok, crvs, _ = RG.Intersect.Intersection.BrepPlane(g, plane, tol)
                if not ok or not crvs:
                    continue
                joined = RG.Curve.JoinCurves(crvs, tol * 2.0, False)
                closed = List[RG.Curve]([c for c in joined if c.IsClosed])
                if closed.Count:
                    b = RG.Brep.CreatePlanarBreps(closed, tol)
                    if b:
                        secs.extend(b)
            return secs

        def subtract(pieces, cutters, plane):
            for cutter in cutters:
                nxt = []
                for p in pieces:
                    res = RG.Brep.CreatePlanarDifference(p, cutter, plane, tol)
                    if res is None:
                        nxt.append(p)          # no overlap / boolean failed
                    else:
                        nxt.extend(res)        # empty list = fully removed
                pieces = nxt
            return pieces

        def make_hatches(brep):
            out = []
            for face in brep.Faces:
                crvs = List[RG.Curve]([lp.To3dCurve() for lp in face.Loops])
                hs = RG.Hatch.Create(crvs, hatchIdx, 0.0, 1.0, tol)
                if hs:
                    out.extend(hs)
            return out

        hatches = []
        if blnC:
            nC = cPlane.Normal
            if _dot(nC, u) > 0:
                nC = RG.Vector3d(-nC.X, -nC.Y, -nC.Z)
            if abs(_dot(nC, u)) > 1e-3:
                pieces = shadow_region_on_plane(cPlane, nC)
                pieces = subtract(pieces, buried_regions(cPlane), cPlane)
                for piece in pieces:
                    hatches.extend(make_hatches(piece))

        # planar target faces that face the light
        for tid, tb in targets:
            if not isinstance(tb, RG.Brep):
                continue
            for face in tb.Faces:
                ok, fp = face.TryGetPlane(tol)
                if not ok:
                    continue
                nrm = face.NormalAt(face.Domain(0).Mid, face.Domain(1).Mid)
                if face.OrientationIsReversed:
                    nrm = RG.Vector3d(-nrm.X, -nrm.Y, -nrm.Z)
                if _dot(nrm, u) > -1e-3:
                    continue  # faces away from (or parallel to) the light
                nLight = _unit(nrm)
                fb = face.DuplicateFace(False)
                pieces = []
                for reg in shadow_region_on_plane(fp, nLight):
                    res = RG.Brep.CreatePlanarIntersection(fb, reg, fp, tol)
                    if res:
                        pieces.extend(res)
                if not pieces:
                    continue
                # remove parts buried inside objects
                pieces = subtract(pieces, buried_regions(fp, skipId=tid), fp)
                for piece in pieces:
                    hatches.extend(make_hatches(piece))

        # add to document
        vecLayer = _ensure_layer(VECTOR_LAYER, System.Drawing.Color.FromArgb(0, 0, 0))
        hatLayer = _ensure_layer(HATCH_LAYER, System.Drawing.Color.FromArgb(0, 0, 0))

        vAttr = Rhino.DocObjects.ObjectAttributes()
        vAttr.LayerIndex = vecLayer
        hAttr = Rhino.DocObjects.ObjectAttributes()
        hAttr.LayerIndex = hatLayer

        newIds = [sc.doc.Objects.AddCurve(c, vAttr) for c in outlines]
        newIds += [sc.doc.Objects.AddHatch(h, hAttr) for h in hatches]

        sc.doc.Objects.UnselectAll()
        if newIds:
            rs.SelectObjects(newIds)
        print("Shadow curves: {}, hatches: {}".format(len(outlines), len(hatches)))
    finally:
        rs.EnableRedraw(True)
        sc.doc.Views.Redraw()


if __name__ == "__main__":
    ShadowCurves()