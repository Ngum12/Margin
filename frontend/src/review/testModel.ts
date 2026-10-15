// The Mock models' names start with this; real models never do (backend: provenance.py).
const TEST_MODEL_PREFIX = "mock-";

export function isTestModel(name: string | null | undefined): boolean {
  return name?.startsWith(TEST_MODEL_PREFIX) ?? false;
}
