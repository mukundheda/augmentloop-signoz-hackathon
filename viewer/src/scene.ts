import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type {
  AgentDecision,
  Coordinate,
  PuneMap,
  RaceRun,
  RoadMapping
} from "./domain";
import { buildWaves, samplePolyline } from "./replay";

const CENTER = { lon: 73.8525, lat: 18.5125 };
const SCALE = 760;
const project = ([lon, lat]: Coordinate, y = 0) =>
  new THREE.Vector3((lon - CENTER.lon) * SCALE, y, -(lat - CENTER.lat) * SCALE);

type ActiveAgent = {
  agent: AgentDecision;
  group: THREE.Group;
  route: THREE.Line;
  started: number;
  duration: number;
  completed: boolean;
};

export interface PlaybackCallbacks {
  onAgent(agent: AgentDecision): void;
  onProgress(agent: AgentDecision, wave: number, waves: number): void;
  onComplete(): void;
}

export type CameraPreset = "overview" | "orbit" | "top" | "chase" | "follow";

function makeLabel(text: string, color = "#a8bad4"): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 112;
  const context = canvas.getContext("2d")!;
  context.font = "600 30px ui-monospace, monospace";
  context.fillStyle = "rgba(5,9,16,.88)";
  context.roundRect(4, 12, 504, 88, 14);
  context.fill();
  context.fillStyle = color;
  context.fillText(text, 24, 66);
  const texture = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false })
  );
  sprite.scale.set(7.5, 1.65, 1);
  return sprite;
}

export function roadSegmentGeometry(polyline: Coordinate[], width: number): THREE.BufferGeometry {
  const positions: number[] = [];
  const indices: number[] = [];
  let vertex = 0;
  const points = polyline.map((point) => project(point, 0.015));
  for (let index = 1; index < points.length; index += 1) {
      const before = points[index - 1];
      const after = points[index];
      const dx = after.x - before.x;
      const dz = after.z - before.z;
      const length = Math.hypot(dx, dz) || 1;
      const offsetX = (-dz / length) * width;
      const offsetZ = (dx / length) * width;
      positions.push(
        before.x + offsetX, 0.015, before.z + offsetZ,
        before.x - offsetX, 0.015, before.z - offsetZ,
        after.x + offsetX, 0.015, after.z + offsetZ,
        after.x - offsetX, 0.015, after.z - offsetZ
      );
      indices.push(vertex, vertex + 1, vertex + 2, vertex + 2, vertex + 1, vertex + 3);
      vertex += 4;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

function ribbonGeometry(features: PuneMap["features"]): THREE.BufferGeometry {
  const geometries: THREE.BufferGeometry[] = [];
  const positions: number[] = [];
  const indices: number[] = [];
  let vertexOffset = 0;
  for (const feature of features) {
    if (feature.properties.kind !== "road" || feature.geometry.type !== "LineString") continue;
    const geometry = roadSegmentGeometry(
      feature.geometry.coordinates as Coordinate[],
      (feature.properties.width ?? 0.065) * 7
    );
    geometries.push(geometry);
    const position = geometry.getAttribute("position");
    positions.push(...Array.from(position.array));
    const index = geometry.getIndex();
    if (index) indices.push(...Array.from(index.array, (value) => Number(value) + vertexOffset));
    vertexOffset += position.count;
  }
  geometries.forEach((geometry) => geometry.dispose());
  const merged = new THREE.BufferGeometry();
  merged.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  merged.setIndex(indices);
  merged.computeVertexNormals();
  return merged;
}

function laneGeometry(features: PuneMap["features"]): THREE.BufferGeometry {
  const positions: number[] = [];
  for (const feature of features) {
    if (feature.properties.kind !== "road" || feature.geometry.type !== "LineString") continue;
    const points = (feature.geometry.coordinates as Coordinate[]).map((point) => project(point, 0.035));
    for (let index = 1; index < points.length; index += 1) {
      positions.push(...points[index - 1].toArray(), ...points[index].toArray());
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return geometry;
}

function routeLine(polyline: Coordinate[], color: string, opacity = 0.75): THREE.Line {
  const geometry = new THREE.BufferGeometry().setFromPoints(
    polyline.map((point) => project(point, 0.18))
  );
  return new THREE.Line(
    geometry,
    new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity,
      depthTest: false
    })
  );
}

export class AgentDotGeometry extends THREE.SphereGeometry {
  constructor() {
    super(0.22, 16, 12);
  }
}

function createAgentMarker(agent: AgentDecision): THREE.Group {
  const group = new THREE.Group();
  const color = new THREE.Color(agent.color);
  const body = new THREE.Mesh(
    new AgentDotGeometry(),
    new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: 2.2,
      metalness: 0.45,
      roughness: 0.25
    })
  );
  const haloScale = agent.difficulty === "hard" ? 0.52 : agent.difficulty === "medium" ? 0.43 : 0.35;
  const halo = new THREE.Mesh(
    new THREE.RingGeometry(haloScale * 0.78, haloScale, 24),
    new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: agent.decision_type === "eta_estimate" ? 0.8 : 0.46,
      side: THREE.DoubleSide
    })
  );
  halo.rotation.x = -Math.PI / 2;
  halo.position.y = -0.2;
  group.add(body, halo);
  group.userData.agent = agent;
  return group;
}

export class RaceScene {
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private controls: OrbitControls;
  private frame = 0;
  private active: ActiveAgent[] = [];
  private timers: number[] = [];
  private selected: ActiveAgent | null = null;
  private callbacks: PlaybackCallbacks | null = null;
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();
  private speed = 1;

  constructor(
    private container: HTMLElement,
    map: PuneMap,
    private roads: RoadMapping
  ) {
    this.scene.background = new THREE.Color("#04070d");
    this.scene.fog = new THREE.FogExp2("#04070d", 0.026);
    this.camera = new THREE.PerspectiveCamera(
      42,
      container.clientWidth / container.clientHeight,
      0.05,
      350
    );
    this.camera.position.set(21, 31, 33);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.shadowMap.enabled = true;
    container.appendChild(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0, 0);
    this.controls.maxPolarAngle = Math.PI * 0.48;
    this.controls.minDistance = 6;
    this.controls.maxDistance = 90;
    this.buildLighting();
    this.buildGround();
    this.buildMap(map);
    this.buildJunctions();
    this.renderer.domElement.addEventListener("pointermove", (event) => this.onPointer(event, false));
    this.renderer.domElement.addEventListener("click", (event) => this.onPointer(event, true));
    this.animate = this.animate.bind(this);
    this.frame = requestAnimationFrame(this.animate);
  }

  private buildLighting() {
    this.scene.add(new THREE.HemisphereLight("#8eb8ff", "#06101a", 2.5));
    const moon = new THREE.DirectionalLight("#d9ecff", 3.2);
    moon.position.set(12, 32, 18);
    moon.castShadow = true;
    this.scene.add(moon);
    const cityGlow = new THREE.PointLight("#19d3ae", 12, 55);
    cityGlow.position.set(-8, 12, 3);
    this.scene.add(cityGlow);
  }

  private buildGround() {
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(55, 65),
      new THREE.MeshStandardMaterial({ color: "#07101a", roughness: 0.98 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.04;
    ground.receiveShadow = true;
    this.scene.add(ground);
  }

  private buildMap(map: PuneMap) {
    const road = new THREE.Mesh(
      ribbonGeometry(map.features),
      new THREE.MeshStandardMaterial({ color: "#1a2633", roughness: 0.76, metalness: 0.08 })
    );
    this.scene.add(road);
    const lanes = new THREE.LineSegments(
      laneGeometry(map.features),
      new THREE.LineBasicMaterial({ color: "#45576a", transparent: true, opacity: 0.34 })
    );
    this.scene.add(lanes);

    const buildings = map.features.filter(
      (feature) => feature.properties.kind === "building" && feature.geometry.type === "Polygon"
    );
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const material = new THREE.MeshStandardMaterial({
      color: "#111d2a",
      emissive: "#07101b",
      emissiveIntensity: 0.5,
      roughness: 0.72,
      metalness: 0.15
    });
    const instances = new THREE.InstancedMesh(geometry, material, buildings.length);
    const dummy = new THREE.Object3D();
    buildings.forEach((feature, index) => {
      const ring = (feature.geometry.coordinates as Coordinate[][])[0];
      const points = ring.map((point) => project(point));
      const minX = Math.min(...points.map((point) => point.x));
      const maxX = Math.max(...points.map((point) => point.x));
      const minZ = Math.min(...points.map((point) => point.z));
      const maxZ = Math.max(...points.map((point) => point.z));
      const sourceHeight = feature.properties.height
        || (feature.properties.levels ?? 0) * 0.45
        || 0.7 + (index % 7) * 0.16;
      const height = Math.max(0.35, Math.min(4.5, sourceHeight * 0.12));
      dummy.position.set((minX + maxX) / 2, height / 2, (minZ + maxZ) / 2);
      dummy.scale.set(Math.max(0.14, maxX - minX), height, Math.max(0.14, maxZ - minZ));
      dummy.updateMatrix();
      instances.setMatrixAt(index, dummy.matrix);
    });
    instances.instanceMatrix.needsUpdate = true;
    this.scene.add(instances);

    for (const feature of map.features) {
      if (feature.properties.kind !== "landmark" || feature.geometry.type !== "Point") continue;
      const label = makeLabel(feature.properties.name ?? "PUNE");
      label.position.copy(project(feature.geometry.coordinates as Coordinate, 1.2));
      this.scene.add(label);
    }
  }

  private buildJunctions() {
    Object.entries(this.roads.nodes).forEach(([name, node]) => {
      const point = project(node.coordinate, 0.12);
      const marker = new THREE.Mesh(
        new THREE.CylinderGeometry(0.2, 0.27, 0.12, 12),
        new THREE.MeshStandardMaterial({
          color: "#6f83a0",
          emissive: "#243b58",
          emissiveIntensity: 1.2
        })
      );
      marker.position.copy(point);
      this.scene.add(marker);
      const label = makeLabel(name, "#d5e3f7");
      label.scale.set(2.3, 0.55, 1);
      label.position.copy(point).add(new THREE.Vector3(0, 0.72, 0));
      this.scene.add(label);
    });
  }

  play(run: RaceRun, speed: number, callbacks: PlaybackCallbacks) {
    this.stop();
    this.speed = speed;
    this.callbacks = callbacks;
    const waves = buildWaves(run, 24);
    const waveDuration = 5200 / speed;
    waves.forEach((wave, waveIndex) => {
      this.timers.push(window.setTimeout(() => {
        this.finishWave();
        this.clearWave();
        wave.agents.forEach((agent, index) => {
          this.spawn(agent, performance.now() + (index % 8) * (105 / speed), waveIndex + 1, waves.length);
        });
      }, waveIndex * waveDuration));
    });
    this.timers.push(window.setTimeout(() => {
      this.finishWave();
      this.pulseOutcomes(run);
      callbacks.onComplete();
    }, waves.length * waveDuration + 800 / speed));
  }

  pause() {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }

  restart(run: RaceRun, speed: number, callbacks: PlaybackCallbacks) {
    this.play(run, speed, callbacks);
  }

  setSpeed(speed: number) {
    this.speed = speed;
  }

  setCameraPreset(preset: CameraPreset) {
    this.setOrbit(preset === "orbit");
    if (preset === "top") {
      this.camera.position.set(0, 52, 0.01);
      this.controls.target.set(0, 0, 0);
    } else if (preset === "chase") {
      this.camera.position.set(3, 4.5, 6);
      this.controls.target.set(0, 0, -3);
    } else if (preset === "follow" && this.selected) {
      const point = this.selected.group.position;
      this.camera.position.copy(point).add(new THREE.Vector3(2.5, 3.2, 4.5));
      this.controls.target.copy(point);
    } else {
      this.camera.position.set(21, 31, 33);
      this.controls.target.set(0, 0, 0);
    }
  }

  setOrbit(enabled: boolean) {
    this.controls.autoRotate = enabled;
    this.controls.autoRotateSpeed = 0.55;
  }

  selectFirstActiveAgent(): boolean {
    const candidate = this.active.find((record) => !record.completed);
    if (!candidate) return false;
    this.selected = candidate;
    this.setCameraPreset("follow");
    return true;
  }

  private spawn(agent: AgentDecision, started: number, wave: number, waves: number) {
    const group = createAgentMarker(agent);
    const route = routeLine(agent.chosen_polyline, agent.color, 0.48);
    group.position.copy(project(agent.chosen_polyline[0], 0.32));
    this.scene.add(route, group);
    const record: ActiveAgent = {
      agent,
      group,
      route,
      started,
      duration: (2200 + Math.min(1800, agent.chosen_polyline.length * 8)) / this.speed,
      completed: false
    };
    group.userData.record = record;
    this.active.push(record);
    this.callbacks?.onAgent(agent);
    group.userData.wave = wave;
    group.userData.waves = waves;
  }

  private clearWave() {
    for (const record of this.active) {
      this.scene.remove(record.group);
      (record.group.children[0] as THREE.Mesh).geometry.dispose();
      const material = record.route.material as THREE.LineBasicMaterial;
      material.opacity = 0.08;
    }
    this.active = [];
    this.selected = null;
  }

  private finishWave() {
    for (const record of this.active) {
      if (!record.completed) this.complete(record);
    }
  }

  private pulseOutcomes(run: RaceRun) {
    for (const agent of run.agents.filter((entry) => entry.outcome)) {
      const pulse = routeLine(
        agent.chosen_polyline,
        agent.outcome?.on_time ? "#4dffb8" : "#ff315d",
        0.95
      );
      const material = pulse.material as THREE.LineBasicMaterial;
      this.scene.add(pulse);
      window.setTimeout(() => {
        material.opacity = 0.12;
      }, 900);
    }
  }

  private complete(record: ActiveAgent) {
    record.completed = true;
    const material = record.route.material as THREE.LineBasicMaterial;
    material.color.set(record.agent.is_correct ? "#35e7a0" : "#ff3f67");
    material.opacity = 0.88;
    if (!record.agent.is_correct) {
      const ghost = routeLine(record.agent.correct_polyline, "#ffd65a", 0.62);
      this.scene.add(ghost);
    }
    const markerMaterial = (record.group.children[0] as THREE.Mesh).material as THREE.MeshStandardMaterial;
    markerMaterial.emissiveIntensity = 0.65;
    this.callbacks?.onProgress(
      record.agent,
      record.group.userData.wave,
      record.group.userData.waves
    );
  }

  private onPointer(event: PointerEvent, click: boolean) {
    const bounds = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      -((event.clientY - bounds.top) / bounds.height) * 2 + 1
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const meshes = this.active.map((record) => record.group.children[0]);
    const hit = this.raycaster.intersectObjects(meshes)[0];
    if (!hit) return;
    const record = hit.object.parent?.userData.record as ActiveAgent | undefined;
    if (record) {
      this.callbacks?.onAgent(record.agent);
      if (click) {
        this.selected = record;
        this.setCameraPreset("follow");
      }
    }
  }

  private animate() {
    const now = performance.now();
    for (const record of this.active) {
      if (now < record.started) {
        record.group.visible = false;
        continue;
      }
      record.group.visible = true;
      const progress = Math.min(1, (now - record.started) / record.duration);
      const coordinate = samplePolyline(record.agent.chosen_polyline, progress);
      const ahead = samplePolyline(record.agent.chosen_polyline, Math.min(1, progress + 0.012));
      const position = project(coordinate, 0.32);
      const next = project(ahead, 0.32);
      record.group.position.copy(position);
      record.group.rotation.y = Math.atan2(next.x - position.x, next.z - position.z);
      if (progress >= 1 && !record.completed) this.complete(record);
    }
    if (this.selected && !this.selected.completed) {
      const point = this.selected.group.position;
      this.controls.target.lerp(point, 0.08);
      const desired = point.clone().add(new THREE.Vector3(2.5, 3.2, 4.5));
      this.camera.position.lerp(desired, 0.05);
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.frame = requestAnimationFrame(this.animate);
  }

  resize() {
    this.camera.aspect = this.container.clientWidth / this.container.clientHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
  }

  stop() {
    this.pause();
    this.clearWave();
  }

  dispose() {
    this.stop();
    cancelAnimationFrame(this.frame);
    this.controls.dispose();
    this.renderer.dispose();
  }
}
