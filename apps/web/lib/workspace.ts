export type WorkspaceId = "personal" | "sandbox";

export interface Workspace {
  id: WorkspaceId;
  name: string;
}

export const workspaces: ReadonlyArray<Workspace> = [
  { id: "personal", name: "Personal" },
  { id: "sandbox", name: "Sandbox" },
] as const;

export const defaultWorkspaceId: WorkspaceId = "personal";
