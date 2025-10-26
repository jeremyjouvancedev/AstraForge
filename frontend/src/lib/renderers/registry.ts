import { DiffPreview } from "@/components/diff-preview";
import { SpecViewer } from "@/components/spec-viewer";
import { TestReport } from "@/components/test-report";
import type { ComponentType } from "react";

type RendererComponent = ComponentType<unknown>;

class RendererRegistry {
  private readonly items = new Map<string, RendererComponent>();

  register(id: string, component: RendererComponent) {
    if (this.items.has(id)) {
      throw new Error(`Renderer ${id} already registered`);
    }
    this.items.set(id, component);
  }

  resolve<TProps = unknown>(id: string) {
    return this.items.get(id) as ComponentType<TProps> | undefined;
  }
}

export const rendererRegistry = new RendererRegistry();

rendererRegistry.register("diff", DiffPreview);
rendererRegistry.register("spec", SpecViewer);
rendererRegistry.register("test-report", TestReport);
