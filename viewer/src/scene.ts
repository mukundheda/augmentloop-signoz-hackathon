import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Decision, Driver, FeatureCollection, RaceRun } from "./domain";
import type { ReplayEvent } from "./replay";

type RouteRecord = { curve: THREE.CatmullRomCurve3; mesh: THREE.Mesh; base: THREE.Color };
type DriverRecord = { mesh: THREE.Group; label: HTMLDivElement; driver: Driver };
type Motion = { driverId: string; curve: THREE.CatmullRomCurve3; started: number; duration: number };

const CENTER = { lon: 73.8505, lat: 18.5075 };
const SCALE = 620;
const project = ([lon, lat]: number[]) => new THREE.Vector3((lon - CENTER.lon) * SCALE, 0, -(lat - CENTER.lat) * SCALE);

function routeKey(junction: string, route: string) {
  return `${junction}:${route}`;
}

function makeTextSprite(text: string, color = "#cbd6ef"): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const ctx = canvas.getContext("2d")!;
  ctx.font = "600 34px Inter, system-ui";
  ctx.fillStyle = "rgba(4,8,16,.82)";
  ctx.roundRect(6, 16, 500, 92, 16);
  ctx.fill();
  ctx.fillStyle = color;
  ctx.fillText(text, 28, 75);
  const texture = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false }));
  sprite.scale.set(8, 2, 1);
  return sprite;
}

export class RaceScene {
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private controls: OrbitControls;
  private routes = new Map<string, RouteRecord>();
  private drivers = new Map<string, DriverRecord>();
  private motions: Motion[] = [];
  private clock = new THREE.Clock();
  private frame = 0;

  constructor(private container: HTMLElement, world: FeatureCollection, context: FeatureCollection, run: RaceRun) {
    this.scene.background = new THREE.Color("#050812");
    this.scene.fog = new THREE.FogExp2("#050812", 0.018);
    this.camera = new THREE.PerspectiveCamera(42, container.clientWidth / container.clientHeight, 0.1, 300);
    this.camera.position.set(17, 26, 28);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.target.set(0, 0, 0);
    this.controls.maxPolarAngle = Math.PI * 0.47;
    this.controls.minDistance = 12;
    this.controls.maxDistance = 75;

    this.scene.add(new THREE.HemisphereLight("#9fc5ff", "#07101c", 2.2));
    const key = new THREE.DirectionalLight("#d9ecff", 2.8);
    key.position.set(10, 28, 12);
    this.scene.add(key);
    this.buildGround();
    this.buildCity(context);
    this.buildRoutes(world);
    this.buildDrivers(run);
    this.animate = this.animate.bind(this);
    this.frame = requestAnimationFrame(this.animate);
  }

  private buildGround() {
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(70, 70),
      new THREE.MeshStandardMaterial({ color: "#09111d", roughness: 0.96, metalness: 0.05 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.12;
    this.scene.add(ground);
    const grid = new THREE.GridHelper(70, 56, "#12253c", "#0b1828");
    grid.position.y = -0.08;
    this.scene.add(grid);
  }

  private buildCity(context: FeatureCollection) {
    const roadMaterial = new THREE.LineBasicMaterial({ color: "#314765", transparent: true, opacity: 0.72 });
    for (const feature of context.features) {
      if (feature.geometry.type === "LineString") {
        const points = (feature.geometry.coordinates as number[][]).map(project);
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), roadMaterial);
        line.position.y = feature.properties.kind === "river" ? 0.02 : 0.01;
        if (feature.properties.kind === "river") (line.material as THREE.LineBasicMaterial) = new THREE.LineBasicMaterial({ color: "#163f68" });
        this.scene.add(line);
      } else if (feature.geometry.type === "Point") {
        const point = project(feature.geometry.coordinates as number[]);
        const marker = makeTextSprite(feature.properties.name ?? "PUNE", "#8aa0bd");
        marker.position.copy(point).add(new THREE.Vector3(0, 1.4, 0));
        marker.scale.multiplyScalar(0.72);
        this.scene.add(marker);
      }
    }
    // Lightweight skyline: deterministic blocks around the corridor.
    const material = new THREE.MeshStandardMaterial({ color: "#101d2d", roughness: 0.84, metalness: 0.12 });
    for (let z = -15; z <= 16; z += 3.2) {
      for (const side of [-1, 1]) {
        const offset = side * (5.5 + ((Math.abs(z * 13) % 4) * 0.35));
        const height = 0.8 + (Math.abs((z + side * 5) * 17) % 4) * 0.55;
        const block = new THREE.Mesh(new THREE.BoxGeometry(2.1, height, 1.9), material);
        block.position.set(offset + Math.sin(z) * 1.4, height / 2, z);
        this.scene.add(block);
      }
    }
  }

  private buildRoutes(world: FeatureCollection) {
    for (const feature of world.features) {
      if (feature.properties.kind === "simulation-route") {
        const raw = feature.geometry.coordinates as number[][];
        const points = raw.map((coordinate, index) => {
          const point = project(coordinate);
          point.y = index === 1 ? 0.25 + (feature.properties.travel_time_min ?? 4) * 0.08 : 0.16;
          return point;
        });
        const curve = new THREE.CatmullRomCurve3(points);
        const base = new THREE.Color(feature.properties.is_fastest ? "#1d6f68" : "#24334b");
        const mesh = new THREE.Mesh(
          new THREE.TubeGeometry(curve, 44, 0.08, 7, false),
          new THREE.MeshStandardMaterial({ color: base, emissive: base, emissiveIntensity: 0.4, roughness: 0.35 })
        );
        this.scene.add(mesh);
        this.routes.set(routeKey(feature.properties.junction!, feature.properties.route!), { curve, mesh, base });
      } else if (feature.geometry.type === "Point" && feature.properties.label) {
        const point = project(feature.geometry.coordinates as number[]);
        const label = makeTextSprite(feature.properties.label, feature.properties.kind === "finish" ? "#ffcc66" : "#dce8ff");
        label.position.copy(point).add(new THREE.Vector3(0, 2.2, 0));
        this.scene.add(label);
      }
    }
  }

  private buildDrivers(run: RaceRun) {
    run.drivers.forEach((driver, index) => {
      const group = new THREE.Group();
      const color = new THREE.Color(driver.color);
      const body = new THREE.Mesh(
        new THREE.IcosahedronGeometry(0.28, 1),
        new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 1.8, metalness: 0.4 })
      );
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.42, 0.035, 8, 30),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.75 })
      );
      ring.rotation.x = Math.PI / 2;
      group.add(body, ring);
      const first = this.routes.get(routeKey(driver.decisions[0].junction, driver.decisions[0].chosen))!;
      group.position.copy(first.curve.getPoint(0)).add(new THREE.Vector3((index - 1.5) * 0.22, 0.35, 0));
      this.scene.add(group);
      const label = document.createElement("div");
      label.className = "world-label";
      label.style.setProperty("--driver", driver.color);
      label.innerHTML = `<b>${driver.id}</b><span>${driver.model.split("/").at(-1)}</span>`;
      this.container.appendChild(label);
      this.drivers.set(driver.id, { mesh: group, label, driver });
    });
  }

  apply(event: ReplayEvent) {
    if (event.kind === "start") {
      for (const route of this.routes.values()) this.setRouteColor(route, route.base);
      return;
    }
    if (event.kind === "decision") {
      const selected = this.routes.get(routeKey(event.decision.junction, event.decision.chosen));
      if (!selected) return;
      this.setRouteColor(selected, new THREE.Color(event.decision.correct ? "#26e6a7" : "#ff496d"));
      if (!event.decision.correct) {
        const ghost = this.routes.get(routeKey(event.decision.junction, event.decision.true_fastest));
        if (ghost) this.setRouteColor(ghost, new THREE.Color("#f5d76e"), true);
      }
      this.motions = this.motions.filter((motion) => motion.driverId !== event.driverId);
      this.motions.push({
        driverId: event.driverId,
        curve: selected.curve,
        started: performance.now(),
        duration: 1250 + event.decision.travel_time_min * 90
      });
    } else if (event.kind === "outcome") {
      const target = this.routes.get(routeKey(event.decision.junction, event.decision.chosen));
      if (target) {
        this.setRouteColor(target, new THREE.Color(event.onTime ? "#68f5b7" : "#ff264f"), true);
        target.mesh.scale.setScalar(1.35);
        setTimeout(() => target.mesh.scale.setScalar(1), 650);
      }
    }
  }

  private setRouteColor(route: RouteRecord, color: THREE.Color, bright = false) {
    const material = route.mesh.material as THREE.MeshStandardMaterial;
    material.color.copy(color);
    material.emissive.copy(color);
    material.emissiveIntensity = bright ? 2.5 : 1.1;
  }

  private animate() {
    this.controls.update();
    const now = performance.now();
    for (const motion of this.motions) {
      const driver = this.drivers.get(motion.driverId);
      if (!driver) continue;
      const progress = Math.min(1, (now - motion.started) / motion.duration);
      const eased = progress < 0.5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2;
      driver.mesh.position.copy(motion.curve.getPoint(eased)).add(new THREE.Vector3(0, 0.35, 0));
      driver.mesh.rotation.y += 0.025;
    }
    this.motions = this.motions.filter((motion) => now - motion.started < motion.duration);
    for (const record of this.drivers.values()) {
      const projected = record.mesh.position.clone().project(this.camera);
      record.label.style.transform = `translate(-50%, -100%) translate(${(projected.x * 0.5 + 0.5) * this.container.clientWidth}px, ${(-projected.y * 0.5 + 0.5) * this.container.clientHeight}px)`;
      record.label.style.opacity = projected.z < 1 ? "1" : "0";
    }
    this.renderer.render(this.scene, this.camera);
    this.frame = requestAnimationFrame(this.animate);
  }

  resize() {
    this.camera.aspect = this.container.clientWidth / this.container.clientHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
  }

  resetCamera() {
    this.camera.position.set(17, 26, 28);
    this.controls.target.set(0, 0, 0);
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.controls.dispose();
    this.renderer.dispose();
  }
}
