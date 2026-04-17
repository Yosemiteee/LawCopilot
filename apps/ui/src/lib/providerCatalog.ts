import providerCatalogJson from "../../../../configs/provider-model-catalog.json";

type ProviderCatalogEntry = {
  baseUrl?: string;
  defaultModel?: string;
  suggestedModels?: string[];
};

type ProviderCatalogFile = {
  providers?: Record<string, ProviderCatalogEntry>;
};

const providerCatalog = providerCatalogJson as ProviderCatalogFile;

export function uniqueProviderModels(values: string[]): string[] {
  const next: string[] = [];
  for (const value of values) {
    const normalized = String(value || "").trim();
    if (!normalized || next.includes(normalized)) {
      continue;
    }
    next.push(normalized);
  }
  return next;
}

export function providerPresetCatalog(type: string): ProviderCatalogEntry {
  const normalized = String(type || "openai").trim() || "openai";
  return providerCatalog.providers?.[normalized] || providerCatalog.providers?.openai || {};
}
