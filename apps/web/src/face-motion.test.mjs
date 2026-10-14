import { test } from "node:test";
import assert from "node:assert/strict";
import { sampleMotion, inspectGLB } from "./face-motion.mjs";
test("speech motion follows audio time, ends at rest, and seeks deterministically", () => {
  const f = [
    { time: 0, jawOpen: 0, mouthPucker: 0 },
    { time: 1, jawOpen: 1, mouthPucker: 0.5 },
    { time: 2, jawOpen: 0, mouthPucker: 0 },
  ];
  assert.deepEqual(sampleMotion(f, 0.5), { jawOpen: 0.5, mouthPucker: 0.25 });
  assert.deepEqual(sampleMotion(f, 2), { jawOpen: 0, mouthPucker: 0 });
  assert.deepEqual(sampleMotion(f, -1), { jawOpen: 0, mouthPucker: 0 });
  assert.equal(sampleMotion(f, 1).jawOpen, 1);
});
function glb(doc) {
  let data = new TextEncoder().encode(JSON.stringify(doc));
  let padded = Math.ceil(data.length / 4) * 4;
  const b = new ArrayBuffer(20 + padded),
    v = new DataView(b);
  v.setUint32(0, 0x46546c67, true);
  v.setUint32(4, 2, true);
  v.setUint32(8, b.byteLength, true);
  v.setUint32(12, padded, true);
  v.setUint32(16, 0x4e4f534a, true);
  new Uint8Array(b, 20).fill(32);
  new Uint8Array(b, 20, data.length).set(data);
  return b;
}
test("GLB import blocks external requests and requires jaw morph", () => {
  assert.throws(
    () =>
      inspectGLB(
        glb({ images: [{ uri: "https://external.invalid/private.png" }] }),
      ),
    /EXTERNAL/,
  );
  assert.throws(() => inspectGLB(glb({ meshes: [] })), /JAWOPEN/);
  assert.deepEqual(
    inspectGLB(
      glb({
        meshes: [
          {
            extras: { targetNames: ["jawOpen", "mouthPucker"] },
            primitives: [
              {
                attributes: { POSITION: 0 },
                targets: [{ POSITION: 1 }, { POSITION: 1 }],
              },
            ],
          },
        ],
        accessors: [
          { count: 3, type: "VEC3" },
          { count: 3, type: "VEC3" },
        ],
      }),
    ).morphTargets,
    ["jawOpen", "mouthPucker"],
  );
  assert.throws(() => inspectGLB(new ArrayBuffer(30)), /GLB_2/);
});
