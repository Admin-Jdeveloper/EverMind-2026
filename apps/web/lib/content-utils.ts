/**
 * MediaCompile — Centralized Content Classification & Statistics Formatter
 * 
 * Enforces canonical primary types:
 * - Document: PDF, PPTX, DOCX, XLSX, TXT, and other file uploads
 * - Link: Website URLs, YouTube, Instagram, Twitter/X, and external links
 * - Note: User-created text entries
 * 
 * Platform names and file formats are strictly secondary metadata.
 * Real statistics only — NO fabricated or hardcoded page counts / durations.
 */

export type CanonicalType = 'Document' | 'Link' | 'Note';

export interface FormattedContentMeta {
  primaryType: CanonicalType;
  secondaryLabel: string; // e.g. "PDF", "DOCX", "youtube.com", "x.com", "Plain text"
  statsLabel: string;     // e.g. "24 chunks" or "12 pages · 24 chunks"
  fullBadge: string;      // e.g. "Document · PDF · 24 chunks"
  platform?: string;
  format?: string;
  domain?: string;
  title?: string;
  secondaryBadge?: string;
  statBadge?: string;
  url?: string;
}

export type CanonicalContentMeta = FormattedContentMeta;

/**
 * Extracts clean domain name from URL (e.g., "arxiv.org", "github.com")
 */
export function extractDomain(urlStr?: string): string {
  if (!urlStr) return '';
  try {
    const parsed = new URL(urlStr);
    return parsed.hostname.replace(/^www\./, '');
  } catch {
    return urlStr.slice(0, 30);
  }
}

/**
 * Detects platform name if known social/media platform
 */
export function detectPlatform(urlStr?: string, metadata?: Record<string, any>): string | null {
  if (metadata?.platform) {
    const p = String(metadata.platform).toLowerCase();
    if (p.includes('youtube')) return 'YouTube';
    if (p.includes('instagram')) return 'Instagram';
    if (p.includes('twitter') || p.includes('x.com')) return 'Twitter/X';
    return metadata.platform;
  }

  if (!urlStr) return null;
  const lower = urlStr.toLowerCase();
  if (lower.includes('youtube.com') || lower.includes('youtu.be')) return 'YouTube';
  if (lower.includes('instagram.com')) return 'Instagram';
  if (lower.includes('twitter.com') || lower.includes('x.com')) return 'Twitter/X';
  return null;
}

/**
 * Detects file format for documents
 */
export function detectFileFormat(item: any): string {
  if (item.metadata?.format) return String(item.metadata.format).toUpperCase();
  if (item.metadata?.extension) return String(item.metadata.extension).replace('.', '').toUpperCase();

  const filename = item.metadata?.filename || item.title || '';
  const match = filename.match(/\.([0-9a-z]+)$/i);
  if (match) {
    return match[1].toUpperCase();
  }

  if (item.content_type === 'document' || item.content_type === 'file') {
    return 'PDF';
  }
  return '';
}

/**
 * Formats canonical content metadata with 100% genuine persisted statistics.
 * NEVER fabricates fake page counts or durations.
 */
export function getCanonicalContentMeta(item: any): FormattedContentMeta {
  const rawType = (item.content_type || '').toLowerCase();
  const meta = item.metadata || {};
  const chunksCount = item.chunk_count ?? (Array.isArray(item.chunks) ? item.chunks.length : (item.chunks ?? 0));
  
  // 1. Determine Primary Type
  let primaryType: CanonicalType = 'Document';
  if (rawType === 'note') {
    primaryType = 'Note';
  } else if (rawType === 'url' || rawType === 'video' || Boolean(item.source_url && !item.file_key)) {
    primaryType = 'Link';
  } else {
    primaryType = 'Document';
  }

  // 2. Secondary Label
  let secondaryLabel = '';
  let platform: string | undefined;
  let format: string | undefined;
  let domain: string | undefined;

  if (primaryType === 'Document') {
    format = detectFileFormat(item) || 'PDF';
    secondaryLabel = format;
  } else if (primaryType === 'Link') {
    platform = detectPlatform(item.source_url, meta) || undefined;
    domain = extractDomain(item.source_url) || (platform ? `${platform.toLowerCase()}.com` : 'link');
    secondaryLabel = platform || domain;
  } else {
    secondaryLabel = 'Note';
  }

  // 3. Genuine Statistics
  const statParts: string[] = [];

  // Real page count if verified
  if (primaryType === 'Document' && typeof meta.page_count === 'number' && meta.page_count > 0) {
    statParts.push(`${meta.page_count} page${meta.page_count === 1 ? '' : 's'}`);
  }

  // Real video runtime if verified
  if (primaryType === 'Link' && typeof meta.duration === 'number' && meta.duration > 0) {
    const mins = Math.round(meta.duration / 60);
    statParts.push(`${mins} min`);
  }

  // Real chunk count
  if (typeof chunksCount === 'number' && chunksCount > 0) {
    statParts.push(`${chunksCount} chunk${chunksCount === 1 ? '' : 's'}`);
  } else if (item.ingestion_status && item.ingestion_status !== 'completed') {
    statParts.push(item.ingestion_status);
  }

  const statsLabel = statParts.join(' · ') || secondaryLabel;

  // 4. Combined Badge
  const fullBadge = statParts.length > 0
    ? `${primaryType} · ${secondaryLabel} · ${statsLabel}`
    : `${primaryType} · ${secondaryLabel}`;

  return {
    primaryType,
    secondaryLabel,
    statsLabel,
    fullBadge,
    platform,
    format,
    domain,
    title: item.title || secondaryLabel || 'Untitled item',
    secondaryBadge: secondaryLabel,
    statBadge: statsLabel,
    url: item.source_url || '',
  };
}
