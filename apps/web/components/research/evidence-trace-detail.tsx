import type { ReactElement, ReactNode } from "react";

import {
  CapsLabel,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui";
import type { components } from "@/lib/api";
import { cn } from "@/lib/cn";

type EvidenceTracePublic = components["schemas"]["EvidenceTracePublic"];
type EvidenceChunkPublic = components["schemas"]["EvidenceChunkPublic"];
type EvidencePublic = components["schemas"]["EvidencePublic"];
type DataSourcePublic = components["schemas"]["DataSourcePublic"];

const NOT_RECORDED_LABEL = "Not recorded";

export interface EvidenceTraceDetailProps {
  data: EvidenceTracePublic;
}

export function EvidenceTraceDetail(
  props: EvidenceTraceDetailProps,
): ReactElement {
  const { data } = props;
  const { chunk, evidence, data_source: dataSource, context_chunks: contextChunks } =
    data;

  return (
    <div
      className="flex flex-col gap-6"
      data-testid="evidence-trace-detail"
    >
      <Card>
        <CardHeader>
          <CardTitle>SELECTED CHUNK</CardTitle>
          <CapsLabel className="text-fg-subtle">
            INDEX {chunk.chunk_index}
          </CapsLabel>
        </CardHeader>
        <CardContent>
          <p
            data-testid="selected-chunk-text"
            className="rounded-md bg-canvas border border-line p-3 text-sm text-fg italic leading-relaxed whitespace-pre-wrap"
          >
            {chunk.text}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>CONTEXT</CardTitle>
          <CapsLabel className="text-fg-subtle">
            {contextChunks.length} CHUNK{contextChunks.length === 1 ? "" : "S"}
          </CapsLabel>
        </CardHeader>
        <CardContent>
          <ul
            className="flex flex-col gap-2"
            data-testid="evidence-context-chunks"
          >
            {contextChunks.map((row) => (
              <ContextChunkRow
                key={row.id}
                chunk={row}
                isSelected={row.id === chunk.id}
              />
            ))}
          </ul>
        </CardContent>
      </Card>

      <EvidenceMetadataCard evidence={evidence} />
      <DataSourceCard dataSource={dataSource} />
    </div>
  );
}

interface ContextChunkRowProps {
  chunk: EvidenceChunkPublic;
  isSelected: boolean;
}

function ContextChunkRow(props: ContextChunkRowProps): ReactElement {
  const { chunk, isSelected } = props;
  return (
    <li
      data-testid="evidence-context-chunk"
      data-selected={isSelected ? "true" : "false"}
      className={cn(
        "rounded-md border bg-surface-2/40 p-3",
        isSelected ? "border-accent-press" : "border-line",
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        <CapsLabel className="text-fg-subtle">
          INDEX {chunk.chunk_index}
        </CapsLabel>
        {isSelected ? (
          <CapsLabel className="text-accent-text">SELECTED</CapsLabel>
        ) : null}
      </div>
      <p className="text-sm text-fg leading-relaxed whitespace-pre-wrap">
        {chunk.text}
      </p>
    </li>
  );
}

interface EvidenceMetadataCardProps {
  evidence: EvidencePublic;
}

function EvidenceMetadataCard(props: EvidenceMetadataCardProps): ReactElement {
  const { evidence } = props;
  return (
    <Card>
      <CardHeader>
        <CardTitle>EVIDENCE</CardTitle>
      </CardHeader>
      <CardContent>
        <dl
          className="grid grid-cols-1 gap-3 md:grid-cols-2"
          data-testid="evidence-metadata"
        >
          <MetaRow label="SOURCE">
            <PlainText value={evidence.source} />
          </MetaRow>
          <MetaRow label="DOCUMENT ID">
            <PlainText value={evidence.document_id} mono />
          </MetaRow>
          <MetaRow label="RAW URL">
            <RawUrlValue url={evidence.raw_url} testId="evidence-raw-url" />
          </MetaRow>
          <MetaRow label="CONTENT HASH">
            <PlainText value={evidence.content_hash} mono />
          </MetaRow>
          <MetaRow label="SIGN">
            <PlainText value={formatSign(evidence.sign)} mono />
          </MetaRow>
          <MetaRow label="MODEL">
            <PlainText value={evidence.extracted_by_model} />
          </MetaRow>
          <MetaRow label="PROMPT VERSION">
            <PlainText value={evidence.prompt_version} mono />
          </MetaRow>
          <MetaRow label="EXTRACTED AT">
            <PlainText value={evidence.extracted_at} mono />
          </MetaRow>
        </dl>
      </CardContent>
    </Card>
  );
}

interface DataSourceCardProps {
  dataSource: DataSourcePublic | null;
}

function DataSourceCard(props: DataSourceCardProps): ReactElement {
  const { dataSource } = props;
  if (dataSource === null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>DATA SOURCE</CardTitle>
        </CardHeader>
        <CardContent>
          <p
            className="text-sm text-fg-subtle"
            data-testid="data-source-empty"
          >
            {NOT_RECORDED_LABEL}
          </p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>DATA SOURCE</CardTitle>
      </CardHeader>
      <CardContent>
        <dl
          className="grid grid-cols-1 gap-3 md:grid-cols-2"
          data-testid="data-source-metadata"
        >
          <MetaRow label="NAME">
            <PlainText value={dataSource.name} />
          </MetaRow>
          <MetaRow label="KIND">
            <PlainText value={dataSource.kind} mono />
          </MetaRow>
          <MetaRow label="HOMEPAGE">
            <RawUrlValue url={dataSource.homepage_url} testId="data-source-homepage" />
          </MetaRow>
          <MetaRow label="DESCRIPTION">
            <PlainText value={dataSource.description} />
          </MetaRow>
        </dl>
      </CardContent>
    </Card>
  );
}

interface MetaRowProps {
  label: string;
  children: ReactNode;
}

function MetaRow(props: MetaRowProps): ReactElement {
  const { label, children } = props;
  return (
    <div className="rounded-md border border-line bg-surface-2/40 p-3">
      <dt className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
        {label}
      </dt>
      <dd className="mt-1 text-sm text-fg leading-relaxed break-all">
        {children}
      </dd>
    </div>
  );
}

interface PlainTextProps {
  value: string | null | undefined;
  mono?: boolean;
}

function PlainText(props: PlainTextProps): ReactElement {
  const { value, mono = false } = props;
  if (value === null || value === undefined || value.length === 0) {
    return (
      <span className="text-fg-subtle italic">{NOT_RECORDED_LABEL}</span>
    );
  }
  return (
    <span className={cn(mono ? "font-mono tabular-nums" : undefined)}>
      {value}
    </span>
  );
}

interface RawUrlValueProps {
  url: string | null | undefined;
  testId: string;
}

function RawUrlValue(props: RawUrlValueProps): ReactElement {
  const { url, testId } = props;
  if (url === null || url === undefined || url.length === 0) {
    return (
      <span className="text-fg-subtle italic">{NOT_RECORDED_LABEL}</span>
    );
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer noopener"
      className="font-mono text-highlight-text hover:underline break-all"
      data-testid={testId}
    >
      {url}
    </a>
  );
}

function formatSign(value: number): string {
  return value.toFixed(2);
}
