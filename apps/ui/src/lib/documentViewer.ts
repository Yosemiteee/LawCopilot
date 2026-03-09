import type { Citation, MatterDocument, MatterWorkspaceDocumentLink } from "../types/domain";

export type DocumentViewerScope = "workspace" | "matter";

export type DocumentViewerTarget = {
  scope: DocumentViewerScope;
  documentId: number;
  matterId?: number | null;
  chunkId?: number | string | null;
  chunkIndex?: number | null;
  excerpt?: string | null;
};

export type DocumentReference = {
  label: string;
  subtitle?: string;
  target: DocumentViewerTarget;
};

const SCOPE_TO_SLUG: Record<DocumentViewerScope, string> = {
  workspace: "calisma-alani",
  matter: "dosya",
};

export function buildDocumentViewerPath(target: DocumentViewerTarget) {
  const params = new URLSearchParams();
  if (target.matterId) {
    params.set("dosya", String(target.matterId));
  }
  if (target.chunkId !== undefined && target.chunkId !== null) {
    params.set("parcaKimligi", String(target.chunkId));
  }
  if (target.chunkIndex !== undefined && target.chunkIndex !== null) {
    params.set("parca", String(target.chunkIndex));
  }
  if (target.excerpt) {
    params.set("alinti", target.excerpt);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/belge/${SCOPE_TO_SLUG[target.scope]}/${target.documentId}${suffix}`;
}

export function parseDocumentViewerScope(scopeSlug: string | undefined) {
  if (scopeSlug === "calisma-alani") {
    return "workspace" as const;
  }
  if (scopeSlug === "dosya") {
    return "matter" as const;
  }
  return null;
}

export function buildCitationTarget(citation: Citation, scope: DocumentViewerScope, matterId?: number | null): DocumentViewerTarget {
  return {
    scope,
    documentId: citation.document_id,
    matterId: scope === "matter" ? (matterId || citation.matter_id || null) : null,
    chunkId: citation.chunk_id,
    chunkIndex: citation.chunk_index,
    excerpt: citation.excerpt,
  };
}

export function resolveSourceDocumentReferences(
  labels: string[],
  matterDocuments: MatterDocument[],
  workspaceDocuments: MatterWorkspaceDocumentLink[],
  matterId: number,
) {
  if (!labels.length) {
    return [];
  }

  const refs: DocumentReference[] = [];
  const seen = new Set<string>();

  const normalizedHints = labels
    .map(normalizeSourceLabel)
    .filter(Boolean);

  const candidates: Array<DocumentReference & { normalized: string; alternative: string }> = [
    ...workspaceDocuments.map((document) => ({
      label: document.display_name,
      subtitle: document.relative_path,
      target: {
        scope: "workspace" as const,
        documentId: document.workspace_document_id,
        matterId,
      },
      normalized: normalizeSourceLabel(document.display_name),
      alternative: normalizeSourceLabel(document.relative_path),
    })),
    ...matterDocuments.map((document) => ({
      label: document.display_name,
      subtitle: document.filename,
      target: {
        scope: "matter" as const,
        documentId: document.id,
        matterId,
      },
      normalized: normalizeSourceLabel(document.display_name),
      alternative: normalizeSourceLabel(document.filename.replace(/\.[^.]+$/, "")),
    })),
  ];

  for (const hint of normalizedHints) {
    for (const candidate of candidates) {
      if (!candidate.normalized && !candidate.alternative) {
        continue;
      }
      const matches =
        candidate.normalized === hint ||
        candidate.alternative === hint ||
        candidate.normalized.includes(hint) ||
        hint.includes(candidate.normalized) ||
        candidate.alternative.includes(hint) ||
        hint.includes(candidate.alternative);
      if (!matches) {
        continue;
      }
      const key = `${candidate.target.scope}:${candidate.target.documentId}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      refs.push({
        label: candidate.label,
        subtitle: candidate.subtitle,
        target: candidate.target,
      });
    }
  }

  return refs;
}

function normalizeSourceLabel(value: string) {
  return value
    .replace(/^[-\s]+/, "")
    .replace(/\([^)]*\)/g, "")
    .replace(/[“”"'`]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase("tr");
}
