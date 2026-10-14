export function sampleMotion(frames, time) {
  if (!frames?.length || time < 0) return { jawOpen: 0, mouthPucker: 0 };
  let i = 0;
  while (i + 1 < frames.length && frames[i + 1].time <= time) i++;
  if (time >= frames[frames.length - 1].time)
    return { jawOpen: 0, mouthPucker: 0 };
  const a = frames[i],
    b = frames[Math.min(i + 1, frames.length - 1)];
  const fraction = Math.max(
    0,
    Math.min(1, (time - a.time) / Math.max(0.001, b.time - a.time)),
  );
  return {
    jawOpen: a.jawOpen + (b.jawOpen - a.jawOpen) * fraction,
    mouthPucker: a.mouthPucker + (b.mouthPucker - a.mouthPucker) * fraction,
  };
}

export function inspectGLB(buffer) {
  if (buffer.byteLength > 20 * 1024 * 1024 || buffer.byteLength < 28)
    throw Error("GLB_SIZE_INVALID");
  const view = new DataView(buffer);
  if (
    view.getUint32(0, true) !== 0x46546c67 ||
    view.getUint32(4, true) !== 2 ||
    view.getUint32(8, true) !== buffer.byteLength ||
    view.getUint32(16, true) !== 0x4e4f534a
  )
    throw Error("GLB_2_REQUIRED");
  const length = view.getUint32(12, true);
  if (length > 1024 * 1024 || length + 20 > buffer.byteLength)
    throw Error("GLB_JSON_INVALID");
  const doc = JSON.parse(
    new TextDecoder().decode(new Uint8Array(buffer, 20, length)),
  );
  if (
    (doc.buffers || []).some((b) => b.uri) ||
    (doc.images || []).some((i) => i.uri)
  )
    throw Error("GLB_EXTERNAL_RESOURCES_DENIED");
  if (
    doc.extensionsRequired?.some(
      (e) => e !== "KHR_materials_unlit" && e !== "KHR_mesh_quantization",
    )
  )
    throw Error("GLB_REQUIRED_EXTENSION_UNSUPPORTED");
  const names = (doc.meshes || []).flatMap((m) => m.extras?.targetNames || []);
  const hasJaw = (doc.meshes || []).some((m) => {
    const index = (m.extras?.targetNames || []).findIndex(
      (n) => typeof n === "string" && n.toLowerCase() === "jawopen",
    );
    return (
      index >= 0 &&
      (m.primitives || []).some((p) => {
        const target = doc.accessors?.[p.targets?.[index]?.POSITION],
          base = doc.accessors?.[p.attributes?.POSITION];
        return (
          target?.type === "VEC3" &&
          base?.count > 0 &&
          target.count === base.count
        );
      })
    );
  });
  if (!hasJaw) throw Error("GLB_JAWOPEN_MORPH_REQUIRED");
  if (
    (doc.accessors || []).some(
      (a) => !Number.isSafeInteger(a.count) || a.count < 0 || a.count > 1000000,
    )
  )
    throw Error("GLB_ACCESSOR_LIMIT");
  return {
    morphTargets: [...new Set(names)],
    vertices: (doc.meshes || [])
      .flatMap((m) => m.primitives || [])
      .reduce(
        (n, p) => n + (doc.accessors?.[p.attributes?.POSITION]?.count || 0),
        0,
      ),
  };
}
