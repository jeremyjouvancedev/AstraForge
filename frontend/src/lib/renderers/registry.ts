import { DiffPreview, type DiffPreviewProps } from "@/components/diff-preview";
import { SpecViewer, type SpecViewerProps } from "@/components/spec-viewer";
import { TestReport, type TestReportProps } from "@/components/test-report";
import type { ComponentType } from "react";

class RendererRegistry {
  private readonly items = new Map<string, ComponentType<unknown>>();

  register<TProps>(id: string, component: ComponentType<TProps>) {
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

rendererRegistry.register<DiffPreviewProps>("diff", DiffPreview);
rendererRegistry.register<SpecViewerProps>("spec", SpecViewer);
rendererRegistry.register<TestReportProps>("test-report", TestReport);
