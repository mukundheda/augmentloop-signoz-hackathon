export const CAMERA_PRESETS = ["overview", "orbit", "top", "chase", "follow"] as const;
export type DemoCamera = typeof CAMERA_PRESETS[number];
export type DemoSpeed = 0.5 | 1 | 2 | 4;

export const isDemoSpeed = (value: number): value is DemoSpeed =>
  value === 0.5 || value === 1 || value === 2 || value === 4;

export interface ToyWorldDemoApi {
  setCamera(camera: DemoCamera): void;
  setOrbit(enabled: boolean): void;
  setSpeed(speed: DemoSpeed): void;
  selectFirstActiveAgent(): boolean;
  restart(): void;
  completeRun(): void;
  getStatus(): {
    decisions: number;
    correct: number;
    cost: number;
    state: string;
  };
}

declare global {
  interface Window {
    toyWorldDemo?: ToyWorldDemoApi;
  }
}
