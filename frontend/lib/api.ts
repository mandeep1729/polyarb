import type {
  Market,
  MarketGroup,
  GroupDetail,
  GroupSnapshot,
  PriceSnapshot,
  TrendingMarket,
  ArbitrageOpportunity,
  PaginatedResponse,
} from '@/lib/types';

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001/api/v1';

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function fetcher<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_URL}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });
  if (!res.ok) {
    throw new ApiError(
      `API error: ${res.status} ${res.statusText}`,
      res.status
    );
  }
  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | number | boolean | null | undefined> | object): string {
  const p = params as Record<string, string | number | boolean | null | undefined>;
  const entries = Object.entries(p).filter(
    ([, v]) => v !== null && v !== undefined && v !== ''
  );
  if (entries.length === 0) return '';
  return '?' + new URLSearchParams(
    entries.map(([k, v]) => [k, String(v)])
  ).toString();
}

export interface MarketFilters {
  category?: string;
  platform?: string;
  status?: string;
  sort?: string;
  end_date_min?: string;
  end_date_max?: string;
  exclude_expired?: boolean;
  cursor?: string;
  limit?: number;
}

export interface ArbitrageFilters {
  min_spread?: number;
  category?: string;
  platform?: string;
  sort?: string;
  cursor?: string;
  limit?: number;
}

export interface SearchFilters {
  category?: string;
  platform?: string;
  exclude_expired?: boolean;
  end_date_min?: string;
  end_date_max?: string;
  limit?: number;
}

export async function getMarkets(
  filters: MarketFilters = {}
): Promise<PaginatedResponse<Market>> {
  return fetcher<PaginatedResponse<Market>>(
    `/markets${qs(filters)}`
  );
}

export async function getMarket(idOrSlug: string | number): Promise<Market> {
  return fetcher<Market>(`/markets/${idOrSlug}`);
}

export async function getPriceHistory(
  marketId: number,
  interval: string = '7d'
): Promise<PriceSnapshot[]> {
  return fetcher<PriceSnapshot[]>(
    `/markets/${marketId}/price-history${qs({ interval })}`
  );
}

export async function getTrending(
  limit: number = 10,
  platform?: string
): Promise<TrendingMarket[]> {
  return fetcher<TrendingMarket[]>(`/markets/trending${qs({ limit, platform })}`);
}

export async function getArbitrage(
  filters: ArbitrageFilters = {}
): Promise<PaginatedResponse<ArbitrageOpportunity>> {
  return fetcher<PaginatedResponse<ArbitrageOpportunity>>(
    `/arbitrage${qs(filters)}`
  );
}

export async function searchMarkets(
  query: string,
  filters: SearchFilters = {}
): Promise<Market[]> {
  return fetcher<Market[]>(
    `/search${qs({ q: query, ...filters })}`
  );
}

export async function getHealth(): Promise<{ status: string }> {
  return fetcher<{ status: string }>('/health');
}

export async function getCategories(): Promise<string[]> {
  return fetcher<string[]>('/markets/categories');
}

// --- Groups ---

export interface GroupFilters {
  category?: string;
  sort_by?: string;
  end_date_min?: string;
  end_date_max?: string;
  exclude_expired?: boolean;
  cursor?: string;
  limit?: number;
}

export async function getGroups(
  filters: GroupFilters = {}
): Promise<PaginatedResponse<MarketGroup>> {
  return fetcher<PaginatedResponse<MarketGroup>>(
    `/groups${qs(filters)}`
  );
}

export async function getGroupDetail(groupId: number): Promise<GroupDetail> {
  return fetcher<GroupDetail>(`/groups/${groupId}`);
}

export async function getGroupHistory(
  groupId: number,
  days: number = 30
): Promise<GroupSnapshot[]> {
  return fetcher<GroupSnapshot[]>(
    `/groups/${groupId}/history${qs({ days })}`
  );
}

export interface GroupSearchFilters {
  category?: string;
  sort_by?: string;
  end_date_min?: string;
  end_date_max?: string;
  exclude_expired?: boolean;
  limit?: number;
}

export async function searchGroups(
  query: string,
  filters: GroupSearchFilters = {}
): Promise<PaginatedResponse<MarketGroup>> {
  return fetcher<PaginatedResponse<MarketGroup>>(
    `/groups/search${qs({ q: query, ...filters })}`
  );
}

export interface CategoryCount {
  category: string;
  display_name: string;
  count: number;
}

export interface GroupTag {
  term: string;
  count: number;
}

export async function getGroupTags(limit = 50): Promise<GroupTag[]> {
  return fetcher<GroupTag[]>(`/groups/tags${qs({ limit })}`);
}

export async function getGroupCategoryCounts(): Promise<CategoryCount[]> {
  return fetcher<CategoryCount[]>('/groups/categories');
}

export async function getMarketCategoryCounts(
  platform?: string
): Promise<CategoryCount[]> {
  return fetcher<CategoryCount[]>(`/markets/category-counts${qs({ platform })}`);
}

// --- Synonyms ---

export interface SynonymsResponse {
  custom: string[][];
  builtin: string[][];
}

export async function getSynonyms(): Promise<SynonymsResponse> {
  return fetcher<SynonymsResponse>('/synonyms');
}

export async function addSynonymGroup(
  words: string[]
): Promise<{ custom: string[][] }> {
  return fetcher<{ custom: string[][] }>('/synonyms', {
    method: 'POST',
    body: JSON.stringify({ words }),
  });
}

export async function updateSynonymGroup(
  index: number,
  words: string[]
): Promise<{ custom: string[][] }> {
  return fetcher<{ custom: string[][] }>(`/synonyms/${index}`, {
    method: 'PUT',
    body: JSON.stringify({ words }),
  });
}

export async function deleteSynonymGroup(
  index: number
): Promise<{ custom: string[][] }> {
  return fetcher<{ custom: string[][] }>(`/synonyms/${index}`, {
    method: 'DELETE',
  });
}

// --- Grouping ---

export async function triggerRegroup(): Promise<{ status: string }> {
  return fetcher<{ status: string }>('/groups/regroup', { method: 'POST' });
}

export interface GroupingStatus {
  active_groups: number;
  total_markets_grouped: number;
  last_run: string | null;
}

export async function getGroupingStatus(): Promise<GroupingStatus> {
  return fetcher<GroupingStatus>('/groups/status');
}

// --- Admin ---

export interface AdminStats {
  timestamp: string;
  platform_stats: { slug: string; name: string; total: number; expired: number; active: number }[];
  sync_health: Record<string, string | null>;
  freshness: { last_1h: number; last_6h: number; last_24h: number; older: number };
  data_quality: { pct_end_date: number; pct_categorized: number; pct_price_history: number };
  price_coverage: { zero: number; '1_to_10': number; '11_to_100': number; '100_plus': number };
  top_markets: { id: number; question: string; platform: string; snapshot_count: number; earliest: string | null; latest: string | null }[];
  task_status: Record<string, { last_run: string; status: string; duration_seconds: number; interval_seconds: number; error: string | null }>;
  arbitrage: { total_pairs: number; arb_pairs: number; avg_spread: number; best_spread: number };
  grouping: { total_active: number; cross_platform: number; cross_platform_pct: number; avg_members: number; high_disagreement: number };
  tags: Record<string, string | number>[];
  platform_slugs: string[];
}

export async function getAdminStats(): Promise<AdminStats> {
  return fetcher<AdminStats>('/admin/stats');
}

export async function searchAdminTags(
  q: string,
  limit: number = 10
): Promise<Record<string, string | number>[]> {
  return fetcher<Record<string, string | number>[]>(
    `/admin/tags/search${qs({ q, limit })}`
  );
}
