import { useEffect, useRef, useState, type MutableRefObject } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { inspectGLB } from "./face-motion.mjs";

export type Motion = { jawOpen: number; mouthPucker: number; manual?: boolean };
export default function FaceViewer({
  model,
  drive,
}: {
  model: ArrayBuffer;
  drive: MutableRefObject<Motion>;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    setReady(false);
    setError("");
    let disposed = false,
      frame = 0;
    let renderer: THREE.WebGLRenderer | undefined,
      controls: OrbitControls | undefined,
      loaded: THREE.Object3D | undefined;
    const container = host.current!;
    try {
      inspectGLB(model);
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(2, devicePixelRatio));
      renderer.setSize(container.clientWidth, container.clientHeight);
      container.appendChild(renderer.domElement);
      const scene = new THREE.Scene(),
        camera = new THREE.PerspectiveCamera(
          35,
          container.clientWidth / container.clientHeight,
          0.001,
          100,
        );
      scene.add(new THREE.HemisphereLight(0xffffff, 0x687c64, 3));
      const light = new THREE.DirectionalLight(0xffffff, 2);
      light.position.set(1, 1, 3);
      scene.add(light);
      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      const manager = new THREE.LoadingManager();
      manager.setURLModifier((url) => {
        if (url.startsWith("blob:") || url.startsWith("data:")) return url;
        throw Error("EXTERNAL_RESOURCE_BLOCKED");
      });
      new GLTFLoader(manager).parse(
        model.slice(0),
        "",
        (gltf) => {
          if (disposed) {
            disposeTree(gltf.scene);
            return;
          }
          loaded = gltf.scene;
          const box = new THREE.Box3().setFromObject(loaded),
            center = box.getCenter(new THREE.Vector3()),
            size = box.getSize(new THREE.Vector3());
          loaded.position.sub(center);
          scene.add(loaded);
          const span = Math.max(size.x, size.y, size.z, 0.01);
          camera.position.set(0, 0, span * 2);
          camera.lookAt(0, 0, 0);
          controls!.target.set(0, 0, 0);
          loaded.traverse((node) => {
            const mesh = node as THREE.Mesh;
            if (mesh.isMesh && !mesh.geometry.attributes.normal)
              mesh.geometry.computeVertexNormals();
          });
          let textures = 0;
          loaded.traverse((node) => {
            const mesh = node as THREE.Mesh;
            if (mesh.isMesh) {
              for (const material of Array.isArray(mesh.material)
                ? mesh.material
                : [mesh.material]) {
                if ((material as THREE.MeshBasicMaterial).map) textures++;
              }
            }
          });
          container.dataset.textures = String(textures);
          setReady(true);
          container.dataset.ready = "true";
        },
        () => setError("模型載入失敗，請檢查 GLB 與形變通道。"),
      );
      const resize = new ResizeObserver(() => {
        if (!renderer) return;
        const width = container.clientWidth,
          height = container.clientHeight;
        renderer.setSize(width, height);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      });
      resize.observe(container);
      const draw = () => {
        if (disposed) return;
        const blink = Math.max(
          0,
          1 - Math.abs(((performance.now() / 1000) % 4.8) - 4.65) / 0.1,
        );
        let appliedJaw = 0;
        loaded?.traverse((node) => {
          const mesh = node as THREE.Mesh;
          if (!mesh.morphTargetDictionary || !mesh.morphTargetInfluences)
            return;
          for (const [name, index] of Object.entries(
            mesh.morphTargetDictionary,
          )) {
            const key = name.toLowerCase();
            let amount =
              key === "jawopen"
                ? drive.current.jawOpen
                : key === "mouthpucker"
                  ? drive.current.mouthPucker
                  : key.startsWith("eyeblink")
                    ? blink
                    : 0;
            mesh.morphTargetInfluences[index] = Math.min(
              1,
              Math.max(0, amount),
            );
            if (key === "jawopen")
              appliedJaw = mesh.morphTargetInfluences[index];
          }
        });
        container.dataset.appliedJaw = appliedJaw.toFixed(3);
        container.dataset.jaw = drive.current.jawOpen.toFixed(3);
        controls?.update();
        renderer!.render(scene, camera);
        frame = requestAnimationFrame(draw);
      };
      draw();
      return () => {
        disposed = true;
        cancelAnimationFrame(frame);
        resize.disconnect();
        controls?.dispose();
        if (loaded) disposeTree(loaded);
        renderer?.dispose();
        renderer?.domElement.remove();
      };
    } catch (e) {
      setError((e as Error).message);
      renderer?.dispose();
      renderer?.domElement.remove();
    }
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
    };
  }, [model, drive]);
  return (
    <div className="face-viewer" ref={host} aria-label="3D 人臉預覽">
      <span className="viewer-tag">
        {error || (!ready ? "正在載入 3D…" : "3D · 拖曳旋轉／滾輪縮放")}
      </span>
    </div>
  );
}
function disposeTree(tree: THREE.Object3D) {
  tree.traverse((node) => {
    const mesh = node as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.geometry.dispose();
    for (const material of Array.isArray(mesh.material)
      ? mesh.material
      : [mesh.material]) {
      for (const value of Object.values(material)) {
        if (value instanceof THREE.Texture) {
          const data = value.source?.data;
          if (data?.close) data.close();
          value.dispose();
        }
      }
      material.dispose();
    }
  });
}
