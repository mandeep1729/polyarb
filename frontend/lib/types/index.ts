export interface Market {
  id: number;
  platform_id: number;
  platform_market_id: string;
  platform_name: string;
  platform_slug: string;
  question: string;
  description: string | null;
  category: string | null;
  outcomes: Record<string, string>;
  outcome_prices: Record<string, number>;
  volume_total: number | null;
  volume_24h: number | null;
  liquidity: number | null;
  start_date: string | null;
  end_date: string | null;
  status: string;
  resolution: string | null;
  event_ticker: string | null;
  series_ticker: string | null;
  yes_ask: number | null;
  no_ask: number | null;
  deep_link_url: string | null;
  image_url: string | null;
  price_change_24h: number | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PriceSnapshot {
  outcome_prices: Record<string, number>;
  volume: number | null;
  timestamp: string;
}

export interface TrendingMarket {
  market: Market;
  trending_score: number;
}

export interface ArbitrageOpportunity {
  id: number;
  market_a: Market;
  market_b: Market;
  similarity_score: number;
  odds_delta: number | null;
  match_method: string;
  is_confirmed: boolean;
  last_checked_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: string | null;
  total: number;
}

export interface MarketGroup {
  id: number;
  canonical_question: string;
  category: string | null;
  consensus_yes: number | null;
  consensus_no: number | null;
  disagreement_score: number | null;
  member_count: number;
  total_volume: number | null;
  total_liquidity: number | null;
  best_yes_market_id: number | null;
  best_no_market_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface GroupDetail {
  group: MarketGroup;
  members: Market[];
  best_yes_market: Market | null;
  best_no_market: Market | null;
}

export interface GroupSnapshot {
  consensus_yes: number | null;
  consensus_no: number | null;
  disagreement_score: number | null;
  total_volume: number | null;
  timestamp: string;
}

export type OddsFormat = 'percentage' | 'decimal' | 'fractional';
